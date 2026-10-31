from uuid import uuid4

from apps.worker.observability import InMemoryTraceSink, TraceEvent, start_trace


async def test_trace_sink_records_redacted_lifecycle_events() -> None:
    """Verify trace events are correlated without retaining raw query text."""
    sink = InMemoryTraceSink()
    trace = start_trace("secret customer query", uuid4())
    await sink.record(TraceEvent(trace.trace_id, "query", "started"))

    assert sink.events[0].trace_id == trace.trace_id
    assert trace.query == "<redacted>"