"""Typed application configuration (Pydantic-Settings v2).

Every value can be overridden by an environment variable or an ``.env`` file at
the backend root. Secrets are never hard-coded — the defaults here are safe for
local development only.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Lists that come from env / .env as a comma-separated string. NoDecode stops
# pydantic-settings from trying to JSON-parse them first, so the "before"
# validator below can split on commas.
CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    """Centralised, validated configuration singleton."""

    # ------------------------------------------------------------------ app
    app_name: str = "Groundwork"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    version: str = "1.0.0"

    # ------------------------------------------------------------- data layer
    database_url: str = Field(
        default="postgresql+psycopg://ekdp:ekdp@localhost:5432/ekdp",
        description="SQLAlchemy URL (psycopg v3 driver).",
    )
    redis_url: str = "redis://localhost:6379/0"

    # Create/upgrade tables on startup. Fine for dev; in prod set false and run
    # `python -m app.core.database init` once as a release step (see DEPLOY.md).
    auto_migrate: bool = True
    # No shared demo corpus — every account starts empty and uploads its own docs.
    seed_on_startup: bool = False

    # ------------------------------------------------------------------- auth
    jwt_secret: str = Field(
        default="dev-insecure-change-me-0000000000000000",
        description="HMAC secret for JWTs (>=32 chars). MUST be overridden in production.",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 720  # 30 days
    min_password_length: int = 8

    # --------------------------------------------------------------- retrieval
    top_k_default: int = 8
    max_top_k: int = 25
    # Number of candidates each retriever pulls before fusion / rerank.
    retrieval_candidates: int = 40
    rrf_k: int = 60  # reciprocal-rank-fusion constant
    rerank_enabled: bool = True
    # "summarise this document" loads every chunk of one document in order (no
    # ranking). Cap so a huge document can't blow the context window.
    document_mode_max_chunks: int = 40
    # Minimum reranked score for the top chunk to count as usable evidence.
    # Tuned for the deterministic-embedding default where keyword + term-coverage
    # carry retrieval; raise it when using real (semantic) embeddings.
    min_evidence_score: float = 0.08

    # ------------------------------------------------------------------ uploads
    # Max upload size. Spreadsheets and decks run larger than text docs.
    max_upload_bytes: int = 15_000_000

    # ------------------------------------------------------ spreadsheet analytics
    # Rows stored per sheet for text-to-SQL (older rows dropped, flagged truncated).
    analysis_max_rows: int = 20_000
    # Rows returned to the client / model from an analysis query.
    analysis_result_row_cap: int = 200
    # Hard timeout for a single generated SQL query.
    analysis_sql_timeout_seconds: float = 8.0

    # --------------------------------------------------------------- embeddings
    # "openai" also covers any OpenAI-compatible embeddings endpoint. If
    # EMBEDDING_BASE_URL / EMBEDDING_API_KEY are unset they fall back to the
    # OPENAI_* values, so chat + embeddings can share one provider or split.
    embedding_provider: Literal["openai", "deterministic"] = "deterministic"
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_dim: int = 768

    # ---------------------------------------------------------------------- LLM
    # "openai" also covers any OpenAI-compatible endpoint (Groq, Gemini, Mistral,
    # OpenRouter, Ollama, …) — just set OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL.
    llm_provider: Literal["anthropic", "openai", "offline"] = "offline"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 1400
    llm_timeout_seconds: float = 45.0
    # Answers below this confidence are surfaced with an "insufficient evidence"
    # disclaimer instead of a confident-sounding response.
    low_confidence_threshold: float = 0.35

    # --------------------------------------------------------------- suggestions
    # After each answer the model proposes 0-4 next steps the user accepts /
    # rejects / marks done. Nothing is executed. Set false to switch it off.
    suggestions_enabled: bool = True
    # Max alternatives generated per suggestion slot when the user keeps rejecting.
    suggestion_max_alternatives: int = 3

    # ---------------------------------------------------------------- caching
    answer_cache_ttl_seconds: int = 900
    cache_enabled: bool = True

    # ------------------------------------------------------------- rate limit
    rate_limit_enabled: bool = True
    # A human asking questions won't reach this; a runaway loop or a free LLM
    # tier's per-minute cap will.
    rate_limit_per_minute: int = 30
    # Behind a load balancer the socket peer is the proxy, so every user shares
    # one rate-limit bucket. Set true in production to read X-Forwarded-For.
    trust_proxy: bool = False

    # ------------------------------------------------------------ observability
    otlp_endpoint: str | None = None
    otel_console_export: bool = True
    log_level: str = "INFO"
    log_json: bool = False

    # ------------------------------------------------------------------- CORS
    cors_origins: CsvList = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------------------------- validators
    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v: object) -> object:
        """Hosting dashboards (Neon, Render, Railway) hand out a bare
        ``postgres://`` / ``postgresql://`` URL. SQLAlchemy needs the driver
        spelled out, and Neon needs SSL — coerce both so a paste-in deploy
        doesn't 500 on the first connection.
        """
        if not isinstance(v, str) or not v:
            return v
        url = v.strip()
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        if "neon.tech" in url and "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):  # tolerate a JSON array form too
                import json

                try:
                    return json.loads(s)
                except ValueError:
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _is_local(url: str | None) -> bool:
        return bool(url) and any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"))

    @property
    def openai_configured(self) -> bool:
        # A hosted OpenAI-compatible endpoint needs a key; a local one
        # (Ollama / LM Studio) does not.
        return bool(self.openai_api_key) or self._is_local(self.openai_base_url)

    @property
    def resolved_embedding_base_url(self) -> str | None:
        return self.embedding_base_url or self.openai_base_url

    @property
    def resolved_embedding_api_key(self) -> str | None:
        if self.embedding_api_key:
            return self.embedding_api_key
        # Only borrow the chat key when embeddings use the same endpoint.
        if self.embedding_base_url and self.embedding_base_url != self.openai_base_url:
            return None
        return self.openai_api_key

    @property
    def embedding_configured(self) -> bool:
        return bool(self.resolved_embedding_api_key) or self._is_local(self.resolved_embedding_base_url)

    @property
    def llm_active(self) -> bool:
        """Whether a real LLM will be used for answer synthesis."""
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return self.openai_configured
        return False

    @property
    def active_model_name(self) -> str:
        if self.llm_provider == "anthropic" and self.anthropic_api_key:
            return self.anthropic_model
        if self.llm_provider == "openai" and self.openai_configured:
            return self.openai_model
        return "offline-extractive"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
