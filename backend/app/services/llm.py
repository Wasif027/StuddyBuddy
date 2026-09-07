"""Answer synthesis with grounded, structured output.

Providers
---------
``anthropic`` — ``claude-sonnet-5`` (default) via structured JSON output.
``openai``    — chat completions with a JSON schema response format.
``offline``   — deterministic extractive synthesis (no network, used in CI/dev).

Every provider returns the same :class:`Synthesis` shape: prose answer with
``[n]`` citation markers, a list of used markers with verbatim quotes, a
self-reported confidence and follow-up questions.
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


_SYSTEM = (
    "You are an enterprise knowledge assistant. Answer ONLY from the numbered "
    "context passages provided. Rules:\n"
    "1. Every factual sentence must cite its source with a bracketed marker like [1] or [2][3].\n"
    "2. If the passages do not contain the answer, say so plainly and set confidence low. Never guess.\n"
    "3. Be concise and specific. Prefer exact figures, dates, names and clauses from the passages.\n"
    "4. 'confidence' is your calibrated probability (0-1) that the answer is fully correct and grounded.\n"
    "5. 'citations' must quote the exact sentence(s) from the cited passage you relied on.\n"
    "6. 'followUps' are up to 3 natural next questions the user might ask."
)

_COMPARE_SYSTEM = (
    "You are an enterprise knowledge assistant comparing two or more documents. "
    "The numbered context passages are drawn from different documents (the title "
    "before each passage identifies which). Rules:\n"
    "1. Answer the question by explicitly CONTRASTING what each document says — "
    "state where they agree, where they differ, and what one adds that the other omits.\n"
    "2. Cite every claim with a bracketed marker like [1] or [2][3], and make clear "
    "which document each marker belongs to (use the passage titles).\n"
    "3. If a document is silent on a point, say so.\n"
    "4. 'confidence' is your calibrated probability (0-1) that the comparison is correct and grounded.\n"
    "5. 'citations' must quote the exact sentence(s) you relied on.\n"
    "6. 'followUps' are up to 3 natural next questions."
)

_DOCUMENT_SYSTEM = (
    "You are an enterprise knowledge assistant. The numbered context passages are "
    "the COMPLETE text of a single document, given in reading order. Rules:\n"
    "1. Produce a faithful, well-structured summary or answer covering the whole "
    "document — purpose, the key rules / figures / dates / obligations, and anything "
    "notable. Use short paragraphs or bullet points.\n"
    "2. Cite each point with a bracketed marker like [1] or [2][3] pointing at the "
    "passage it came from.\n"
    "3. Do NOT say the evidence is insufficient — the document itself is the evidence. "
    "If the document simply doesn't address something, don't mention it.\n"
    "4. 'confidence' is your calibrated probability (0-1) that the summary is faithful.\n"
    "5. 'citations' must quote the exact sentence(s) you relied on.\n"
    "6. 'followUps' are up to 3 natural next questions about this document."
)

_OVERVIEW_SYSTEM = (
    "You are an enterprise knowledge assistant. The numbered context passages are a "
    "BROAD SAMPLE drawn from several different documents in the knowledge base (the "
    "title before each passage identifies the document). Rules:\n"
    "1. Give a synthesising overview that answers the question across the documents. "
    "Group related points and name the documents they come from.\n"
    "2. Cite every claim with a bracketed marker like [1] or [2][3].\n"
    "3. Be clear about what the knowledge base does and does not cover. If the sample "
    "looks thin for the question, say so and lower confidence.\n"
    "4. 'confidence' is your calibrated probability (0-1) that the overview is correct.\n"
    "5. 'citations' must quote the exact sentence(s) you relied on.\n"
    "6. 'followUps' are up to 3 natural next questions."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marker": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["marker", "quote"],
                "additionalProperties": False,
            },
        },
        "followUps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "confidence", "citations", "followUps"],
    "additionalProperties": False,
}

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _prompt(question: str, passages: list[ContextPassage], history: str | None = None) -> str:
    blocks = [
        f"[{p.marker}] {p.title}" + (f" — {p.heading}" if p.heading else "") + f"\n{p.text}"
        for p in passages
    ]
    head = f"{history}\n\n" if history else ""
    return (
        head
        + f"Question: {question}\n\nContext passages:\n\n"
        + "\n\n---\n\n".join(blocks)
    )


# --------------------------------------------------------------------- offline
def _offline(
    question: str,
    passages: list[ContextPassage],
    mode: str = "pinpoint",
    *,
    degraded: bool = False,
) -> Synthesis:
    from app.services.reranker import _terms

    prefix = "_(the model is busy — this is a simpler extractive answer)_\n\n" if degraded else ""

    q_terms = set(_terms(question))

    if mode in ("document", "overview") and passages:
        # No model: stitch the opening sentence of each passage into an outline.
        picked = []
        for p in passages[: (12 if mode == "document" else 8)]:
            first = next((s.strip() for s in _SENT_RE.split(p.text) if s.strip()), p.text[:200].strip())
            picked.append(CitationUse(marker=p.marker, quote=first))
        body = " ".join(f"{c.quote} [{c.marker}]" for c in picked)
        lead = (
            f"Outline of {passages[0].title}:" if mode == "document"
            else "Across the knowledge base:"
        )
        return Synthesis(
            answer=f"{prefix}{lead} {body}",
            citations=picked,
            confidence=0.5,
            follow_ups=[f"What are the specifics in {passages[0].title}?"],
        )

    if not passages or (passages and passages[0].score < settings.min_evidence_score):
        return Synthesis(
            answer=(
                "I could not find enough relevant information in the knowledge base to answer "
                "this question confidently. Try rephrasing, widening the category filter, or "
                "ingesting a document that covers this topic."
            ),
            citations=[],
            confidence=0.12,
            follow_ups=[],
        )

    picked: list[tuple[int, str]] = []
    used_markers: list[CitationUse] = []
    for p in passages[:4]:
        best_sent, best_overlap = "", 0
        for sent in _SENT_RE.split(p.text):
            overlap = len(q_terms & set(_terms(sent)))
            if overlap > best_overlap:
                best_sent, best_overlap = sent.strip(), overlap
        sentence = best_sent or p.text[:240].strip()
        picked.append((p.marker, sentence))
        used_markers.append(CitationUse(marker=p.marker, quote=sentence))
        if len(picked) >= 2 and best_overlap == 0:
            break

    body = " ".join(f"{sent} [{marker}]" for marker, sent in picked if sent)
    answer = f"{prefix}Based on your documents: {body}"
    top = [p.score for p in passages[:3]]
    confidence = max(0.15, min(0.8, sum(top) / len(top))) if top else 0.15
    follow_ups = [
        f"What are the exceptions to this in {passages[0].title}?",
        "Which team or role owns this?",
    ]
    return Synthesis(answer=answer, citations=used_markers, confidence=round(confidence, 3), follow_ups=follow_ups)


# ------------------------------------------------------------------- anthropic
def _anthropic(question: str, passages: list[ContextPassage], system: str, history: str | None) -> Synthesis:  # pragma: no cover
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=[{"role": "user", "content": _prompt(question, passages, history)}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    usage = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
        "cache_read_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
    }
    return _from_payload(data, provider="anthropic", model=settings.anthropic_model, usage=usage)


# --------------------------------------------------------------------- openai
# Also handles any OpenAI-compatible endpoint (Groq, Gemini, Mistral, OpenRouter,
# Ollama, …) via OPENAI_BASE_URL. `json_object` mode is used because it is the
# most widely supported JSON mode across those providers; the schema lives in the
# system prompt.
_JSON_HINT = (
    '\n\nReturn ONLY a JSON object of this exact shape (no markdown fence):\n'
    '{"answer": string, "confidence": number 0-1, '
    '"citations": [{"marker": integer, "quote": string}], '
    '"followUps": [string]}'
)


def _openai(question: str, passages: list[ContextPassage], system: str, history: str | None) -> Synthesis:  # pragma: no cover
    from openai import OpenAI

    base_url = settings.openai_base_url or None
    # Fail fast to the offline fallback rather than hang if the provider is slow.
    client = OpenAI(
        api_key=settings.openai_api_key or "not-needed",
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    extra: dict = {}
    model = settings.openai_model
    # Many current models "reason" before answering, which can balloon latency on
    # a simple grounded-RAG turn. Ask for minimal reasoning where the provider
    # understands the hint (Gemini 2.5+/3, Groq gpt-oss/qwen, OpenAI o-series).
    if base_url and any(p in base_url for p in ("groq", "generativelanguage", "google")):
        extra["reasoning_effort"] = "low"
    resp = client.chat.completions.create(
        model=model,
        max_tokens=settings.llm_max_tokens,
        temperature=0.0,  # grounded RAG: same passages → same answer/verdict
        messages=[
            {"role": "system", "content": system + _JSON_HINT},
            {"role": "user", "content": _prompt(question, passages, history)},
        ],
        response_format={"type": "json_object"},
        **extra,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1] or "{}")
    usage = {
        "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        "cache_read_tokens": 0,
    }
    return _from_payload(data, provider="openai", model=settings.openai_model, usage=usage)


def _coerce_str(item: object) -> str:
    """Follow-ups sometimes come back as {'question': '...'} instead of a string."""
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
    )


def synthesize(
    question: str,
    passages: list[ContextPassage],
    *,
    compare: bool = False,
    mode: str = "pinpoint",
    history: str | None = None,
) -> Synthesis:
    if compare:
        system = _COMPARE_SYSTEM
    elif mode == "document":
        system = _DOCUMENT_SYSTEM
    elif mode == "overview":
        system = _OVERVIEW_SYSTEM
    else:
        system = _SYSTEM
    with _tracer.start_as_current_span("llm.synthesize") as span:
        span.set_attribute("provider", settings.llm_provider)
        span.set_attribute("passages", len(passages))
        span.set_attribute("compare", compare)
        span.set_attribute("mode", mode)
        try:
            if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
                return _anthropic(question, passages, system, history)
            if settings.llm_provider == "openai" and settings.openai_configured:
                return _openai(question, passages, system, history)
            degraded = False
        except Exception as exc:
            logger.warning("llm_synthesis_failed_falling_back", provider=settings.llm_provider, error=str(exc))
            span.record_exception(exc)
            degraded = True
        return _offline(question, passages, mode, degraded=degraded)


# ===================================================================== analysis
# Text-to-SQL over uploaded spreadsheet data + narration of the result table.


def provider_ready() -> bool:
    return (settings.llm_provider == "anthropic" and bool(settings.anthropic_api_key)) or (
        settings.llm_provider == "openai" and settings.openai_configured
    )


_CLASSIFY_SYSTEM = (
    "Classify what the user is asking for. One word:\n"
    "- analysis : they want a figure, table, ranking, share, count, total, average, "
    "trend or per-group breakdown computed FROM DATA (e.g. 'which product sells best', "
    "'what % is from the top channel', 'sales by month', 'anything at a loss'). "
    "Typos and loose phrasing are fine — judge the intent.\n"
    "- summary : they want an overview of a whole document or the whole knowledge base.\n"
    "- lookup : anything else — a specific fact, a policy detail, a how-to, a definition.\n"
    'Return ONLY JSON: {"kind": "analysis" | "summary" | "lookup"}'
)


def classify_query(question: str) -> str:
    """Cheap intent classifier — 'analysis' | 'summary' | 'lookup'.

    Used by the query planner only when the fast keyword heuristics are
    ambiguous, so it forgives typos and unusual phrasing. Falls back to
    'lookup' offline or on any error.
    """
    if not provider_ready():
        return "lookup"
    try:
        data = _json_complete(_CLASSIFY_SYSTEM, f"Question: {question}", max_tokens=30)
        kind = str(data.get("kind", "lookup")).strip().lower()
        return kind if kind in ("analysis", "summary", "lookup") else "lookup"
    except Exception as exc:  # pragma: no cover
        logger.warning("classify_query_failed", error=str(exc))
        return "lookup"


def _json_complete(system: str, user: str, *, max_tokens: int | None = None) -> dict:
    """One JSON-object completion via the configured provider. Raises on failure."""
    mt = max_tokens or settings.llm_max_tokens
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=mt,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return json.loads(text[text.find("{") : text.rfind("}") + 1] or "{}")

    from openai import OpenAI

    base_url = settings.openai_base_url or None
    client = OpenAI(
        api_key=settings.openai_api_key or "not-needed",
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    extra: dict = {}
    if base_url and any(p in base_url for p in ("groq", "generativelanguage", "google")):
        extra["reasoning_effort"] = "low"
    resp = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=mt,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        **extra,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw[raw.find("{") : raw.rfind("}") + 1] or "{}")


_SQL_SYSTEM = (
    "You translate a business question into ONE read-only DuckDB SQL query over the "
    "user's uploaded spreadsheet tables.\n"
    "Rules:\n"
    "1. Output a SINGLE statement beginning with SELECT or WITH. No semicolons, no DDL/DML, "
    "no PRAGMA/SET/ATTACH/COPY, no file functions (read_csv, etc.).\n"
    "2. Use only the tables and columns in the provided schema. You MAY JOIN tables.\n"
    "3. Column names with spaces or punctuation are already sanitised in the schema — use "
    "the identifiers shown.\n"
    "4. Prefer explicit aggregates, GROUP BY, ORDER BY and a sensible LIMIT. For "
    "'which X is most/least ...' return the row(s), not just the value.\n"
    "5. Derive metrics the question implies (e.g. profit = revenue - cost, margin = "
    "profit / revenue) inline. Cast text-numbers with TRY_CAST.\n"
    "6. If the question cannot be answered from the schema, set \"sql\" to \"\" and explain "
    "in \"assumptions\".\n"
    'Return ONLY JSON: {"sql": string, "assumptions": string} — "assumptions" states any '
    "column-meaning guesses or filters you applied."
)

_ANALYSIS_SYSTEM = (
    "You are a data analyst. You are given a business question, the SQL that was run over "
    "the user's spreadsheet(s), and the resulting rows. Optionally some passages from other "
    "documents are provided for context.\n"
    "Write a short, direct answer to the question grounded ONLY in the result rows (and the "
    "context passages if relevant). Quote concrete figures. If passages are used, cite them "
    "with [1], [2] markers matching their numbers. Do not invent numbers not present in the "
    "result.\n"
    'Return ONLY JSON: {"answer": string, "confidence": number 0-1, '
    '"citations": [{"marker": integer, "quote": string}], "followUps": [string]}'
)


def generate_sql(question: str, schema: str, *, history: str | None = None, prior_error: str | None = None) -> tuple[str, str]:
    """Return ``(sql, assumptions)``. ``sql`` is "" when the model declines."""
    parts = [f"Schema:\n{schema}"]
    if history:
        parts.append(history)
    if prior_error:
        parts.append(f"The previous query failed with: {prior_error}\nFix it.")
    parts.append(f"Question: {question}")
    data = _json_complete(_SQL_SYSTEM, "\n\n".join(parts), max_tokens=700)
    return str(data.get("sql", "")).strip(), str(data.get("assumptions", "")).strip()


def narrate_analysis(
    question: str,
    sql: str,
    columns: list[str],
    rows: list[list],
    *,
    context_passages: list[ContextPassage] | None = None,
) -> Synthesis:
    """Turn a result table into a grounded prose answer."""
    table_md = "| " + " | ".join(columns) + " |\n" + "| " + " | ".join("---" for _ in columns) + " |\n"
    table_md += "\n".join(
        "| " + " | ".join("" if c is None else str(c) for c in r) + " |" for r in rows[:50]
    )
    blocks = [f"Question: {question}", f"SQL:\n{sql}", f"Result ({len(rows)} rows):\n{table_md}"]
    if context_passages:
        ctx = "\n\n".join(
            f"[{p.marker}] {p.title}" + (f" — {p.heading}" if p.heading else "") + f"\n{p.text}"
            for p in context_passages
        )
        blocks.append(f"Context passages:\n{ctx}")
    try:
        data = _json_complete(_ANALYSIS_SYSTEM, "\n\n".join(blocks), max_tokens=900)
        return _from_payload(
            data, provider=settings.llm_provider, model=settings.active_model_name, usage={}
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("narrate_analysis_failed", error=str(exc))
        n = len(rows)
        summary = (
            f"The query returned {n} row{'s' if n != 1 else ''}. "
            + (f"First row: {dict(zip(columns, rows[0], strict=False))}." if rows else "")
        )
        return Synthesis(answer=summary, citations=[], confidence=0.4, follow_ups=[])


# =================================================================== suggestions
# After an answer, propose concrete next steps the user can accept / reject / mark
# done. Nothing is executed — these are recommendations.

_SUGGEST_SYSTEM = (
    "You are given a user's question, the answer they were just given, and the source "
    "passages it drew on. Propose the concrete NEXT STEPS the user could take now.\n"
    "Rules:\n"
    "1. 0 to 3 steps. Be conservative — only suggest a step when the answer clearly implies "
    "an action. A question that just asks for a fact, definition, number or policy detail "
    "('what is the refund window?', 'how much is shipping?') usually needs ZERO steps → "
    'return {"steps": []}.\n'
    "2. A step is warranted when the question describes a SITUATION to handle (a complaint, a "
    "loss-making product, low stock, a late order) — then propose what to do about it.\n"
    "3. Each step: a short imperative sentence (e.g. 'Email the customer offering a "
    "replacement', 'Flag the Amber candle for repricing'), plus a one-line reason grounded "
    "in the answer or passages. Do NOT restate the answer.\n"
    "4. priority is 'high' | 'medium' | 'low'. Steps are things a person does, not things "
    "you do.\n"
    "5. kind is 'explore' when the step can be answered right now purely from the uploaded "
    "documents / spreadsheets (e.g. 'Check which products are below reorder level', 'Review "
    "the refund rate by month') — or 'external' when it needs a person or another system "
    "(sending an email, changing a price in a shop, contacting a supplier).\n"
    'Return ONLY JSON: {"steps": [{"text": string, "rationale": string, "priority": string, '
    '"kind": "explore" | "external"}]}'
)

_ALT_SYSTEM = (
    "You previously proposed next steps for this question; the user rejected the ones listed "
    "below. Propose ONE different next step (same JSON shape, including 'kind'), or return null "
    "if there is no genuinely better or different option.\n"
    'Return ONLY JSON: {"step": {"text": string, "rationale": string, "priority": string, '
    '"kind": "explore" | "external"} | null}'
)


@dataclass
class SuggestedStep:
    text: str
    rationale: str
    priority: str = "medium"
    kind: str = "external"


def _coerce_step(d: object) -> SuggestedStep | None:
    if not isinstance(d, dict) or not str(d.get("text", "")).strip():
        return None
    pr = str(d.get("priority", "medium")).lower()
    kind = str(d.get("kind", "external")).lower()
    return SuggestedStep(
        text=str(d["text"]).strip(),
        rationale=str(d.get("rationale", "")).strip(),
        priority=pr if pr in ("high", "medium", "low") else "medium",
        kind="explore" if kind == "explore" else "external",
    )


def _answer_context(question: str, answer_text: str, passages: list[ContextPassage]) -> str:
    ctx = "\n\n".join(
        f"- {p.title}" + (f" ({p.heading})" if p.heading else "") + f": {p.text[:500]}"
        for p in passages[:5]
    )
    return f"Question: {question}\n\nAnswer given:\n{answer_text[:1500]}\n\nSource passages:\n{ctx}"


def suggest_actions(
    question: str, answer_text: str, passages: list[ContextPassage]
) -> list[SuggestedStep]:
    if not provider_ready():
        return []
    try:
        data = _json_complete(
            _SUGGEST_SYSTEM, _answer_context(question, answer_text, passages), max_tokens=600
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("suggest_actions_failed", error=str(exc))
        return []
    steps = [s for s in (_coerce_step(x) for x in data.get("steps", [])) if s]
    return steps[:3]


def suggest_alternative(
    question: str,
    answer_text: str,
    passages: list[ContextPassage],
    rejected: list[str],
) -> SuggestedStep | None:
    if not provider_ready():
        return None
    body = _answer_context(question, answer_text, passages) + "\n\nRejected steps:\n" + "\n".join(
        f"- {r}" for r in rejected
    )
    try:
        data = _json_complete(_ALT_SYSTEM, body, max_tokens=400)
    except Exception as exc:  # pragma: no cover
        logger.warning("suggest_alternative_failed", error=str(exc))
        return None
    return _coerce_step(data.get("step"))
