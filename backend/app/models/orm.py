"""SQLAlchemy ORM entities.

Tables
------
users          — an account (username + bcrypt password hash + study level)
categories     — a user-owned subject folder (Maths, Physics, "Bio A-level" …)
conversations  — a chat thread owned by a user
messages       — one turn in a conversation (user prompt or assistant answer)
documents      — a study material owned by a user (PDF, Word, slides, image scan)
chunks         — embedded, full-text-indexed passages of a document
document_slides— one slide of an uploaded deck (structured extract)
answers        — a persisted question → grounded tutor answer (chat audit)
practice_sets  — a generated set of practice questions (4 easy / 4 med / 2 hard / 1 brutal)
questions      — one question in a practice set, with its answer key + rubric
attempts       — a user's answer to a question, AI-graded (feeds the progress dashboard)
notes          — a saved note / learning-log entry / parsed routine
review_items   — SM-2 spaced-repetition state for a question the user got wrong
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.database import Base

_DIM = get_settings().embedding_dim


def _uuid() -> str:
    return str(uuid.uuid4())


def _enum_col(enum_cls: type[enum.Enum]):
    """Store the enum's *value* (lowercase) rather than its NAME."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class QuestionTier(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    BRUTAL = "brutal"


class QuestionType(str, enum.Enum):
    MCQ = "mcq"
    SHORT = "short"
    NUMERIC = "numeric"
    TRUE_FALSE = "true_false"
    EXPLAIN = "explain"


class NoteKind(str, enum.Enum):
    NOTE = "note"          # a plain note
    LOG = "log"            # a dated "today I learned …" entry
    ROUTINE = "routine"    # a parsed timetable / class schedule
    SAVED = "saved"        # an explanation saved from a chat


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _user_fk() -> ForeignKey:
    # A fresh ForeignKey per column (they cannot share a parent).
    return ForeignKey("users.id", ondelete="CASCADE")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    # The level the tutor calibrates explanations and question difficulty to,
    # e.g. "year-8", "gcse", "a-level", "undergraduate". A per-category override
    # lives on the Category row.
    study_level: Mapped[str] = mapped_column(String(32), default="high-school", nullable=False)
    # The user's own Gemini API key, encrypted (app.core.crypto) — never sent
    # back to the client once saved. NULL = use the shared server key.
    custom_llm_api_key_enc: Mapped[str | None] = mapped_column(Text)

    @property
    def has_custom_key(self) -> bool:
        return self.custom_llm_api_key_enc is not None

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    categories: Mapped[list[Category]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Category(TimestampMixin, Base):
    """A subject folder owned by one user. Documents, notes and practice sets
    reference it by ``slug`` (stable, user-scoped). New accounts are seeded with
    a default set; the user can add their own."""

    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # Per-category study level override ("a-level" for Chemistry, "gcse" for the
    # rest). Null → fall back to the user's study_level.
    level: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(16))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="categories")

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_categories_user_id_slug"),
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat", nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A structured, running "working memory" for this chat — the topic, facts
    # established (with their source), corrections made, misconceptions spotted.
    # Refreshed after each turn and fed into every later generation in this chat.
    # Shape: {topics:[str], established:[{fact,source,verified}], corrections:
    # [{was,now,turn}], student_claims:[{claim,issue}], observed_level:str|None,
    # misconceptions:[str], summary:str}
    context_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(Message.created_at, Message.role.desc())",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(_enum_col(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Full AnswerResponse payload for assistant turns (citations, chunks, …).
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Category slug (matches Category.slug for this user). Free-form is tolerated;
    # an unknown slug auto-creates a Category row at upload time.
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    # "pdf" | "docx" | "pptx" | "image" | "text"
    source_type: Mapped[str] = mapped_column(String(64), default="document", nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum_col(DocumentStatus), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Set when the material was added from inside a chat — it's then always in
    # scope for that chat's retrieval, on top of any category filter.
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )

    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    slides: Mapped[list[DocumentSlide]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "content_sha256", name="uq_documents_user_id_content_sha256"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(512))
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_DIM))
    text_tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', coalesce(heading,'') || ' ' || text)", persisted=True)
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),
        Index("ix_chunks_text_tsv", "text_tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class DocumentSlide(Base):
    """One slide of an uploaded deck — structured extract for the study panel."""

    __tablename__ = "document_slides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    bullets_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    tables_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    has_chart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_table: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 0-1 heuristic: how information-dense / "important" this slide looks.
    data_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "index", name="uq_document_slides_document_id_index"),
    )


class Answer(TimestampMixin, Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(128))
    compare_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    citations_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    source_chunks_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    follow_ups_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class PracticeSet(TimestampMixin, Base):
    """A generated practice set: 4 easy + 4 medium + 2 hard + 1 brutal, pitched
    at a study level, drawn from a topic, a document, or the current chat."""

    __tablename__ = "practice_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    study_level: Mapped[str] = mapped_column(String(32), nullable=False)
    # "topic" | "document" | "chat"
    source: Mapped[str] = mapped_column(String(16), default="topic", nullable=False)
    model: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    questions: Mapped[list[Question]] = relationship(
        back_populates="practice_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Question.index",
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    practice_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("practice_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[QuestionTier] = mapped_column(_enum_col(QuestionTier), nullable=False)
    qtype: Mapped[QuestionType] = mapped_column(_enum_col(QuestionType), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    # Canonical answer / answer key. For MCQ this is the correct option text.
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Grading guidance + the explanation shown after answering.
    rubric: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The sub-skill / subtopic this question tests — used for weak-topic detection.
    skill: Mapped[str | None] = mapped_column(String(160), index=True)
    # "text" = typed answer only (theory / recall / MCQ). "text_or_upload" = the
    # student may type OR upload a photo / PDF of their working (derivations,
    # proofs, multi-step calculations, sketches).
    answer_mode: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    practice_set: Mapped[PracticeSet] = relationship(back_populates="questions")

    __table_args__ = (
        UniqueConstraint("practice_set_id", "index", name="uq_questions_practice_set_id_index"),
    )


class Attempt(TimestampMixin, Base):
    """A graded answer to a question. Question fields are snapshotted so an
    attempt still counts toward the progress dashboard after the set is deleted."""

    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    question_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="SET NULL"), index=True
    )
    practice_set_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..1
    feedback: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Set when the student uploaded a photo / PDF of their working. `transcription`
    # is what the vision model read from it — shown so they can check the reading.
    answer_image_path: Mapped[str | None] = mapped_column(String(512))
    transcription: Mapped[str | None] = mapped_column(Text)
    # snapshot
    tier: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    topic: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    skill: Mapped[str | None] = mapped_column(String(160), index=True)


class ReviewItem(Base):
    """SM-2 spaced-repetition state for a question the user should revisit
    (created when they get one wrong). Same algorithm as Anki."""

    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    easiness: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_review_items_user_id_question_id"),
    )


class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    kind: Mapped[NoteKind] = mapped_column(
        _enum_col(NoteKind), default=NoteKind.NOTE, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # For routines: {"days": [{"day": "Monday", "entries": [{"time": "09:00",
    # "label": "Physics", "location": "Room 4"}]}]}. Otherwise {}.
    structured_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # "manual" | "chat" | "image"
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(36))  # message id / document id
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
