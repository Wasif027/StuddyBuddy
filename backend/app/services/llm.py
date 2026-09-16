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
import math
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.request_context import get_user_llm_key
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
    chart: dict | None = None


# --------------------------------------------------------------------- prompts
# Each level is written as a concrete, mechanically-followable spec — a rough
# length band plus a required shape — not just a vibe. A vague style note like
# "explain simply" barely moves a fast model's output; a length + structure
# constraint reliably does, and it's what actually makes the four depths read
# as obviously different answers rather than the same paragraph reworded.
_LEVEL_GUIDE = {
    "simple": (
        "SIMPLE MODE. Target ~70-120 words. ONE idea only — the single most "
        "important thing to know, nothing else. Exactly one everyday analogy "
        "(kitchens, sports, money, weather — not another technical idea). Short "
        "sentences. Zero jargon: if a technical word is truly unavoidable, put "
        "the plain-English meaning in brackets right next to it. No formulas, "
        "no multi-step derivations, no 'edge cases'. Write like you're talking "
        "to a curious 10-year-old, not writing a textbook paragraph in simpler "
        "words."
    ),
    "standard": (
        "STANDARD MODE. Target ~150-250 words. Structure: (1) a one-sentence "
        "plain definition, (2) how it works in 2-4 sentences, (3) exactly one "
        "worked example or concrete instance. Define each technical term the "
        "first time you use it, in the same sentence. No tangents, no 'common "
        "misconceptions' section, no exam-style breakdown — that's other modes."
    ),
    "deep": (
        "DEEP MODE. Target 350-550+ words, several short paragraphs or headed "
        "sections. Assume the student already has the basics — do NOT redefine "
        "them from scratch. Must include ALL of: the underlying mechanism and "
        "WHY it works that way (not just what), at least one edge case or "
        "limit where the simple picture breaks down, how it connects to at "
        "least one neighbouring concept, and one specific misconception named "
        "and corrected ('a common mistake is to think X, but actually Y'). If "
        "the topic is quantitative, include the general formula and briefly "
        "why it takes that form."
    ),
    "exam": (
        "EXAM MODE. Write like a revision note / mark scheme, not a "
        "conversation — no 'Hello!', no encouragement, no chit-chat. Structure, "
        "in order: a precise one-line definition using correct technical "
        "vocabulary and notation; a short bulleted list of the specific points "
        "a mark scheme would award credit for; a compact model-answer example "
        "using that exact vocabulary; then one line naming what a typical "
        "answer gets wrong or leaves out. Terse throughout — every sentence "
        "should be something worth writing down."
    ),
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

_GENERAL_RULES = (
    "You are StudyBuddy, a patient, encouraging personal tutor.\n"
    "The student has NOT attached any of their own notes or materials for this "
    "question. That is fine — teach the topic yourself, fully and confidently, from "
    "standard knowledge. Give a real, complete explanation: define the idea, explain "
    "how it works in your own words, and add a concrete example or two. Do NOT tell "
    "the student to upload anything and do NOT refuse or hedge about missing "
    "materials — a solid textbook explanation is exactly what is wanted.\n"
    "Rules:\n"
    "1. Match the requested depth exactly (see the depth instruction in the prompt) "
    "and pitch it to the student's level.\n"
    "2. 'grounded' is false and 'citations' is [] — there is nothing to cite.\n"
    "3. 'confidence' is your calibrated probability (0-1) the explanation is correct. "
    "For standard curriculum topics this should be high (0.85-0.95); lower it only "
    "for genuinely uncertain or contested points.\n"
    "4. 'followUps' are up to 3 natural next steps (\"go deeper on X\", \"practice "
    "questions on Y\", \"explain Z more simply\").\n"
    "5. If a CONVERSATION CONTEXT block is present, honour the student's "
    "course-specific definitions, notation and syllabus scope. Stay authoritative on "
    "facts: correct a wrong student assertion kindly rather than adopting it. If new "
    "information means an EARLIER answer in this chat was wrong, open with a brief "
    "'↻ Correcting an earlier answer:' and set 'corrected' true — only for a genuine "
    "conflict, never an invented one."
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
        "chart": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string", "enum": ["line", "bar", "scatter"]},
                "title": {"type": "string"},
                "xLabel": {"type": "string"},
                "yLabel": {"type": "string"},
                "series": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                                    "required": ["x", "y"],
                                },
                            },
                        },
                        "required": ["points"],
                    },
                },
            },
        },
    },
    "required": ["answer", "confidence", "citations", "followUps"],
    "additionalProperties": False,
}

