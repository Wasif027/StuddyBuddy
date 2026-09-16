"""Understand an uploaded image — a diagram, a worked problem, a page of notes,
or a class timetable — with the vision model, and turn it into study text.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import llm

logger = get_logger(__name__)
settings = get_settings()

_MAX_EDGE = 1536

_SYSTEM = (
    "You are StudyBuddy looking at a photo or scan a student uploaded. First classify it:\n"
    "- diagram : a labelled diagram, figure, chart or illustration\n"
    "- problem : a maths / physics / chemistry problem or worked example to solve\n"
    "- notes   : a page of handwritten or printed study notes\n"
    "- timetable: a class schedule / weekly timetable / exam timetable\n"
    "- other   : anything else study-related\n\n"
    "Then, for the whole image:\n"
    "- title: a short title for it (<=8 words)\n"
    "- markdown: a full, teaching explanation. For a diagram, explain every labelled part and "
    "what the whole thing shows. For a problem, give the complete step-by-step solution with "
    "the reasoning. For notes, explain the concepts (don't just transcribe). For a timetable, "
    "summarise it in prose.\n"
    "- transcription: the text visible in the image, cleaned up (empty if none)\n"
    "- routine: ONLY for a timetable — {\"days\": [{\"day\": \"Monday\", \"entries\": "
    "[{\"time\": \"09:00\", \"label\": \"Physics\", \"location\": \"Lab 2\"}]}]}. Otherwise {}.\n"
    "- subject: your best guess at the school subject, lowercase (e.g. \"biology\"), or \"\".\n\n"
    'Return ONLY JSON: {"kind": string, "title": string, "markdown": string, '
    '"transcription": string, "routine": object, "subject": string}'
)


@dataclass
class VisionResult:
    kind: str = "other"
    title: str = "Image"
    markdown: str = ""
    transcription: str = ""
    routine: dict[str, Any] = field(default_factory=dict)
    subject: str = ""

    @property
    def embed_text(self) -> str:
        parts = [f"# {self.title}", self.markdown]
        if self.transcription:
            parts.append("## Transcription\n\n" + self.transcription)
        return "\n\n".join(p for p in parts if p).strip()


def _data_uri(data: bytes) -> str:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((_MAX_EDGE, _MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


_TRANSCRIBE_SYSTEM = (
    "A student photographed or scanned their handwritten answer to the question below. "
    "Read it carefully — handwriting varies a lot. Produce a faithful transcription of "
    "everything they wrote: their working, every line of algebra (as LaTeX), any diagram "
    "described in words, their final answer. Do not solve it yourself, do not correct their "
    "mistakes, do not add steps they didn't write. If part is genuinely illegible, write "
    "[illegible] there.\n"
    'Return ONLY JSON: {"transcription": string, "legible": boolean, "notes": string} — '
    "notes = anything the marker should know (e.g. \"last line cut off\", \"diagram unclear\")."
)


def _pdf_to_images(data: bytes, max_pages: int = 5) -> list[bytes]:
    """Rasterise the first pages of a PDF to PNG bytes (handwritten answers are
    usually scans, so there's no text layer to extract)."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF answers need pypdfium2 installed") from exc
    pdf = pdfium.PdfDocument(data)
    out: list[bytes] = []
    try:
        for i in range(min(len(pdf), max_pages)):
            bitmap = pdf[i].render(scale=200 / 72)  # ~200 dpi
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            out.append(buf.getvalue())
    finally:
        pdf.close()
    return out


def transcribe_work(data: bytes, filename: str, question: str) -> tuple[str, str]:
    """Read a photo / PDF of a student's handwritten answer. Returns
    (transcription, notes). Raises if vision isn't configured or the file is unreadable."""
    if not (settings.vision_enabled and llm.provider_ready()):
        raise RuntimeError("reading a photo answer needs a vision-capable model configured")

    is_pdf = filename.lower().endswith(".pdf") or data[:5] == b"%PDF-"
    pages = _pdf_to_images(data) if is_pdf else [data]
    if not pages:
        raise ValueError("couldn't read any pages from that file")
    uris = []
    for p in pages[:5]:
        try:
            uris.append(_data_uri(p))
        except Exception:  # skip an unreadable page
            continue
    if not uris:
        raise ValueError("couldn't read this file as an image")

    user = f"Question: {question}\n\n(Answer image{'s' if len(uris) > 1 else ''} attached.)"
    try:
        out = llm.json_complete(_TRANSCRIBE_SYSTEM, user, max_tokens=2000, images=uris)
    except Exception as exc:
        raise RuntimeError(
            "the vision model is briefly unavailable (rate limit or network issue) — "
            "try uploading your working again in a moment"
        ) from exc
    text = str(out.get("transcription", "")).strip()
    notes = str(out.get("notes", "")).strip()
    return text, notes


def describe_image(
    data: bytes, filename: str = "image", *, hint: str | None = None,
    existing_subjects: list[str] | None = None,
) -> VisionResult:
    if not (settings.vision_enabled and llm.provider_ready()):
        raise RuntimeError(
            "image understanding needs a vision-capable model — set OPENAI_* (Gemini) "
            "or ANTHROPIC_API_KEY and VISION_ENABLED=true"
        )
    try:
        uri = _data_uri(data)
    except Exception as exc:
        raise ValueError("couldn't read this image file") from exc

    user = f"Filename: {filename}." + (f" The student says: {hint}" if hint else "")
    if existing_subjects:
        user += (
            f" The student's existing subjects: {', '.join(existing_subjects)}. "
            "If this matches one, use that exact name for 'subject' rather than coining a new one."
        )
    try:
        data_out = llm.json_complete(_SYSTEM, user, max_tokens=2600, images=[uri])
    except Exception as exc:
        # A transient provider failure (rate limit, timeout, network) must
        # degrade like the chat path does, not crash the upload with a raw 500.
        raise RuntimeError(
            "the vision model is briefly unavailable (rate limit or network issue) — "
            "try uploading this image again in a moment"
        ) from exc
    if not data_out:
        raise RuntimeError("the vision model didn't return a usable description of this image — try again")
    kind = str(data_out.get("kind", "other")).lower().strip()
    if kind not in ("diagram", "problem", "notes", "timetable", "other"):
        kind = "other"
    routine = data_out.get("routine") if isinstance(data_out.get("routine"), dict) else {}
    return VisionResult(
        kind=kind,
        title=(str(data_out.get("title", "")).strip() or filename)[:200],
        markdown=str(data_out.get("markdown", "")).strip(),
        transcription=str(data_out.get("transcription", "")).strip(),
        routine=routine or {},
        subject=str(data_out.get("subject", "")).strip().lower(),
    )
