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

ConfidenceLabel = Literal["high", "medium", "low", "insufficient"]
ExplainLevel = Literal["simple", "standard", "deep", "exam"]
QuestionTierValue = Literal["easy", "medium", "hard", "brutal"]
QuestionTypeValue = Literal["mcq", "short", "numeric", "true_false", "explain"]
NoteKindValue = Literal["note", "log", "routine", "saved"]
RetrievalMode = Literal["pinpoint", "document", "overview", "meta", "general"]


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


class ChartPoint(APIModel):
    x: float
    y: float


class ChartSeries(APIModel):
    name: str = ""
    points: list[ChartPoint] = Field(default_factory=list)


class ChartSpec(APIModel):
    type: Literal["line", "bar", "scatter"] = "line"
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(default_factory=list)


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


class TokenUsage(APIModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


# ----------------------------------------------------------------- responses
class AnswerResponse(APIModel):
    id: str
    conversation_id: str | None = None
    message_id: str | None = None
    question: str
    answer: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel = "medium"
    # True when the answer isn't grounded in the user's uploaded materials
    # (the tutor answered from general knowledge, or couldn't answer).
    insufficient_evidence: bool = False
    grounded: bool = False
    # The tutor revised an earlier answer in this chat in light of new context.
    corrected: bool = False
    compare_mode: bool = False
    retrieval_mode: RetrievalMode = "pinpoint"
    retrieval_note: str = ""
    explain_level: ExplainLevel = "standard"
    citations: list[Citation] = Field(default_factory=list)
    source_chunks: list[SourceChunk] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    chart: ChartSpec | None = None
    model: str
    provider: str = "offline"
    latency_ms: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cached: bool = False
    created_at: datetime


# ------------------------------------------------------------------ requests
class QueryRequest(APIModel):
    question: str = Field(..., min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, description="Append to this chat; a new one is created if omitted")
    top_k: int = Field(default=8, ge=1, le=25)
    category_id: str | None = None
    document_id: str | None = Field(
        default=None, description="Target one document — forces a full-document read"
    )
    intent: Literal["auto", "summary"] = Field(
        default="auto",
        description="'summary' forces a full-document read; 'auto' lets the planner decide.",
    )
    explain_level: ExplainLevel | None = Field(
        default=None,
        description="Override the explanation depth for this turn "
        "(simple / standard / deep / exam). Defaults to the category's level.",
    )
    compare_document_ids: list[str] | None = Field(
        default=None, description="Restrict retrieval to these documents and contrast them"
    )
    stream: bool = False
    bypass_cache: bool = False


# --------------------------------------------------------------------- auth
class RegisterRequest(APIModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)
    study_level: str | None = Field(default=None, max_length=32)


class LoginRequest(APIModel):
    username: str
    password: str


class UserRead(APIModel):
    id: str
    username: str
    display_name: str | None = None
    study_level: str = "high-school"
    has_custom_key: bool = False
    created_at: datetime


class UserUpdate(APIModel):
    display_name: str | None = Field(default=None, max_length=120)
    study_level: str | None = Field(default=None, max_length=32)


class SetApiKeyRequest(APIModel):
    # Empty/whitespace clears the key and reverts to the shared one.
    api_key: str | None = Field(default=None, max_length=400)


class AuthResponse(APIModel):
    token: str
    user: UserRead


# ------------------------------------------------------------- categories
class CategoryRead(APIModel):
    id: str
    slug: str
    label: str
    level: str | None = None
    color: str | None = None
    is_default: bool = False
    doc_count: int = 0
    note_count: int = 0
    created_at: datetime | None = None


class CategoryCreate(APIModel):
    label: str = Field(..., min_length=1, max_length=80)
    slug: str | None = Field(default=None, max_length=64)
    level: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)


class CategoryUpdate(APIModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    level: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)


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


class ChatContext(APIModel):
    """The running "working memory" for a chat, surfaced to the user."""

    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    established: list[dict[str, Any]] = Field(default_factory=list)
    student_claims: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    observed_level: str | None = None


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = Field(default_factory=list)
    context: ChatContext = Field(default_factory=ChatContext)
    attached_documents: list[str] = Field(default_factory=list)


class ConversationCreate(APIModel):
    title: str = Field(default="New chat", max_length=200)


class ConversationUpdate(APIModel):
    title: str = Field(..., min_length=1, max_length=200)


# ------------------------------------------------------------- documents
class IngestionRequest(APIModel):
    content: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=128)
    source_type: str = Field(default="text", max_length=64)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionResponse(APIModel):
    document_id: str
    document_title: str
    status: str
    chunks_created: int
    char_count: int
    elapsed_ms: float
    deduplicated: bool = False
    # For image uploads: what the vision model saw / did.
    note_id: str | None = None
    detected_kind: str | None = None


class DocumentChunkPreview(APIModel):
    chunk_index: int
    heading: str | None = None
    text: str
    token_count: int


class SlidePreview(APIModel):
    index: int
    title: str | None = None
    bullets: list[str] = Field(default_factory=list)
    notes: str | None = None
    has_chart: bool = False
    has_table: bool = False
    importance: float = 0.0


