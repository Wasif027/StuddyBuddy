"""Turn one uploaded material into study aids: a guide, a glossary, a one-page
cheat sheet, a concept map, flashcards, or a ranked list of the key slides.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.orm import Chunk, Document, DocumentSlide, User
from app.models.schemas import ConceptNode, Flashcard, SlidePreview, StudyGuideResponse
from app.services import llm

logger = get_logger(__name__)
settings = get_settings()

_KINDS = {"guide", "glossary", "cheatsheet", "concept_map", "flashcards", "key_slides"}

_MATH = " Write maths/science notation in LaTeX ($...$ inline, $$...$$ display)."

_SYS = {
    "guide": (
        "You are StudyBuddy. Turn the student's material into a revision guide in Markdown: "
        "a short overview, then the key ideas as headed sections with the definitions, "
        "formulae, dates and examples that matter, and a 'likely exam questions' list at the "
        "end. Faithful to the material; don't invent." + _MATH + " Return ONLY JSON: {\"markdown\": string}."
    ),
    "glossary": (
        "You are StudyBuddy. Extract every important term from the material and define each "
        "in one clear sentence a student would understand, ordered as they appear. Return "
        "ONLY JSON: {\"markdown\": string} where markdown is a '**term** — definition' list."
    ),
    "cheatsheet": (
        "You are StudyBuddy. Produce a dense one-page cheat sheet in Markdown: only the "
        "facts, formulae, definitions and steps worth memorising, tightly grouped under short "
        "headings. No filler sentences." + _MATH + " Return ONLY JSON: {\"markdown\": string}."
    ),
    "concept_map": (
        "You are StudyBuddy. Build a concept map of the material as a tree (2-4 levels, "
        "8-20 nodes). Each node: id (short slug), label, parent (id or null for the root), "
        "note (one short line on how it links to its parent, optional). One root. Return "
        "ONLY JSON: {\"concepts\": [{\"id\":..,\"label\":..,\"parent\":..,\"note\":..}]}."
    ),
    "flashcards": (
        "You are StudyBuddy. Make 10-20 flashcards from the material — front is a question or "
        "term, back is a concise answer, hint optional. Cover the whole material, mix recall "
        "and application." + _MATH + " Return ONLY JSON: {\"flashcards\": [{\"front\":..,\"back\":..,\"hint\":..}]}."
    ),
    "key_slides": (
        "You are StudyBuddy. From the list of slides (number + title + bullets), pick the "
        "5-10 MOST important for revision and say why each matters in one line. Return ONLY "
        "JSON: {\"slides\": [{\"index\": int, \"why\": string}]}."
    ),
}

_TITLES = {
    "guide": "Revision guide", "glossary": "Glossary", "cheatsheet": "Cheat sheet",
    "concept_map": "Concept map", "flashcards": "Flashcards", "key_slides": "Key slides",
}


def _doc_text(db: Session, document_id: str, limit: int = 40) -> str:
    rows = db.execute(
        select(Chunk.heading, Chunk.text)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
    ).all()
    parts = []
    for heading, text in rows:
        parts.append((f"## {heading}\n" if heading else "") + text)
    return "\n\n".join(parts)[:14000]


def _slides(db: Session, document_id: str) -> list[DocumentSlide]:
    return list(
        db.execute(
            select(DocumentSlide)
            .where(DocumentSlide.document_id == document_id)
            .order_by(DocumentSlide.index)
        ).scalars().all()
    )


def _offline(kind: str, text: str, title: str) -> dict:
    # Chunk text is prefixed with its own "## Heading" markers (_doc_text). Those
    # aren't sentence-terminated, so they'd otherwise glom onto the front of the
    # next real sentence — e.g. a bullet reading "## Page 1 Osmosis is...".
    text = re.sub(r"(?m)^#{1,6}\s*.*$", "", text)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]
    if kind == "flashcards":
        cards = []
        for s in sents[:15]:
            words = re.findall(r"[A-Za-z][A-Za-z\-]{4,}", s)
            if not words:
                continue
            term = words[len(words) // 2]
            cards.append({"front": s.replace(term, "_____", 1), "back": term})
        return {"flashcards": cards}
    if kind == "concept_map":
        nodes = [{"id": "root", "label": title, "parent": None}]
        for i, s in enumerate(sents[:8]):
            nodes.append({"id": f"n{i}", "label": s[:60], "parent": "root"})
        return {"concepts": nodes}
    if kind == "key_slides":
        return {"slides": []}
    body = "\n".join(f"- {s}" for s in sents[:20])
    return {"markdown": f"_(extractive summary — configure a model for a proper {title.lower()})_\n\n{body}"}


def build(db: Session, user: User, document_id: str, kind: str) -> StudyGuideResponse:
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {sorted(_KINDS)}")
    doc = db.get(Document, document_id)
    if not doc or doc.user_id != user.id:
        raise ValueError("document not found")

    title = f"{_TITLES[kind]} — {doc.title}"
    model = ""

    if kind == "key_slides":
        slides = _slides(db, document_id)
        if not slides:
            raise ValueError("this material has no slides")
        listing = "\n".join(
            f"{s.index}. {s.title or '(untitled)'} — {'; '.join(s.bullets_json[:4])}"
            for s in slides
        )
        picks: dict[int, str] = {}
        if llm.provider_ready():
            try:
                data = llm.json_complete(_SYS["key_slides"], f"{doc.title}\n\n{listing}", max_tokens=800)
                for s in data.get("slides", []):
                    picks[int(s["index"])] = str(s.get("why", "")).strip()
            except Exception as exc:  # pragma: no cover
                logger.warning("key_slides_failed", error=str(exc))
        if picks:
            # Only claim the real model when it actually produced usable picks —
            # a "successful" call that came back empty/unparseable must not be
            # reported as if the model wrote this.
            model = settings.active_model_name
        else:
            ranked = sorted(slides, key=lambda s: s.data_score, reverse=True)[:8]
            picks = {s.index: "Information-dense slide." for s in ranked}
        chosen = [s for s in slides if s.index in picks]
        return StudyGuideResponse(
            document_id=document_id, kind=kind, title=title, model=model,
            key_slides=[
                SlidePreview(
                    index=s.index, title=s.title, bullets=list(s.bullets_json or []),
                    notes=picks.get(s.index), has_chart=s.has_chart, has_table=s.has_table,
                    importance=s.data_score,
                )
                for s in chosen
            ],
        )

    text = _doc_text(db, document_id)
    if not text.strip():
        raise ValueError("this material has no readable text")

    data: dict = {}
    if llm.provider_ready():
        try:
            data = llm.json_complete(_SYS[kind], f"Material: {doc.title}\n\n{text}", max_tokens=4500)
        except Exception as exc:  # pragma: no cover
            logger.warning("study_guide_failed", kind=kind, error=str(exc))
    if data:
        # Only claim the real model when it actually returned something usable
        # — a "successful" call whose JSON we couldn't parse must fall back to
        # the offline extract WITHOUT being reported as model-generated.
        model = settings.active_model_name
    else:
        data = _offline(kind, text, _TITLES[kind])

    resp = StudyGuideResponse(document_id=document_id, kind=kind, title=title, model=model)
    if kind == "flashcards":
        resp.flashcards = [
            Flashcard(front=str(c.get("front", "")), back=str(c.get("back", "")),
                      hint=(str(c["hint"]).strip() if c.get("hint") else None))
            for c in data.get("flashcards", []) if c.get("front") and c.get("back")
        ]
    elif kind == "concept_map":
        resp.concepts = [
            ConceptNode(
                id=str(n.get("id") or f"n{i}"), label=str(n.get("label", "")).strip(),
                parent=(str(n["parent"]) if n.get("parent") else None),
                note=(str(n["note"]).strip() if n.get("note") else None),
            )
            for i, n in enumerate(data.get("concepts", [])) if n.get("label")
        ]
    else:
        resp.markdown = str(data.get("markdown", "")).strip()
    return resp
