"""Enterprise Knowledge & Decision Platform - Backend application package.

A production-grade FastAPI service that provides Retrieval-Augmented
Generation (RAG) over ingested documents, plus an agentic "decision pipeline"
that can propose tool calls alongside grounded answers.

Package layout (layered architecture - routers -> services -> models):

    app/
      core/       configuration, database, telemetry
      models/     SQLAlchemy ORM entities + Pydantic v2 DTOs
      services/   business logic: embeddings, vector store, RAG, tools
      routers/    HTTP layer: ingestion, retrieval, health
      main.py     FastAPI app entrypoint
"""

__version__ = "0.1.0"
