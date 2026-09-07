"""SQLAlchemy ORM entities.

Tables
------
users          — an account (username + bcrypt password hash)
conversations  — a chat thread owned by a user
messages       — one turn in a conversation (user prompt or assistant answer)
documents      — a knowledge source owned by a user (policy, contract, ...)
chunks         — embedded, full-text-indexed passages of a document
answers        — a persisted question → grounded answer (audit + action linkage)
actions        — a controlled tool call proposed alongside an answer (human-in-loop)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
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


class SuggestionDecision(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DONE = "done"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


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

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat", nullable=False)
    archived: Mapped[bool] = mapped_column(default=False, nullable=False)

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
    # Full AnswerResponse payload for assistant turns (citations, chunks, tools…).
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
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="document", nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum_col(DocumentStatus), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
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


class DocumentTable(Base):
    """One worksheet of an uploaded spreadsheet, kept queryable for text-to-SQL.

    ``rows_json`` holds the sheet as a list-of-lists (header excluded), capped at
    ``settings.analysis_max_rows``. At query time each row set is loaded into an
    in-memory DuckDB table named ``sql_name``.
    """

    __tablename__ = "document_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sql_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    columns_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    truncated: Mapped[bool] = mapped_column(default=False, nullable=False)
    rows_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "position", name="uq_document_tables_document_id_position"),
    )


class DocumentSlide(Base):
    """One slide of an uploaded deck — structured extract for the reference panel."""

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
    has_chart: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_table: Mapped[bool] = mapped_column(default=False, nullable=False)
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
    compare_mode: Mapped[bool] = mapped_column(default=False, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    citations_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    source_chunks_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    follow_ups_json: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    suggestions: Mapped[list[Suggestion]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class Suggestion(TimestampMixin, Base):
    """An AI-proposed next step the user can accept / reject / mark already done.

    Nothing is executed — this is a decision log. ``conversation_id`` nulls when the
    chat is deleted, which is how the history view detects "conversation deleted".
    """

    __tablename__ = "suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), _user_fk(), nullable=False, index=True)
    answer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("answers.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(String(36))  # dead once conversation_id IS NULL
    question: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    # "explore" = answerable now from the user's own docs/data (gets a Run button);
    # "external" = needs a person or another system (decision-log only).
    kind: Mapped[str] = mapped_column(String(16), default="external", nullable=False)
    decision: Mapped[SuggestionDecision] = mapped_column(
        _enum_col(SuggestionDecision), default=SuggestionDecision.PENDING, nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replaces_id: Mapped[str | None] = mapped_column(String(36))
    superseded_by_id: Mapped[str | None] = mapped_column(String(36))

    answer: Mapped[Answer | None] = relationship(back_populates="suggestions")