_JSON_HINT = (
    '\n\nReturn ONLY a JSON object of this exact shape (no markdown fence):\n'
    '{"answer": string, "confidence": number 0-1, "grounded": boolean, '
    '"corrected": boolean, '
    '"citations": [{"marker": integer, "quote": string}], "followUps": [string], '
    '"chart": {"type": "line"|"bar"|"scatter", "title": string, "xLabel": string, '
    '"yLabel": string, "series": [{"name": string, "points": [{"x": number, "y": number}]}]} '
    'or null}'
)

_CHART_NOTE = (
    "If (and only if) the student asks you to plot, graph, sketch, or visually show a "
    "function or a set of data, COMPUTE real (x, y) data points yourself (15-40 points, "
    "evenly spread across a sensible range — infer one if not given) and put them in the "
    "'chart' field ('line' for a continuous function, 'scatter' for discrete data, 'bar' "
    "for categorical comparisons). Still describe the shape/key features in 'answer' too — "
    "the chart is a supplement, not a replacement. Otherwise set 'chart' to null."
)

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _first_substantive_sentence(text: str, title: str) -> str:
    """First sentence of a passage that isn't just a bare repeat of its own
    title — a chunk commonly starts with its own heading line ("Cell biology
    notes.", "Chapter 3.") which otherwise makes the offline extractive
    fallback read as an inane "Study outline of X: X.\""""
    title_norm = title.strip().rstrip(".").lower()
    sentences = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
    for s in sentences:
        if s.rstrip(".").lower() != title_norm:
            return s
    return sentences[0] if sentences else text[:200].strip()

_MATH_NOTE = (
    "Write any mathematical or scientific notation in LaTeX — $...$ for inline "
    "(e.g. $F = ma$, $x^2$, $\\frac{a}{b}$) and $$...$$ for a display equation. "
    "It is rendered for the student."
)


