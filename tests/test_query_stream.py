from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.api.routes.query import QueryStreamService, encode_sse
from packages.contracts.models import Answer, Query, StreamEvent, StreamEventType


class FakeGraph:
    async def ainvoke(self, input: dict[str, object]) -> dict[str, object]:
        return {
            "route": "unstructured",
            "answer": Answer(
                text="Grounded answer",
                citations=[],
                model="test",
                created_at=datetime.now(UTC),
            ),
        }


@pytest.mark.asyncio
async def test_query_stream_emits_answer_and_completion() -> None:
    """Verify graph output becomes ordered typed SSE events."""
    query = Query(text="Explain the policy", tenant_id=uuid4())
    events = [event async for event in QueryStreamService(FakeGraph()).events(query)]

    assert [event.event_id for event in events] == ["route", "answer", "complete"]
    assert events[1].event_type is StreamEventType.TOKEN
    assert events[1].data == "Grounded answer"


def test_encode_sse_uses_standard_framing() -> None:
    """Verify event IDs, names, and JSON data are encoded correctly."""
    event = StreamEvent(
        event_id="event-1",
        event_type=StreamEventType.ERROR,
        data="failed",
        created_at=datetime.now(UTC),
    )
    encoded = encode_sse(event)
    assert "id: event-1\n" in encoded
    assert "event: error\n" in encoded
    assert 'data: "failed"\n\n' in encoded