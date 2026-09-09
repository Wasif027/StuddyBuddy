"""Tutor answer synthesis + a shared JSON-completion helper.

Providers
---------
``anthropic`` — ``claude-sonnet-5`` via structured JSON output.
``openai``    — chat completions with a JSON response format (also covers any
                OpenAI-compatible endpoint: Gemini, Groq, Mistral, Ollama, …).
``offline``   — deterministic extractive synthesis (no network, used in CI/dev).

``synthesize`` returns a :class:`Synthesis`: a prose explanation with ``[n]``
citation markers into the numbered context passages, the markers actually used
(with verbatim quotes), a self-reported confidence and follow-up prompts.

``json_complete`` is the low-level "one JSON object out" call used by the
assessment / study-guide / vision services.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import tracer

logger = get_logger(__name__)
settings = get_settings()
_tracer = tracer(__name__)


@dataclass
class ContextPassage:
    marker: int
    chunk_id: str
    title: str
    heading: str | None
    text: str
    score: float


@dataclass
class CitationUse:
    marker: int
    quote: str


@dataclass
class Synthesis:
    answer: str
    citations: list[CitationUse]
    confidence: float
    follow_ups: list[str] = field(default_factory=list)
    provider: str = "offline"
    model: str = "offline-extractive"
    usage: dict = field(default_factory=dict)
    grounded: bool = True
    corrected: bool = False


# --------------------------------------------------------------------- prompts
_LEVEL_GUIDE = {
    "simple": "Explain in plain, everyday language a curious beginner would follow. "
    "Short sentences, one idea at a time, a concrete everyday analogy. Avoid jargon; "
    "if a technical term is unavoidable, define it in the same sentence.",
    "standard": "Explain clearly for a motivated student meeting this properly for the "
    "first time. Define terms as they come up, give a worked example, keep it tight.",
    "deep": "Give a thorough explanation: the mechanism and the why, edge cases, how it "
    "connects to neighbouring ideas, and a common misconception to avoid. Assume the "
    "student already knows the basics.",
    "exam": "Answer at the level and phrasing an examiner expects: precise definitions, "
    "the key steps or criteria that earn marks, correct notation, and a model answer "
    "structure. Note what a common answer gets wrong.",
}

_TUTOR_RULES = (
    "You are StudyBuddy, a patient, encouraging personal tutor.\n"
    "You have been given numbered passages from the student's OWN uploaded notes / "
    "slides / textbook pages. Ground your explanation in them and cite with bracketed "
    "markers like [1] or [2][3] on the sentences that use them.\n"
    "Rules:\n"
    "1. Teach — don't just quote. Explain in your own words, then point to the passage.\n"
    "2. If the passages don't fully cover the question you MAY add correct standard "
    "knowledge, but say briefly which part isn't from their materials, and lower "
    "'confidence'.\n"
    "3. If the passages are irrelevant or empty, still give a genuinely helpful answer "
    "from standard knowledge, set 'grounded' false and 'confidence' to how sure you are.\n"
    "4. Match the requested depth exactly (see the depth instruction in the prompt).\n"
    "5. 'confidence' is your calibrated probability (0-1) the explanation is correct.\n"
    "6. 'citations' quote the exact sentence(s) from the cited passage you used.\n"
    "7. 'followUps' are up to 3 natural next things the student might want "
    "(\"go deeper on X\", \"give me practice questions on Y\", \"explain Z more simply\").\n"
    "8. If a CONVERSATION CONTEXT block is present, it is the running state of THIS "
    "chat. Honour the student's course-specific definitions, notation, syllabus scope "
    "and conventions listed there. But stay authoritative on facts: if the context "
    "shows the student asserted something factually wrong, correct it kindly rather "
    "than adopting it. If new information in the context means an EARLIER answer in "
    "this chat was wrong or incomplete, open with a brief '↻ Correcting an earlier "
    "answer:' and give the fixed version, and set 'corrected' true. Only do this for a "
    "genuine conflict you're confident about — never invent a contradiction."
)

_COMPARE_RULES = (
    "You are StudyBuddy, a personal tutor. The numbered passages come from DIFFERENT "
    "materials (the title before each says which). Answer by contrasting what each one "
    "says — where they agree, where they differ, what one adds. Cite every claim with "
    "[n] markers and make clear which material each belongs to. Same JSON shape and "
    "depth rules as usual."
)

_DOCUMENT_RULES = (
    "You are StudyBuddy, a personal tutor. The numbered passages are the COMPLETE text "
    "of ONE of the student's materials, in reading order. Produce a faithful study "
    "summary: what it covers, the key ideas / definitions / formulae / dates, and "
    "anything an exam would test. Use short paragraphs or bullets, cite each point with "
    "[n]. Never say the evidence is insufficient — the document is the evidence. Set "
    "'grounded' true."
)

_OVERVIEW_RULES = (
    "You are StudyBuddy, a personal tutor. The numbered passages are a BROAD SAMPLE from "
    "several of the student's materials (the title before each says which). Give a "
    "synthesising overview that answers the question across them, grouping related "
    "points and naming their source. Cite with [n]. If the sample looks thin, say so "
    "and lower confidence."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "grounded": {"type": "boolean"},
        "corrected": {"type": "boolean"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"marker": {"type": "integer"}, "quote": {"type": "string"}},
                "required": ["marker", "quote"],
                "additionalProperties": False,
            },
        },
        "followUps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "confidence", "citations", "followUps"],
    "additionalProperties": False,
}

_JSON_HINT = (
    '\n\nReturn ONLY a JSON object of this exact shape (no markdown fence):\n'
    '{"answer": string, "confidence": number 0-1, "grounded": boolean, '
    '"corrected": boolean, '
    '"citations": [{"marker": integer, "quote": string}], "followUps": [string]}'
)

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _depth_instruction(level: str) -> str:
    return "Depth: " + _LEVEL_GUIDE.get(level, _LEVEL_GUIDE["standard"])


_STUDENT_LEVELS = {
    "year-8": "a Year 8 / middle-school student (~13 years old)",
    "middle-school": "a middle-school student (~13 years old)",
    "gcse": "a GCSE student (~15-16)",
    "high-school": "a high-school student",
    "a-level": "an A-level / senior high-school student (~17-18)",
    "ib": "an IB diploma student",
    "undergraduate": "a first- or second-year undergraduate",
    "bachelors": "an undergraduate",
}


def _prompt(
    question: str,
    passages: list[ContextPassage],
    *,
    level: str = "standard",
    student_level: str = "",
    history: str | None = None,
    conversation_context: str = "",
) -> str:
    blocks = [
        f"[{p.marker}] {p.title}" + (f" — {p.heading}" if p.heading else "") + f"\n{p.text}"
        for p in passages
    ]
    cc = f"CONVERSATION CONTEXT (running state of this chat):\n{conversation_context}\n\n" if conversation_context else ""
    head = f"{history}\n\n" if history else ""
    ctx = "\n\n---\n\n".join(blocks) if blocks else "(no passages retrieved from the student's materials)"
    who = _STUDENT_LEVELS.get(student_level, student_level)
    aud = f"The student is {who}. Pitch the content, examples and assumed background to that.\n" if who else ""
    return f"{cc}{head}{aud}{_depth_instruction(level)}\n\nQuestion: {question}\n\nContext passages:\n\n{ctx}"


# --------------------------------------------------------------------- offline
def _offline(
    question: str,
    passages: list[ContextPassage],
    mode: str = "pinpoint",
    *,
    level: str = "standard",
    student_level: str = "",
    degraded: bool = False,
) -> Synthesis:
    from app.services.reranker import _terms

    prefix = "_(the tutor model is busy — here's a simpler extract)_\n\n" if degraded else ""
    q_terms = set(_terms(question))

    if mode in ("document", "overview") and passages:
        picked = []
        for p in passages[: (12 if mode == "document" else 8)]:
            first = next((s.strip() for s in _SENT_RE.split(p.text) if s.strip()), p.text[:200].strip())
            picked.append(CitationUse(marker=p.marker, quote=first))
        body = " ".join(f"{c.quote} [{c.marker}]" for c in picked)
        lead = f"Study outline of {passages[0].title}:" if mode == "document" else "Across your materials:"
        return Synthesis(
            answer=f"{prefix}{lead} {body}",
            citations=picked,
            confidence=0.5,
            follow_ups=[f"Give me practice questions on {passages[0].title}"],
        )

    if not passages or passages[0].score < settings.min_evidence_score:
        return Synthesis(
            answer=(
                f"{prefix}I couldn't find this in your uploaded materials, and no tutor model is "
                "configured to explain it from general knowledge. Try rephrasing, or upload a "
                "note or slide that covers it."
            ),
            citations=[],
            confidence=0.12,
            follow_ups=[],
            grounded=False,
        )

    picked: list[tuple[int, str]] = []
    used: list[CitationUse] = []
    for p in passages[:4]:
        best_sent, best_overlap = "", 0
        for sent in _SENT_RE.split(p.text):
            overlap = len(q_terms & set(_terms(sent)))
            if overlap > best_overlap:
                best_sent, best_overlap = sent.strip(), overlap
        sentence = best_sent or p.text[:240].strip()
        picked.append((p.marker, sentence))
        used.append(CitationUse(marker=p.marker, quote=sentence))
        if len(picked) >= 2 and best_overlap == 0:
            break

    body = " ".join(f"{sent} [{marker}]" for marker, sent in picked if sent)
    top = [p.score for p in passages[:3]]
    confidence = max(0.15, min(0.8, sum(top) / len(top))) if top else 0.15
    return Synthesis(
        answer=f"{prefix}From your materials: {body}",
        citations=used,
        confidence=round(confidence, 3),
        follow_ups=["Explain this more simply", "Give me practice questions on this"],
    )


# ------------------------------------------------------------------- providers
def _anthropic(question, passages, system, level, student_level, history, cc) -> Synthesis:  # pragma: no cover
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=[{"role": "user", "content": _prompt(
            question, passages, level=level, student_level=student_level,
            history=history, conversation_context=cc)}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = _loads(text)
    usage = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
        "cache_read_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
    }
    return _from_payload(data, provider="anthropic", model=settings.anthropic_model, usage=usage)


def _reasoning_kwargs(base_url: str | None, *, want_thinking: bool) -> dict:
    """Provider-specific reasoning knobs.

    Gemini's *-flash-lite models are non-thinking and 400 on ``reasoning_effort``;
    the full flash/pro models think by default. So for Gemini we send nothing and
    pick the model per path (``HARD_MODEL`` for the reasoning-heavy work). Groq's
    gpt-oss / qwen models take a hint.
    """
    if not base_url:
        return {}
    if "groq" in base_url:
        return {"reasoning_effort": "low"}
    return {}


def _json_content(resp) -> str:
    """Extract the message content, raising if the model returned nothing
    (a thinking model that spent its whole budget reasoning)."""
    msg = resp.choices[0].message
    raw = (msg.content or "").strip()
    if not raw:
        fr = getattr(resp.choices[0], "finish_reason", "?")
        raise RuntimeError(
            f"model returned an empty message (finish_reason={fr}) — likely a "
            "'thinking' model that used its token budget on hidden reasoning. "
            "Try a non-thinking model (e.g. gemini-3.5-flash-lite) or raise LLM_MAX_TOKENS."
        )
    return raw


_BAD_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])')


def _loads(raw: str) -> dict:
    """Parse a JSON object out of a model response, tolerating the usual sins:
    surrounding prose / fences, and invalid backslash escapes (models love to
    emit ``\\(`` / ``\\,`` from LaTeX-ish content)."""
    span = raw[raw.find("{") : raw.rfind("}") + 1] or "{}"
    for candidate in (span, _BAD_ESCAPE_RE.sub(r"\\\\", span)):
        try:
            out = json.loads(candidate)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            continue
    logger.warning("json_parse_failed", head=span[:200])
    return {}


def _openai(question, passages, system, level, student_level, history, cc) -> Synthesis:  # pragma: no cover
    from openai import OpenAI

    base_url = settings.openai_base_url or None
    client = OpenAI(
        api_key=settings.openai_api_key or "not-needed",
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.llm_max_tokens,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system + _JSON_HINT},
            {"role": "user", "content": _prompt(
                question, passages, level=level, student_level=student_level,
                history=history, conversation_context=cc)},
        ],
        response_format={"type": "json_object"},
        **_reasoning_kwargs(base_url, want_thinking=False),
    )
    data = _loads(_json_content(resp))
    usage = {
        "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        "cache_read_tokens": 0,
    }
    return _from_payload(data, provider="openai", model=settings.openai_model, usage=usage)


def _coerce_str(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("question", "text", "value", "followUp", "follow_up"):
            if isinstance(item.get(key), str):
                return item[key].strip()
        return next((v.strip() for v in item.values() if isinstance(v, str)), "")
    return str(item).strip()


def _from_payload(data: dict, *, provider: str, model: str, usage: dict) -> Synthesis:
    cites: list[CitationUse] = []
    for c in data.get("citations", []):
        if isinstance(c, dict) and "marker" in c:
            try:
                cites.append(CitationUse(marker=int(c["marker"]), quote=str(c.get("quote", "")).strip()))
            except (TypeError, ValueError):
                continue
    conf = float(data.get("confidence", 0.5) or 0.5)
    follow_ups = [s for s in (_coerce_str(f) for f in data.get("followUps", [])) if s][:3]
    return Synthesis(
        answer=str(data.get("answer", "")).strip(),
        citations=cites,
        confidence=max(0.0, min(1.0, conf)),
        follow_ups=follow_ups,
        provider=provider,
        model=model,
        usage=usage,
        grounded=bool(data.get("grounded", True)),
        corrected=bool(data.get("corrected", False)),
    )


def provider_ready() -> bool:
    return (settings.llm_provider == "anthropic" and bool(settings.anthropic_api_key)) or (
        settings.llm_provider == "openai" and settings.openai_configured
    )


def synthesize(
    question: str,
    passages: list[ContextPassage],
    *,
    compare: bool = False,
    mode: str = "pinpoint",
    level: str = "standard",
    student_level: str = "",
    history: str | None = None,
    conversation_context: str = "",
) -> Synthesis:
    if compare:
        system = _COMPARE_RULES
    elif mode == "document":
        system = _DOCUMENT_RULES
    elif mode == "overview":
        system = _OVERVIEW_RULES
    else:
        system = _TUTOR_RULES
    with _tracer.start_as_current_span("llm.synthesize") as span:
        span.set_attribute("provider", settings.llm_provider)
        span.set_attribute("passages", len(passages))
        span.set_attribute("mode", mode)
        span.set_attribute("level", level)
        try:
            if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
                return _anthropic(question, passages, system, level, student_level, history, conversation_context)
            if settings.llm_provider == "openai" and settings.openai_configured:
                return _openai(question, passages, system, level, student_level, history, conversation_context)
            degraded = False
        except Exception as exc:
            logger.warning("llm_synthesis_failed_falling_back", provider=settings.llm_provider, error=str(exc))
            span.record_exception(exc)
            degraded = True
        return _offline(question, passages, mode, level=level, student_level=student_level, degraded=degraded)


# ------------------------------------------------------ shared JSON completion
def json_complete(
    system: str,
    user: str,
    *,
    max_tokens: int | None = None,
    hard: bool = False,
    images: list[str] | None = None,
) -> dict:
    """One JSON-object completion via the configured provider. Raises on failure.

    ``hard`` routes to ``settings.hard_model`` (stronger reasoning) when set.
    ``images`` is a list of ``data:`` URIs to attach (vision) — OpenAI-compatible
    endpoints only.
    """
    mt = max_tokens or settings.llm_max_tokens
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        content: list[dict] = [{"type": "text", "text": user}]
        for uri in images or []:
            if uri.startswith("data:") and ";base64," in uri:
                meta, b64 = uri.split(";base64,", 1)
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": meta[5:], "data": b64},
                })
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=mt,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return _loads(text)

    from openai import OpenAI

    base_url = settings.openai_base_url or None
    client = OpenAI(
        api_key=settings.openai_api_key or "not-needed",
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    user_content: object = user
    if images:
        user_content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": uri}} for uri in images
        ]
    model = (settings.hard_model or settings.openai_model) if hard else settings.openai_model
    resp = client.chat.completions.create(
        model=model,
        max_tokens=mt,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        **_reasoning_kwargs(base_url, want_thinking=hard),
    )
    return _loads(_json_content(resp))


# Back-compat alias (older imports).
_json_complete = json_complete


# ------------------------------------------------ conversation working memory
_CONTEXT_SYSTEM = (
    "You maintain a compact running memory for one tutoring chat. Given the current "
    "memory, the latest question and the tutor's answer, return the UPDATED memory.\n"
    "Keep it small and factual:\n"
    "- topics: 1-4 short phrases naming what this chat is about\n"
    "- established: facts / definitions / notation the tutor and student are working "
    "with. Each: {fact, source: 'student'|'material'|'standard', verified: bool}. "
    "Mark verified=false for a student claim you can't confirm; verified=true for "
    "standard knowledge or something the tutor stated. Keep at most ~8, most recent / "
    "most load-bearing.\n"
    "- student_claims: things the student asserted that look WRONG or dubious — "
    "{claim, issue}. The tutor should correct these, not adopt them.\n"
    "- corrections: {was, now} for any point the tutor has since corrected in this chat.\n"
    "- observed_level: your read on the student's level if it's clearer than stated, else null.\n"
    "- misconceptions: short phrases for confusions the student has shown.\n"
    "- summary: 1-2 sentences a tutor could read to get back up to speed.\n"
    "Do NOT invent facts. Prefer removing stale entries over letting it grow.\n"
    'Return ONLY JSON with exactly those keys.'
)


def update_conversation_context(
    prev: dict, question: str, answer: str, passages: list[ContextPassage] | None = None
) -> dict:
    """Refresh a chat's working memory after a turn. Falls back to ``prev`` offline / on error."""
    if not provider_ready():
        return prev or {}
    src = ""
    if passages:
        src = "\n\nMaterials in play:\n" + "\n".join(f"- {p.title}: {p.text[:300]}" for p in passages[:4])
    body = (
        f"Current memory:\n{json.dumps(prev or {}, ensure_ascii=False)}\n\n"
        f"Latest question: {question}\n\nTutor's answer:\n{answer[:2500]}{src}"
    )
    try:
        data = json_complete(_CONTEXT_SYSTEM, body, max_tokens=900)
    except Exception as exc:  # pragma: no cover - network
        logger.warning("context_update_failed", error=str(exc))
        return prev or {}
    if not isinstance(data, dict):
        return prev or {}
    keep = ("topics", "established", "student_claims", "corrections", "observed_level",
            "misconceptions", "summary")
    return {k: data[k] for k in keep if k in data}


def render_context(ctx: dict) -> str:
    """Render a chat's working memory for injection into a generation prompt."""
    if not ctx:
        return ""
    lines: list[str] = []
    if ctx.get("summary"):
        lines.append(str(ctx["summary"]))
    if ctx.get("topics"):
        lines.append("Topics: " + ", ".join(str(t) for t in ctx["topics"]))
    for e in ctx.get("established", [])[:8]:
        if isinstance(e, dict) and e.get("fact"):
            tag = str(e.get("source", "")) + ("" if e.get("verified", True) else ", UNVERIFIED student claim")
            lines.append(f"- {e['fact']}" + (f"  ({tag})" if tag.strip(", ") else ""))
    for c in ctx.get("student_claims", [])[:4]:
        if isinstance(c, dict) and c.get("claim"):
            lines.append(f"- Student claimed (likely wrong — correct it): {c['claim']} — {c.get('issue', '')}")
    for c in ctx.get("corrections", [])[:4]:
        if isinstance(c, dict) and c.get("now"):
            lines.append(f"- Already corrected earlier: was \"{c.get('was', '')}\", now \"{c['now']}\"")
    if ctx.get("misconceptions"):
        lines.append("Watch for these confusions: " + "; ".join(str(m) for m in ctx["misconceptions"]))
    return "\n".join(lines).strip()