def _depth_instruction(level: str) -> str:
    return "REQUIRED DEPTH — follow this exactly, it must be obviously different from the other modes:\n" + _LEVEL_GUIDE.get(
        level, _LEVEL_GUIDE["standard"]
    )


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
    who = _STUDENT_LEVELS.get(student_level, student_level)
    aud = f"The student is {who}. Pitch the content, examples and assumed background to that.\n" if who else ""
    lead = f"{cc}{head}{aud}{_depth_instruction(level)}\n{_MATH_NOTE}\n{_CHART_NOTE}\n\nQuestion: {question}"
    if not blocks:
        # Nothing retrieved — a plain general-knowledge question. Don't mention
        # "passages" at all; weak models fixate on the emptiness and hedge.
        return f"{lead}\n\nAnswer it directly and completely from standard knowledge."
    ctx = "\n\n---\n\n".join(blocks)
    return f"{lead}\n\nContext passages:\n\n{ctx}"


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
            first = _first_substantive_sentence(p.text, p.title)
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
        msg = (
            "The tutor model is briefly unavailable, so I can't give a full explanation "
            "right now — try again in a moment."
            if degraded
            else "I couldn't find this in your uploaded materials, and no tutor model is "
            "configured to explain it from general knowledge. Try rephrasing, or upload a "
            "note or slide that covers it."
        )
        return Synthesis(
            answer=f"{prefix}{msg}",
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

# \t \f \r \b are all valid JSON escapes (tab / form-feed / CR / backspace) — so
# a model writing unescaped LaTeX like "$8\text{GB}$" or "\frac{1}{2}" produces
# JSON that PARSES FINE but silently decodes "\t"/"\f" into a literal control
# character, eating the rest of the command name (`ext{GB}`, `rac{1}{2}`) as
# plain text. No exception is raised, so the usual "retry on parse failure"
# fallbacks never even run. A tutor answer has no legitimate use for a raw
# tab/form-feed/CR/backspace, so treat one immediately followed by a letter as
# a mis-escaped LaTeX command and double the backslash before parsing. `\n` is
# deliberately left alone — real newlines for paragraph breaks are common and
# legitimate, and the ambiguity there is real (unlike t/f/r/b).
_AMBIGUOUS_JSON_ESCAPE = frozenset("tfrb")


def _fix_ambiguous_json_escapes(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    in_str = False
    while i < n:
        ch = s[i]
        if not in_str:
            out.append(ch)
            in_str = ch == '"'
            i += 1
            continue
        if ch == '"':
            in_str = False
            out.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt in _AMBIGUOUS_JSON_ESCAPE and i + 2 < n and s[i + 2].isalpha():
                out.append("\\\\")
                out.append(nxt)
            else:
                out.append(ch)
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _repair_json(s: str) -> str:
    """Best-effort close of a JSON object/array the model left truncated (it hit
    its token cap mid-structure). Walks the text tracking string state and the
    bracket stack, cuts back to the last point where a container element was
    cleanly finished, and appends the closers open at that point."""
    stack: list[str] = []
    in_str = esc = False
    last_safe = 0
    safe_stack: list[str] = []
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            last_safe, safe_stack = i + 1, list(stack)
        elif ch == "," and stack[-1:] == ["]"]:
            last_safe, safe_stack = i, list(stack)  # after a finished array element
    if in_str:
        # Cut off mid-string (the common case: a long "answer" value ran out of
        # tokens). Close the string as-is and every currently-open container —
        # a partial answer beats losing the whole response.
        tail = s[:-1] if esc else s  # a dangling trailing backslash would escape our closing quote
        return tail + '"' + "".join(reversed(stack))
    if not stack or last_safe == 0:
        return s
    head = s[:last_safe].rstrip().rstrip(",")
    return head + "".join(reversed(safe_stack))


def _loads(raw: str) -> dict:
    """Parse a JSON object out of a model response, tolerating the usual sins:
    surrounding prose / fences, invalid backslash escapes (models love to emit
    ``\\(`` / ``\\,`` from LaTeX-ish content), and truncation at the token cap."""
    start = raw.find("{")
    if start < 0:
        logger.warning("json_parse_failed", head=raw[:200])
        return {}
    span = _fix_ambiguous_json_escapes(raw[start : raw.rfind("}") + 1] or "{}")
    tail = _fix_ambiguous_json_escapes(raw[start:])
    fixed = _BAD_ESCAPE_RE.sub(r"\\\\", tail)
    for candidate in (span, _BAD_ESCAPE_RE.sub(r"\\\\", span), _repair_json(fixed)):
        try:
            out = json.loads(candidate)
            if isinstance(out, dict):
                return out
        except (json.JSONDecodeError, ValueError):
            continue
    logger.warning("json_parse_failed", head=span[:200])
    return {}


def _openai(question, passages, system, level, student_level, history, cc) -> Synthesis:  # pragma: no cover
    from openai import OpenAI

    base_url = settings.openai_base_url or None
    client = OpenAI(
        api_key=get_user_llm_key() or settings.openai_api_key or "not-needed",
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


def _coerce_chart(raw: object) -> dict | None:
    """Validate a model-proposed chart spec loosely — drop it rather than error
    if it's malformed; a missing chart is fine, a broken one is not."""
    if not isinstance(raw, dict):
        return None
    series_out = []
    for s in raw.get("series", []) if isinstance(raw.get("series"), list) else []:
        if not isinstance(s, dict):
            continue
        points = []
        for p in s.get("points", []) if isinstance(s.get("points"), list) else []:
            if not isinstance(p, dict):
                continue
            try:
                x, y = float(p["x"]), float(p["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(y):
                points.append({"x": x, "y": y})
        if points:
            series_out.append({"name": str(s.get("name", "")).strip(), "points": points})
    if not series_out:
        return None
    chart_type = str(raw.get("type", "line")).strip().lower()
    if chart_type not in ("line", "bar", "scatter"):
        chart_type = "line"
    return {
        "type": chart_type,
        "title": str(raw.get("title", "")).strip(),
        "xLabel": str(raw.get("xLabel", "")).strip(),
        "yLabel": str(raw.get("yLabel", "")).strip(),
        "series": series_out,
    }


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
        chart=_coerce_chart(data.get("chart")),
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
    elif not passages:
        system = _GENERAL_RULES
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

    user_content: object = user
    if images:
        user_content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": uri}} for uri in images
        ]

    def _call(api_key: str, base_url: str | None, model: str, *, want_thinking: bool) -> dict:
        client = OpenAI(
            api_key=api_key, base_url=base_url or None,
            timeout=settings.llm_timeout_seconds, max_retries=1,
        )
        resp = client.chat.completions.create(
            model=model, max_tokens=mt, temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            **_reasoning_kwargs(base_url, want_thinking=want_thinking),
        )
        return _loads(_json_content(resp))

    if images:
        api_key, base_url, model = settings.vision_llm()
        return _call(api_key, base_url, model, want_thinking=False)
    if hard:
        api_key, base_url, model = settings.hard_llm()
        # A dedicated HARD_* endpoint (e.g. a free Groq tier) can hit its own
        # rate/quota limit independently of the main provider — degrade to the
        # everyday model rather than falling all the way to offline templates.
        if base_url != (settings.openai_base_url or None):
            try:
                return _call(api_key, base_url, model, want_thinking=True)
            except Exception as exc:
                logger.warning("hard_model_failed_falling_back_to_default", error=str(exc))
        else:
            return _call(api_key, base_url, model, want_thinking=True)
    return _call(
        get_user_llm_key() or settings.openai_api_key or "not-needed", settings.openai_base_url or None,
        settings.openai_model, want_thinking=False,
    )


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


_CLASSIFY_SYSTEM = (
    "You are looking at the title and an excerpt of a document a student uploaded. "
    "Guess the single school/university subject it belongs to, lowercase, one or two "
    'words (e.g. "biology", "computer science", "business studies"). If you genuinely '
    'can\'t tell, return "".\n\nReturn ONLY JSON: {"subject": string}'
)


def classify_document_subject(title: str, text: str, existing_subjects: list[str] | None = None) -> str:
    """Best-effort subject guess for a document upload (PDF/DOCX/PPTX), mirroring
    what vision.describe_image already does for photos. Never raises — an empty
    string just means the document falls back to uncategorised, same as before
    this existed.

    ``existing_subjects`` (the student's own category labels) steers the model
    to reuse one of those verbatim instead of coining a near-duplicate — e.g.
    "business studies" as a fresh category when "Business Studies" already
    exists, which would silently split one subject into two in every view
    that groups by category."""
    if not provider_ready():
        return ""
    hint = (
        f"\n\nThe student's existing subjects: {', '.join(existing_subjects)}. "
        "If this document matches one of those, return that exact name. "
        "Otherwise suggest a new short subject name."
        if existing_subjects else ""
    )
    try:
        data = json_complete(
            _CLASSIFY_SYSTEM, f"Title: {title}\n\nExcerpt:\n{text[:1500]}{hint}", max_tokens=60
        )
    except Exception as exc:
        logger.warning("classify_document_subject_failed", error=str(exc), title=title[:60])
        return ""
    subject = str(data.get("subject", "")).strip().lower()
    return subject[:40]
