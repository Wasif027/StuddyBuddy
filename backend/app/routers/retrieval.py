"""Retrieval API — grounded Q&A (JSON or SSE stream)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.telemetry import tracer
from app.models.orm import User
from app.models.schemas import AnswerResponse, QueryRequest
from app.services.rag import generate_answer, stream_answer

_tracer = tracer(__name__)
router = APIRouter(tags=["retrieval"])


@router.post(
    "/query",
    response_model=AnswerResponse,
    summary="Ask a question",
    description="Returns a grounded answer with citations, confidence, source passages and "
    "AI-suggested next steps. Set `stream=true` for an SSE token stream. Pass "
    "`compareDocumentIds` to restrict retrieval to specific documents and contrast them.",
)
async def query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if request.stream:

        async def event_gen():
            try:
                async for frame in stream_answer(db, user, request):
                    yield {"event": frame["type"], "data": json.dumps(frame["payload"], default=str)}
            except Exception as exc:  # pragma: no cover - defensive
                db.rollback()
                yield {"event": "error", "data": json.dumps({"message": str(exc)})}

        # identity → GZipMiddleware skips this response; buffering gzip would
        # defeat token-by-token streaming.
        return EventSourceResponse(
            event_gen(),
            headers={"X-Accel-Buffering": "no", "Content-Encoding": "identity"},
        )

    with _tracer.start_as_current_span("retrieval.query") as span:
        response = generate_answer(db, user, request)
        span.set_attribute("answer.id", response.id)
        span.set_attribute("confidence", response.confidence)
        return response
