"""Pydantic v2 DTOs.

Every model serialises to **camelCase** JSON (JS-friendly) while still accepting
snake_case on input. These shapes are the single source of truth for the wire
contract and are mirrored by ``frontend/src/lib/types.ts``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SuggestionDecisionValue = Literal["pending", "accepted", "rejected", "done"]
SuggestionPriority = Literal["high", "medium", "low"]
ConfidenceLabel = Literal["high", "medium", "low", "insufficient"]


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)


# --------------------------------------------------------------------- nested
class Citation(APIModel):
    marker: int = Field(..., description="1-based [n] marker used in the answer text")
    chunk_id: str
    document_id: str
    title: str
    category: str | None = None
    page: int | None = None
    quote: str
    score: float = Field(..., ge=0.0, le=1.0)


class SourceChunk(APIModel):
    chunk_id: str
    document_id: str
    title: str
    heading: str | None = None
    chunk_index: int = 0
    text: str
    category: str | None = None
    score: float = Field(..., ge=0.0, le=1.0, description="Fused retrieval score")
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SuggestionRead(APIModel):
    id: str
    text: str
    rationale: str | None = None
    priority: SuggestionPriority = "medium"
    # "explore" = the app can answer it now (gets a Run button); "external" = decision-log only
    kind: Literal["explore", "external"] = "external"
    decision: SuggestionDecisionValue = "pending"
    note: str | None = None
    reject_depth: int = 0
    created_at: datetime | None = None
    decided_at: datetime | None = None
    # context (populated in the history view)
    question: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    conversation_title: str | None = None
    conversation_deleted: bool = False


class TokenUsage(APIModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


class ChartSpec(APIModel):
    type: Literal["bar", "line"] = "bar"
    x: str
    series: list[str] = Field(default_factory=list)


class AnalysisBlock(APIModel):
    """A computed answer over uploaded spreadsheet data (text-to-SQL)."""

    ok: bool = True
    sql: str = ""
    dialect: str = "duckdb"
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    tables_used: list[str] = Field(default_factory=list)
    assumptions: str = ""
    error: str | None = None
    chart: ChartSpec | None = None


# ----------------------------------------------------------------- responses
class AnswerResponse(APIModel):
    id: str
    conversation_id: str | None = None
    message_id: str | None = None
    question: str
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel = "medium"
    insufficient_evidence: bool = False
    compare_mode: bool = False
    retrieval_mode: Literal["pinpoint", "document", "overview", "analysis", "meta"] = "pinpoint"
    retrieval_note: str = ""
    analysis: AnalysisBlock | None = None
    citations: list[Citation] = Field(default_factory=list)
    source_chunks: list[SourceChunk] = Field(default_factory=list)
    suggestions: list[SuggestionRead] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    model: str
    provider: str = "offline"
    latency_ms: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cached: bool = False
    created_at: datetime


# ------------------------------------------------------------------ requests
class QueryRequest(APIModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, description="Append to this chat; a new one is created if omitted")
    top_k: int = Field(default=8, ge=1, le=25)
    category_id: str | None = None
    document_id: str | None = Field(
        default=None, description="Target one document — forces a full-document read (summary)"
    )
    intent: Literal["auto", "summary", "analysis"] = Field(
        default="auto",
        description="'analysis' forces spreadsheet text-to-SQL; 'summary' forces a full read; "
        "'auto' lets the query planner decide from the question.",
    )
    compare_document_ids: list[str] | None = Field(
        default=None, description="Restrict retrieval to these documents and contrast them"
    )
    suggest: bool = Field(default=True, description="Generate AI next-step suggestions for this answer")
    stream: bool = False
    bypass_cache: bool = False


# --------------------------------------------------------------------- auth
class RegisterRequest(APIModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(APIModel):
    username: str
    password: str


class UserRead(APIModel):
    id: str
    username: str
    display_name: str | None = None
    created_at: datetime


class AuthResponse(APIModel):
    token: str
    user: UserRead


# ------------------------------------------------------------- conversations
class MessageRead(APIModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    answer: AnswerResponse | None = None
    created_at: datetime


class ConversationRead(APIModel):
    id: str
    title: str
    message_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = Field(default_factory=list)


class ConversationCreate(APIModel):
    title: str = Field(default="New chat", max_length=200)


class ConversationUpdate(APIModel):
    title: str = Field(..., min_length=1, max_length=200)


class IngestionRequest(APIModel):
    content: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=128)
    source_type: str = Field(default="document", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionResponse(APIModel):
    document_id: str
    document_title: str
    status: str
    chunks_created: int
    char_count: int
    elapsed_ms: float
    deduplicated: bool = False


class DocumentChunkPreview(APIModel):
    chunk_index: int
    heading: str | None = None
    text: str
    token_count: int


class DocumentRead(APIModel):
    id: str
    title: str
    category: str | None = None
    source_type: str
    status: str
    error: str | None = None
    chunk_count: int = 0
    char_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    chunks: list[DocumentChunkPreview] = Field(default_factory=list)


class DocumentCategory(APIModel):
    id: str
    label: str
    doc_count: int = 0
    chunk_count: int = 0
    status: Literal["ready", "processing", "failed", "empty", "indexing"] = "ready"


class SuggestionDecisionRequest(APIModel):
    decision: Literal["accept", "reject", "done"]
    note: str | None = Field(default=None, max_length=2000)


class SuggestionDecisionResponse(APIModel):
    suggestion: SuggestionRead
    alternative: SuggestionRead | None = None
    message: str = ""


class ServiceStatus(APIModel):
    postgres: str
    redis: str
    api: str = "up"


class HealthResponse(APIModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    env: str
    services: ServiceStatus
    llm_provider: str
    llm_model: str
    llm_active: bool
    embedding_provider: str
    embedding_dim: int


# ------------------------------------------------------------- stream events
class StreamEnvelope(APIModel):
    """One SSE frame: ``{ "type": ..., "payload": {...} }``."""

    type: Literal["start", "grounding", "token", "analysis", "suggestions", "final", "error"]
    payload: dict[str, Any] = Field(default_factory=dict)
