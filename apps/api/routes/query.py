from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from apps.api.auth import AuthContext
from apps.api.membership import get_authorized_context
from apps.worker.observability import InMemoryTraceSink, TraceEvent, TraceSink, start_trace
from packages.contracts.models import Answer, Query, StreamEvent, StreamEventType


class QueryGraph(Protocol):
    async def ainvoke(self, input: dict[str, object]) -> dict[str, object]:
        """Run the compiled orchestration graph."""
        ...


class QueryStreamService:
    """Translate graph completion into a reconnect-friendly SSE event stream."""

    def __init__(self, graph: QueryGraph, trace_sink: TraceSink | None = None) -> None:
        self._graph = graph
        self._trace_sink = trace_sink or InMemoryTraceSink()

    async def events(self, query: Query) -> AsyncIterator[StreamEvent]:
        """Yield route, answer, citation, completion, or error events in order."""
        trace = start_trace(query.text, query.tenant_id)
        await self._trace_sink.record(
            TraceEvent(trace.trace_id, "query", "started", {"tenant_id": str(query.tenant_id)})
        )
        try:
            result = await self._graph.ainvoke({"query": query})
            route = result.get("route")
            if route is not None:
                yield StreamEvent(
                    event_id="route",
                    event_type=StreamEventType.COMPLETE,
                    data=str(route),
                    created_at=query_created_at(),
                )
            error = result.get("error")
            if error:
                yield StreamEvent(
                    event_id="error",
                    event_type=StreamEventType.ERROR,
                    data=str(error),
                    created_at=query_created_at(),
                )
                return
            answer = result.get("answer")
            if not isinstance(answer, Answer):
                raise ValueError("orchestration graph returned no answer")
            yield StreamEvent(
                event_id="answer",
                event_type=StreamEventType.TOKEN,
                data=answer.text,
                created_at=query_created_at(),
            )
            for index, citation in enumerate(answer.citations):
                yield StreamEvent(
                    event_id=f"citation-{index}",
                    event_type=StreamEventType.CITATION,
                    data=citation.model_dump_json(),
                    created_at=query_created_at(),
                )
            yield StreamEvent(
                event_id="complete",
                event_type=StreamEventType.COMPLETE,
                data="complete",
                created_at=query_created_at(),
            )
            await self._trace_sink.record(
                TraceEvent(trace.trace_id, "query", "completed", {"route": str(route or "unknown")})
            )
        except Exception as exc:
            await self._trace_sink.record(
                TraceEvent(trace.trace_id, "query", "failed", {"error_type": type(exc).__name__})
            )
            yield StreamEvent(
                event_id="error",
                event_type=StreamEventType.ERROR,
                data=str(exc),
                created_at=query_created_at(),
            )


def query_created_at():
    """Return a timezone-aware timestamp for SSE event creation."""
    from datetime import UTC, datetime

    return datetime.now(UTC)


def encode_sse(event: StreamEvent) -> str:
    """Encode one typed event using standard SSE framing."""
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event_type.value}\n"
        f"data: {json.dumps(event.data)}\n\n"
    )


router = APIRouter(prefix="/api/v1/query", tags=["query"])


@router.post("/stream")
async def stream_query(
    request: Request,
    query: Query,
    auth: AuthContext = Depends(get_authorized_context),  # noqa: B008
) -> StreamingResponse:
    """Stream a graph answer over SSE, returning 503 when not composed."""
    service = getattr(request.app.state, "query_service", None)
    if not isinstance(service, QueryStreamService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="query orchestration is not configured",
        )
    query = query.model_copy(update={"tenant_id": auth.tenant_id})

    async def body() -> AsyncIterator[str]:
        async for event in service.events(query):
            yield encode_sse(event)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
