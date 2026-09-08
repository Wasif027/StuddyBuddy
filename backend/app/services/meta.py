"""Conversational / meta replies — greetings, "what can you do", "what have I
uploaded", counts, gibberish. Answered directly (no retrieval) so a hello never
triggers the retrieval pipeline.
"""

from __future__ import annotations

import re
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orm import Conversation, Document, User

MetaKind = Literal["greeting", "thanks", "capability", "doc_list", "count", "gibberish"]

_GREETING_RE = re.compile(
    r"^\s*(hi|hey+|hello+|yo|hiya|howdy|sup|good\s+(morning|afternoon|evening|day)|greetings)"
    r"(\s+(there|all|studybuddy|buddy|tutor))?[\s!.,]*$",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s+you|ty|thx|cheers|much\s+appreciated|great|perfect|awesome|"
    r"nice|cool|got\s+it|ok(ay)?|sounds?\s+good|makes\s+sense)[\s!.,]*$",
    re.IGNORECASE,
)
_CAPABILITY_RE = re.compile(
    r"\b(what\s+can\s+you\s+do|what\s+do\s+you\s+do|how\s+(does\s+this|do\s+you)\s+work|"
    r"what\s+(is|are)\s+(this|you)|who\s+are\s+you|help\s+me\s+(get\s+)?start|what\s+are\s+"
    r"your\s+(features|capabilities)|how\s+do\s+i\s+use\s+(this|it))\b",
    re.IGNORECASE,
)
_DOC_LIST_RE = re.compile(
    r"\b(what\s+(materials|documents|files|docs|notes|slides)\s+(do\s+i\s+have|have\s+i\s+"
    r"(uploaded|added|got)|are\s+(there|here|loaded|uploaded))|list\s+(my\s+|all\s+)?"
    r"(materials|documents|files|docs|notes)|show\s+(me\s+)?(my\s+)?(materials|documents|files|uploads))\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(materials|documents|files|docs|notes|chats|conversations|uploads)\b",
    re.IGNORECASE,
)


def detect(question: str) -> MetaKind | None:
    q = question.strip()
    if len(re.sub(r"[^a-z]", "", q.lower())) < 2:
        return "gibberish"
    if _GREETING_RE.match(q):
        return "greeting"
    if _THANKS_RE.match(q):
        return "thanks"
    if _DOC_LIST_RE.search(q):
        return "doc_list"
    if _COUNT_RE.search(q):
        return "count"
    if _CAPABILITY_RE.search(q):
        return "capability"
    return None


def is_ephemeral(kind: MetaKind) -> bool:
    return kind in ("greeting", "thanks", "capability", "gibberish")


def _docs(db: Session, user: User) -> list[tuple[str, str | None]]:
    return list(
        db.execute(
            select(Document.title, Document.category)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
        ).all()
    )


def _label(db: Session, user_id: str, slug: str | None) -> str:
    from app.services.catalog import category_label

    return category_label(db, user_id, slug)


def answer(db: Session, user: User, kind: MetaKind) -> str:
    name = (user.display_name or user.username or "").split(" ")[0]
    hey = f"Hi {name}" if name else "Hi"

    if kind == "thanks":
        return "You're welcome — ask me anything else, or say *practice questions on …* when you want to test yourself."
    if kind == "gibberish":
        return (
            "I didn't quite catch that. Ask me to explain a topic, upload your notes or "
            "slides, or say *give me practice questions on …*."
        )

    docs = _docs(db, user)
    n = len(docs)

    if kind == "greeting":
        if not n:
            return (
                f"{hey}! I'm StudyBuddy, your study tutor. Ask me to explain any topic up to "
                "undergraduate level — I'll pitch it to your level and can go simpler or deeper "
                "on request. Upload your notes, slides or textbook pages and I'll ground the "
                "explanations in them. When you're ready to test yourself, ask for practice "
                "questions.\n\nWhat would you like to work on today?"
            )
        return (
            f"{hey}! What would you like to work on? I can explain a topic, quiz you with a set "
            f"of practice questions, or work through your {n} uploaded "
            f"material{'s' if n != 1 else ''}."
        )

    if kind == "capability":
        return (
            "I'm a study tutor. I can:\n"
            "- **explain any topic** up to undergraduate level, pitched to you — ask for it "
            "*simpler*, *deeper* or *exam-style* any time\n"
            "- **ground explanations in your own materials** (PDF, Word, slides, photos) with "
            "citations back to the page or slide\n"
            "- **set practice questions** — 4 easy, 4 medium, 2 hard and 1 very hard — at your "
            "level, then mark your answers with feedback\n"
            "- build **study guides, glossaries, concept maps and flashcards** from a document\n"
            "- read a **photo** — a diagram, a worked problem, a page of notes, or your class "
            "timetable\n"
            "- keep **notes** and a learning log, and track your **progress** and weak spots\n\n"
            + (
                f"You have **{n}** material{'s' if n != 1 else ''} uploaded."
                if n
                else "Upload your first material to get started, or just ask me to explain something."
            )
        )

    if kind == "count":
        chats = db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.user_id == user.id, Conversation.archived.is_(False)
            )
        ).scalar_one()
        return f"You have **{n}** material{'s' if n != 1 else ''} and **{chats}** chat{'s' if chats != 1 else ''}."

    # doc_list
    if not n:
        return "You haven't uploaded any materials yet — add your notes, slides or a textbook chapter."
    lines = [f"- **{t}**" + (f" ({_label(db, user.id, c)})" if c else "") for t, c in docs[:40]]
    more = f"\n\n…and {n - 40} more." if n > 40 else ""
    return f"You have **{n}** material{'s' if n != 1 else ''}:\n" + "\n".join(lines) + more
