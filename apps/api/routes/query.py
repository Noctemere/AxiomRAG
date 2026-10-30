from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from packages.contracts.models import Answer, Query, StreamEvent, StreamEventType


class QueryGraph(Protocol):
    async def ainvoke(self, input: dict[str, object]) -> dict[str, object]:
        """Run the compiled orchestration graph."""
        ...


class QueryStreamService:
    """Translate graph completion into a reconnect-friendly SSE event stream."""

    def __init__(self, graph: QueryGraph) -> None:
        self._graph = graph

    async def events(self, query: Query) -> AsyncIterator[StreamEvent]:
        """Yield route, answer, citation, completion, or error events in order."""
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
        except Exception as exc:
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
async def stream_query(request: Request, query: Query) -> StreamingResponse:
    """Stream a graph answer over SSE, returning 503 when not composed."""
    service = getattr(request.app.state, "query_service", None)
    if not isinstance(service, QueryStreamService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="query orchestration is not configured",
        )

    async def body() -> AsyncIterator[str]:
        async for event in service.events(query):
            yield encode_sse(event)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
