"""Conversational / meta answers — greetings, "what can you do", "what have I
uploaded", counts, and gibberish. Answered directly (no retrieval), so the user
never sees an "insufficient evidence" banner for a hello.
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
    r"(\s+(there|all|everyone|folks|team|claude))?[\s!.,]*$",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s+you|ty|thx|cheers|much\s+appreciated|great|perfect|awesome|"
    r"nice|cool|got\s+it|ok(ay)?|sounds?\s+good)[\s!.,]*$",
    re.IGNORECASE,
)
_CAPABILITY_RE = re.compile(
    r"\b(what\s+can\s+you\s+do|what\s+do\s+you\s+do|how\s+(does\s+this|do\s+you)\s+work|"
    r"what\s+(is|are)\s+(this|you)|who\s+are\s+you|help\s+me\s+(get\s+)?start|what\s+are\s+"
    r"your\s+(features|capabilities)|how\s+do\s+i\s+use\s+(this|it))\b",
    re.IGNORECASE,
)
_DOC_LIST_RE = re.compile(
    r"\b(what\s+(documents|files|docs|data)\s+(do\s+i\s+have|have\s+i\s+(uploaded|added|got)|"
    r"are\s+(there|here|loaded|uploaded))|list\s+(my\s+|all\s+)?(documents|files|docs)|"
    r"show\s+(me\s+)?(my\s+)?(documents|files|uploads)|what('?s| is)\s+in\s+(my\s+|the\s+)?"
    r"(knowledge\s+base|library|documents))\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(documents|files|docs|chats|conversations|uploads)\b", re.IGNORECASE
)

_LABELS = {
    "policy": "Policies", "contract": "Contracts", "runbook": "Runbooks",
    "tech-doc": "Technical Docs", "meeting-notes": "Meeting Notes", "incident": "Incidents",
    "hr": "HR", "finance": "Finance", "legal": "Legal", "security": "Security",
    "sales": "Sales", "data": "Data & Reports", "deck": "Decks", "uncategorized": "Uncategorised",
}


def _label(cat: str | None) -> str:
    key = cat or "uncategorized"
    return _LABELS.get(key, key.replace("-", " ").replace("_", " ").title())


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


def _example_questions(cats: set[str | None]) -> list[str]:
    ex: list[str] = []
    if any(c in ("sales", "data") for c in cats):
        ex.append("which product is least profitable?")
    if "deck" in cats:
        ex.append("summarise the latest deck")
    ex.append("what does the returns policy say?" if "policy" in cats else "what are the key points across my documents?")
    return ex[:3]


def answer(db: Session, user: User, kind: MetaKind) -> str:
    if kind == "thanks":
        return "You're welcome."
    if kind == "gibberish":
        return "I didn't catch that — ask a question about your documents, or click **Add document** if you haven't uploaded anything yet."

    docs = _docs(db, user)
    n = len(docs)
    cats = {c for _, c in docs}
    cat_str = ", ".join(sorted(_label(c) for c in cats)) if cats else ""

    if kind == "greeting":
        if not n:
            return "Hi — I answer questions about files you upload. Click **Add document** to add a PDF, Word doc, spreadsheet or slide deck, then ask away."
        ex = "\n".join(f"- *{e}*" for e in _example_questions(cats))
        return f"Hi — ask me anything about your {n} document{'s' if n != 1 else ''}. For example:\n{ex}"

    if kind == "capability":
        base = (
            "I answer questions grounded in the files you upload — **PDF, Word, Excel, "
            "PowerPoint** — always with citations back to the source. I can:\n"
            "- **answer questions** about your documents\n"
            "- **run calculations** over spreadsheets (totals, rankings, margins, trends…)\n"
            "- **summarise** a document or a slide deck\n"
            "- **compare** two documents\n"
            "- suggest **next steps** an answer implies"
        )
        if n:
            base += f"\n\nYou currently have **{n}** document{'s' if n != 1 else ''}"
            base += f" across {cat_str}." if cat_str else "."
        else:
            base += "\n\nYou haven't added any documents yet — click **Add document** to start."
        return base

    if kind == "count":
        chats = db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.user_id == user.id, Conversation.archived.is_(False)
            )
        ).scalar_one()
        return f"You have **{n}** document{'s' if n != 1 else ''} and **{chats}** chat{'s' if chats != 1 else ''}."

    # doc_list
    if not n:
        return "You haven't added any documents yet — click **Add document** to upload one."
    lines = [f"- **{t}**" + (f" ({_label(c)})" if c else "") for t, c in docs[:40]]
    more = f"\n\n…and {n - 40} more." if n > 40 else ""
    return f"You have **{n}** document{'s' if n != 1 else ''}:\n" + "\n".join(lines) + more
