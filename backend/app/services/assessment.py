"""Practice-question generation + grading.

A practice set is always the same shape — 4 easy, 4 medium, 2 hard, 1 brutal —
pitched at the student's level and, where possible, grounded in their uploaded
materials. Grading is deterministic for MCQ / true-false / clean numeric answers
and model-graded (with partial credit + feedback) for free text.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.orm import (
    Attempt,
    Conversation,
    Document,
    Message,
    PracticeSet,
    Question,
    QuestionTier,
    QuestionType,
    ReviewItem,
    User,
)
from app.services import llm
from app.services.embeddings import embed_text
from app.services.sm2 import quality_from_score, schedule
from app.services.vectorstore import Scope, fetch_document_chunks, hybrid_search

logger = get_logger(__name__)
settings = get_settings()

_TIERS = settings.practice_tier_counts  # {"easy":4,"medium":4,"hard":2,"brutal":1}
_TOTAL = sum(_TIERS.values())
_VALID_TYPES = {t.value for t in QuestionType}


_GEN_SYSTEM = (
    "You are StudyBuddy's question setter. Produce a practice set that tests genuine "
    "understanding of the topic, pitched EXACTLY at the stated student level — not harder, "
    "not easier.\n\n"
    f"Return EXACTLY {_TOTAL} questions with this tier mix:\n"
    f"- {_TIERS['easy']} \"easy\": recall, definitions, one-step application\n"
    f"- {_TIERS['medium']} \"medium\": multi-step application, 'explain why', short compare\n"
    f"- {_TIERS['hard']} \"hard\": synthesis across sub-topics, non-obvious application, spot-the-flaw\n"
    f"- {_TIERS['brutal']} \"brutal\": one question only a student with deep, connected "
    "understanding can answer — multi-part, reason from first principles\n\n"
    "Each question object:\n"
    "- tier: easy|medium|hard|brutal\n"
    "- qtype: mcq | short | numeric | true_false | explain. Use mcq for roughly half the "
    "easy/medium questions; use explain for most hard/brutal; use numeric when the subject "
    "is quantitative.\n"
    "- prompt: the question text. Self-contained.\n"
    "- options: for mcq an array of 3-5 answer choices (exactly one correct); for true_false "
    "[\"True\", \"False\"]; otherwise [].\n"
    "- answer: the answer key. mcq/true_false → the exact correct option text. numeric → the "
    "number with its unit. short → the expected answer. explain → a concise model answer.\n"
    "- answer_mode: \"text\" or \"text_or_upload\". Use \"text_or_upload\" when a good answer "
    "involves showing working — a derivation or proof, a multi-step calculation, a diagram or "
    "sketch, algebra the student would normally do on paper. Use \"text\" for pure theory, "
    "recall, definitions, compare/contrast, mcq and true_false.\n"
    "- rubric: what a FULL-CREDIT answer needs FROM A STUDENT AT THIS EXACT LEVEL — 1-3 "
    "sentences, with the mark breakdown for 'explain'. A Year-8 answer and an undergraduate "
    "answer to the same topic are marked to very different bars; write the rubric for the "
    "stated level, not the hardest possible answer.\n"
    "- skill: a 2-4 word sub-skill this tests (e.g. 'balancing equations', 'osmosis "
    "direction') — used to track weak areas.\n\n"
    "Ground the questions in the CONTEXT passages when they're relevant; otherwise use "
    "standard curriculum knowledge for the stated level. Vary the sub-skills across the set.\n"
    "Write any maths/science notation in LaTeX ($...$ inline, $$...$$ display) — it is "
    "rendered for the student.\n"
    'Return ONLY JSON: {"questions": [ ... ]}'
)

_GRADE_SYSTEM = (
    "You are marking one exam answer. You are given the student's LEVEL, the question, the "
    "answer key, the marking rubric, and the student's answer. The answer may have been "
    "transcribed from a photo of handwritten working — if so, judge the reasoning and the "
    "maths, not transcription noise or spelling.\n\n"
    "Mark to the bar for the STATED LEVEL — the rubric is written for that level. An answer "
    "that meets the level's expectations is full marks even if a specialist could say more; "
    "an answer below the level's expectations is not.\n\n"
    "Return:\n"
    "- score: 0.0-1.0. Partial credit generously for partially-right answers; 0 for wrong, "
    "empty, or 'I don't know'.\n"
    "- correct: true if score >= 0.6\n"
    "- verdict: \"correct\" | \"partial\" | \"incorrect\"\n"
    "- feedback: 2-4 sentences to the student ('you…'). If not fully correct, name the "
    "SPECIFIC problem — which step is wrong, which term/case/step is missing, which "
    "misconception is showing — not just 'review this'. For a theory answer, say exactly "
    "which required point was absent or misstated. Encouraging but precise.\n"
    'Return ONLY JSON: {"score": number, "correct": boolean, "verdict": string, "feedback": string}'
)


# --------------------------------------------------------------- context
def _gather_context(
    db: Session,
    user: User,
    *,
    topic: str | None,
    document_id: str | None,
    conversation_id: str | None,
    category: str | None,
    note_context: str | None = None,
) -> tuple[str, str, str | None]:
    """Return (resolved_topic, context_text, source)."""
    if document_id:
        doc = db.get(Document, document_id)
        if not doc or doc.user_id != user.id:
            raise ValueError("document not found")
        scope = Scope(user_id=user.id, document_ids=[document_id])
        chunks = fetch_document_chunks(db, document_id, scope, 30)
        ctx = "\n\n".join(c.chunk.text for c in chunks)[:12000]
        return (topic or doc.title, ctx, "document")

    # A chat's running "working memory" — course definitions, corrections, etc. —
    # is prepended to whatever else we gather so the questions stay consistent
    # with the tutoring so far.
    chat_ctx = ""
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv and conv.user_id == user.id:
            rendered = llm.render_context(conv.context_json or {})
            if rendered:
                chat_ctx = "WHAT THIS CHAT HAS ESTABLISHED (honour these definitions):\n" + rendered + "\n\n"

    # A note's own body is already the exact material to quiz on — use it
    # directly as context instead of a hybrid-search query so the display
    # "topic" stays a short clean label (the note's title), not the whole body.
    if note_context:
        return (topic or "your note", (chat_ctx + note_context)[:9000], "note")

    if topic:
        scope = Scope(user_id=user.id, category=category, conversation_id=conversation_id)
        try:
            hits = hybrid_search(db, query=topic, embedding=embed_text(topic), k=10, scope=scope)
        except Exception:  # retrieval is best-effort here
            hits = []
        ctx = "\n\n".join(h.chunk.text for h in hits if h.score > 0.05)[:9000]
        return (topic, chat_ctx + ctx, "topic" if not conversation_id else "chat")

    if conversation_id:
        rows = db.execute(
            select(Message.role, Message.content)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(8)
        ).all()
        rows = list(reversed(rows))
        last_user = next((c for r, c in reversed(rows) if str(r) in ("user", "MessageRole.USER")), "")
        convo = "\n".join(f"{r}: {c[:600]}" for r, c in rows)
        return (topic or last_user[:120] or "this conversation", chat_ctx + convo[:8000], "chat")

    raise ValueError("provide a topic, a document, or a conversation to build questions from")


# --------------------------------------------------------------- generation
_WORKING_RE = re.compile(
    r"\b(prove|proof|derive|derivation|show that|calculate|evaluate|solve|"
    r"integrate|differentiate|sketch|draw|plot|construct|find the (value|equation|area|"
    r"gradient|volume)|work out|simplify|expand|factou?rise|balance the equation)\b",
    re.I,
)
_ANSWER_MODES = {"text", "text_or_upload"}


def _infer_answer_mode(qtype: str, prompt: str) -> str:
    if qtype in ("mcq", "true_false", "short"):
        return "text"
    if qtype == "numeric" or _WORKING_RE.search(prompt or ""):
        return "text_or_upload"
    return "text"


def _coerce_question(raw: dict, index: int, fallback_tier: str) -> Question | None:
    if not isinstance(raw, dict):
        return None
    prompt = str(raw.get("prompt") or raw.get("question") or "").strip()
    if not prompt:
        return None
    tier = str(raw.get("tier", fallback_tier)).lower().strip()
    if tier not in _TIERS:
        tier = fallback_tier
    qtype = str(raw.get("qtype") or raw.get("type") or "short").lower().strip()
    if qtype not in _VALID_TYPES:
        qtype = "short"
    options = [str(o).strip() for o in raw.get("options", []) if str(o).strip()]
    if qtype == "true_false" and not options:
        options = ["True", "False"]
    if qtype == "mcq" and len(options) < 2:
        qtype = "short"
        options = []
    mode = str(raw.get("answer_mode") or raw.get("answerMode") or "").strip().lower()
    if mode not in _ANSWER_MODES:
        mode = _infer_answer_mode(qtype, prompt)
    elif qtype in ("mcq", "true_false"):
        mode = "text"  # never makes sense to upload a photo for a multiple-choice
    return Question(
        id=str(uuid.uuid4()),
        index=index,
        tier=QuestionTier(tier),
        qtype=QuestionType(qtype),
        prompt=prompt,
        options_json=options,
        answer=str(raw.get("answer", "")).strip(),
        rubric=str(raw.get("rubric", "")).strip(),
        skill=(str(raw.get("skill", "")).strip() or None),
        answer_mode=mode,
    )


def _tier_sequence() -> list[str]:
    seq: list[str] = []
    for tier, n in _TIERS.items():
        seq += [tier] * n
    return seq


def _offline_questions(topic: str, context: str) -> list[dict]:
    """No LLM: cloze / short questions from context sentences (keeps the feature
    working locally without an API key). Not clever, but valid."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", context) if 40 < len(s.strip()) < 240]
    out: list[dict] = []
    for i, tier in enumerate(_tier_sequence()):
        if i < len(sents):
            s = sents[i]
            words = re.findall(r"[A-Za-z][A-Za-z\-]{4,}", s)
            target = words[len(words) // 2] if words else ""
            prompt = s.replace(target, "_____", 1) if target else f"Explain: {s}"
            out.append({
                "tier": tier, "qtype": "short", "prompt": f"Fill the gap: {prompt}",
                "options": [], "answer": target,
                "rubric": f"The missing term is '{target}'.", "skill": topic[:60],
            })
        else:
            out.append({
                "tier": tier, "qtype": "explain",
                "prompt": f"Explain a key idea about {topic} in your own words ({tier} level).",
                "options": [], "answer": "",
                "rubric": "Award credit for a clear, correct explanation with an example.",
                "skill": topic[:60],
            })
    return out


def generate_practice_set(
    db: Session,
    user: User,
    *,
    topic: str | None = None,
    document_id: str | None = None,
    conversation_id: str | None = None,
    category: str | None = None,
    study_level: str | None = None,
    note_context: str | None = None,
) -> PracticeSet:
    resolved_topic, context, source = _gather_context(
        db, user, topic=topic, document_id=document_id,
        conversation_id=conversation_id, category=category, note_context=note_context,
    )
    level = (study_level or "").strip() or user.study_level or settings.default_study_level

    user_msg = (
        f"Student level: {level}\nTopic: {resolved_topic}\n\n"
        + (f"CONTEXT passages from the student's materials:\n{context}\n" if context else
           "(no material uploaded for this — use standard curriculum knowledge)\n")
    )
    model = ""
    raw_qs: list[dict] = []
    if llm.provider_ready():
        try:
            data = llm.json_complete(_GEN_SYSTEM, user_msg, max_tokens=6000, hard=True)
            raw_qs = data.get("questions", []) if isinstance(data, dict) else []
            model = settings.hard_model_name
        except Exception as exc:  # pragma: no cover - network
            logger.warning("practice_generation_failed", error=str(exc))
    if not raw_qs:
        raw_qs = _offline_questions(resolved_topic, context)
        model = model or "offline-template"
    elif len(raw_qs) < _TOTAL:
        # Model gave us a partial set (truncation etc.) — keep the good ones,
        # top up the rest from templates rather than throwing it all away.
        raw_qs = list(raw_qs) + _offline_questions(resolved_topic, context)[len(raw_qs):]

    seq = _tier_sequence()
    questions: list[Question] = []
    for i in range(_TOTAL):
        q = _coerce_question(raw_qs[i] if i < len(raw_qs) else {}, i, seq[i])
        if q is None:
            q = _coerce_question(_offline_questions(resolved_topic, context)[i], i, seq[i])
        questions.append(q)  # type: ignore[arg-type]

    ps = PracticeSet(
        id=str(uuid.uuid4()),
        user_id=user.id,
        conversation_id=conversation_id,
        document_id=document_id,
        topic=resolved_topic[:300],
        category=category,
        study_level=level,
        source=source or "topic",
        model=model,
    )
    ps.questions = questions
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


# --------------------------------------------------------------- grading
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*(?:[eE][+-]?\d+)?")


def _num(text: str) -> float | None:
    m = _NUM_RE.search((text or "").replace(",", ""))
    try:
        return float(m.group()) if m else None
    except ValueError:
        return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _deterministic_grade(q: Question, answer: str, option_index: int | None) -> tuple[float, str] | None:
    """Grade without the model where we safely can. Returns (score, feedback) or None."""
    if q.qtype in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
        chosen = ""
        if option_index is not None and 0 <= option_index < len(q.options_json or []):
            chosen = q.options_json[option_index]
        elif answer:
            chosen = answer
        # Exact normalised match only. A substring check here is unsafe: a wrong
        # distractor's text is often literally contained in the correct answer's
        # text (e.g. picking "Energy" when the answer is "Kinetic energy" must
        # NOT score as correct).
        ok = _norm(chosen) == _norm(q.answer)
        fb = "Correct." if ok else f"Not quite — the answer is **{q.answer}**."
        return (1.0 if ok else 0.0, f"{fb} {q.rubric}".strip())

    if q.qtype == QuestionType.NUMERIC:
        want, got = _num(q.answer), _num(answer)
        if want is None or got is None:
            return None  # fall through to model grading
        tol = max(abs(want) * 0.02, 1e-6)
        ok = abs(got - want) <= tol
        fb = "Correct." if ok else f"The expected value is **{q.answer}**."
        return (1.0 if ok else 0.0, f"{fb} {q.rubric}".strip())

    return None


def grade_attempt(
    db: Session,
    user: User,
    question: Question,
    *,
    answer: str = "",
    option_index: int | None = None,
    transcription: str | None = None,
    image_path: str | None = None,
) -> Attempt:
    answer = (answer or "").strip()
    # A photo of working: the vision transcription becomes the answer to grade.
    from_upload = bool(transcription)
    graded_answer = (transcription or "").strip() if from_upload else answer

    ps = question.practice_set
    level = (ps.study_level if ps else "") or user.study_level or settings.default_study_level

    det = None if from_upload else _deterministic_grade(question, answer, option_index)
    if det is not None:
        score, feedback = det
    elif not graded_answer:
        score = 0.0
        feedback = (
            "I couldn't read any working in that upload — try a clearer photo, or type your answer."
            if image_path else "You didn't write an answer. " + (question.rubric or "")
        )
    elif llm.provider_ready():
        body = (
            f"Student level: {level}\n\nQuestion: {question.prompt}\n\n"
            f"Answer key: {question.answer}\n\nRubric: {question.rubric}\n\n"
            + (
                f"Student's answer (transcribed from a photo of handwritten working):\n{graded_answer}"
                if from_upload
                else f"Student's answer: {graded_answer}"
            )
        )
        try:
            data = llm.json_complete(_GRADE_SYSTEM, body, max_tokens=600, hard=True)
            score = max(0.0, min(1.0, float(data.get("score", 0.0))))
            feedback = str(data.get("feedback", "")).strip() or question.rubric
        except Exception as exc:  # pragma: no cover - network
            logger.warning("grade_failed", error=str(exc))
            score, feedback = _keyword_grade(question, graded_answer)
    else:
        score, feedback = _keyword_grade(question, graded_answer)

    attempt = Attempt(
        id=str(uuid.uuid4()),
        user_id=user.id,
        question_id=question.id,
        practice_set_id=question.practice_set_id,
        user_answer=answer or (
            question.options_json[option_index]
            if option_index is not None and 0 <= option_index < len(question.options_json or [])
            else ""
        ) or ("[uploaded working]" if from_upload else ""),
        correct=score >= 0.6,
        score=round(score, 3),
        feedback=feedback,
        transcription=transcription or None,
        answer_image_path=image_path or None,
        tier=question.tier.value,
        topic=(ps.topic if ps else "")[:300],
        category=ps.category if ps else None,
        skill=question.skill,
    )
    db.add(attempt)
    _update_review(db, user, question, score)
    db.commit()
    db.refresh(attempt)
    return attempt


def _keyword_grade(q: Question, answer: str) -> tuple[float, str]:
    """Offline fallback for free-text: term overlap with the answer key."""
    key = set(_norm(q.answer).split())
    key = {w for w in key if len(w) > 3}
    if not key:
        return 0.5, "Saved — I can't mark this one automatically without a model. " + (q.rubric or "")
    hit = len(key & set(_norm(answer).split())) / len(key)
    score = round(min(1.0, 0.2 + hit), 2)
    return score, f"Rough self-check: your answer covers ~{int(hit * 100)}% of the key points. {q.rubric}".strip()


def _update_review(db: Session, user: User, question: Question, score: float) -> None:
    """Seed / advance the SM-2 schedule for this question."""
    ri = db.execute(
        select(ReviewItem).where(
            ReviewItem.user_id == user.id, ReviewItem.question_id == question.id
        )
    ).scalar_one_or_none()
    q = quality_from_score(score)
    if ri is None:
        if score >= 0.85:
            return  # got it comfortably first time — nothing to review
        ri = ReviewItem(
            id=str(uuid.uuid4()), user_id=user.id, question_id=question.id,
            easiness=2.5, interval_days=0, repetitions=0,
        )
        db.add(ri)
    # column defaults haven't been flushed onto a brand-new row yet — coalesce.
    s = schedule(
        easiness=ri.easiness if ri.easiness is not None else 2.5,
        interval_days=ri.interval_days or 0,
        repetitions=ri.repetitions or 0,
        quality=q,
    )
    from datetime import UTC, datetime, timedelta

    ri.easiness = s.easiness
    ri.interval_days = s.interval_days
    ri.repetitions = s.repetitions
    ri.last_reviewed_at = datetime.now(UTC)
    ri.next_review_at = datetime.now(UTC) + timedelta(days=s.interval_days)