class DocumentRead(APIModel):
    id: str
    title: str
    category: str | None = None
    source_type: str
    status: str
    error: str | None = None
    chunk_count: int = 0
    slide_count: int = 0
    char_count: int = 0
    image_kind: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[DocumentChunkPreview] = Field(default_factory=list)
    slides: list[SlidePreview] = Field(default_factory=list)


# ------------------------------------------------------- study guide / materials
class StudyGuideRequest(APIModel):
    document_id: str
    kind: Literal["guide", "glossary", "cheatsheet", "concept_map", "flashcards", "key_slides"] = "guide"


class Flashcard(APIModel):
    front: str
    back: str
    hint: str | None = None


class ConceptNode(APIModel):
    id: str
    label: str
    parent: str | None = None
    note: str | None = None


class StudyGuideResponse(APIModel):
    document_id: str
    kind: str
    title: str
    markdown: str = ""
    flashcards: list[Flashcard] = Field(default_factory=list)
    concepts: list[ConceptNode] = Field(default_factory=list)
    key_slides: list[SlidePreview] = Field(default_factory=list)
    model: str = ""


# ------------------------------------------------------------- assessment
class PracticeRequest(APIModel):
    topic: str | None = Field(default=None, max_length=300)
    document_id: str | None = None
    conversation_id: str | None = None
    category: str | None = Field(default=None, max_length=128)
    study_level: str | None = Field(default=None, max_length=32)


class QuestionRead(APIModel):
    id: str
    index: int
    tier: QuestionTierValue
    qtype: QuestionTypeValue
    prompt: str
    options: list[str] = Field(default_factory=list)
    skill: str | None = None
    # "text" or "text_or_upload" — whether a photo/PDF of working is accepted.
    answer_mode: str = "text"
    # answer + rubric are withheld until the question has been attempted
    answer: str | None = None
    rubric: str | None = None
    attempt: AttemptRead | None = None


class PracticeSetRead(APIModel):
    id: str
    topic: str
    category: str | None = None
    study_level: str
    source: str
    document_id: str | None = None
    conversation_id: str | None = None
    model: str = ""
    created_at: datetime
    questions: list[QuestionRead] = Field(default_factory=list)
    # progress
    answered: int = 0
    correct: int = 0


class PracticeSetSummary(APIModel):
    id: str
    topic: str
    category: str | None = None
    study_level: str
    source: str
    created_at: datetime
    question_count: int = 0
    answered: int = 0
    correct: int = 0


class GradeRequest(APIModel):
    answer: str = Field(default="", max_length=8000)
    # For MCQ / true-false the client may send the chosen option index instead.
    option_index: int | None = None


class AttemptRead(APIModel):
    id: str
    question_id: str | None = None
    user_answer: str = ""
    correct: bool = False
    score: float = 0.0
    feedback: str = ""
    tier: str = "medium"
    # set when the answer was a photo/PDF of working — what the vision model read
    transcription: str | None = None
    created_at: datetime | None = None


class GradeResponse(APIModel):
    attempt: AttemptRead
    answer: str = ""
    rubric: str = ""
    model: str = ""


# ------------------------------------------------------------- notes
class NoteRead(APIModel):
    id: str
    category: str | None = None
    kind: NoteKindValue
    title: str
    body_md: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"
    source_ref: str | None = None
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class NoteCreate(APIModel):
    title: str = Field(..., min_length=1, max_length=300)
    body_md: str = Field(default="", max_length=20000)
    kind: NoteKindValue = "note"
    category: str | None = Field(default=None, max_length=128)
    structured: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = None


class NoteUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body_md: str | None = Field(default=None, max_length=20000)
    category: str | None = Field(default=None, max_length=128)
    pinned: bool | None = None


class SaveFromChatRequest(APIModel):
    message_id: str
    title: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=128)


# ------------------------------------------------------------- export
class ExportRequest(APIModel):
    format: Literal["pdf", "md"] = "pdf"
    title: str = Field(default="StudyBuddy", max_length=300)
    markdown: str = Field(default="", max_length=200000)


# ------------------------------------------------------------- progress
class SetTrendPoint(APIModel):
    """One practice set's result, in chronological order. Unanswered questions
    count as incorrect — an untouched set is a real 0/N data point, not a gap."""

    set_id: str
    created_at: str
    correct: int = 0
    total: int = 0
    accuracy: float = 0.0


class CategoryProgress(APIModel):
    category: str
    label: str
    total_sets: int = 0
    solved_sets: int = 0
    doc_count: int = 0
    by_tier: dict[str, float] = Field(default_factory=dict)
    trend: list[SetTrendPoint] = Field(default_factory=list)


class ProgressResponse(APIModel):
    total_questions: int = 0
    total_correct: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    total_sets: int = 0
    incomplete_sets: int = 0
    by_tier: dict[str, float] = Field(default_factory=dict)
    by_category: list[CategoryProgress] = Field(default_factory=list)
    documents: int = 0
    notes: int = 0


# ------------------------------------------------------------- misc
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
    vision_enabled: bool = False
    embedding_provider: str
    embedding_dim: int


# ------------------------------------------------------------- stream events
class StreamEnvelope(APIModel):
    """One SSE frame: ``{ "type": ..., "payload": {...} }``."""

    type: Literal["start", "grounding", "token", "final", "error"]
    payload: dict[str, Any] = Field(default_factory=dict)


QuestionRead.model_rebuild()
