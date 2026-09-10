from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from apps.worker.orchestration import OrchestrationGraph, QueryRoute, QueryRouter
from packages.contracts.models import (
    Answer,
    DocumentChunk,
    Modality,
    Provenance,
    Query,
    RetrievalFilter,
    RetrievalResult,
)


def result_for(tenant_id: UUID) -> RetrievalResult:
    document_id = uuid4()
    return RetrievalResult(
        chunk=DocumentChunk(
            chunk_id=uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            content="retrieved evidence",
            modality=Modality.TEXT,
            provenance=Provenance(document_id=document_id, page_number=1),
            created_at=datetime.now(UTC),
        ),
        score=1.0,
        source="test",
    )


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(
        self,
        query: Query,
        *,
        filters: RetrievalFilter | None,
        limit: int,
    ) -> list[RetrievalResult]:
        self.calls += 1
        return [result_for(query.tenant_id)]


class FakeSqlExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, query: Query) -> list[dict[str, object]]:
        self.calls += 1
        return [{"count": 1}]


class FakeAnswerer:
    async def answer(
        self,
        query: Query,
        evidence: list[RetrievalResult],
        sql_rows: list[dict[str, object]],
    ) -> Answer:
        return Answer(
            text=f"evidence={len(evidence)} rows={len(sql_rows)}",
            citations=[],
            model="test",
            created_at=datetime.now(UTC),
        )


def make_query(text: str) -> Query:
    return Query(text=text, tenant_id=uuid4())


def test_query_router_selects_all_routes() -> None:
    """Verify deterministic routing distinguishes structured and document queries."""
    router = QueryRouter()
    assert (
        router.route(make_query("What does the policy document explain?"))
        is QueryRoute.UNSTRUCTURED
    )
    assert (
        router.route(make_query("What is the total revenue in the database?"))
        is QueryRoute.STRUCTURED
    )
    assert (
        router.route(make_query("Compare database revenue with the policy document"))
        is QueryRoute.HYBRID
    )


@pytest.mark.asyncio
async def test_unstructured_graph_route_retrieves_and_answers() -> None:
    """Verify the compiled graph executes the unstructured path."""
    retriever = FakeRetriever()
    sql = FakeSqlExecutor()
    graph = OrchestrationGraph(
        retriever=retriever,
        sql_executor=sql,
        answerer=FakeAnswerer(),
    ).compile()

    result = await graph.ainvoke({"query": make_query("Explain the policy document")})

    assert retriever.calls == 1
    assert sql.calls == 0
    assert result["answer"].text == "evidence=1 rows=0"


@pytest.mark.asyncio
async def test_structured_graph_route_executes_sql_only() -> None:
    """Verify structured routing does not call unstructured retrieval."""
    retriever = FakeRetriever()
    sql = FakeSqlExecutor()
    graph = OrchestrationGraph(
        retriever=retriever,
        sql_executor=sql,
        answerer=FakeAnswerer(),
    ).compile()

    result = await graph.ainvoke({"query": make_query("What is the total database revenue?")})

    assert retriever.calls == 0
    assert sql.calls == 1
    assert result["answer"].text == "evidence=0 rows=1"


def test_graph_rejects_invalid_limits() -> None:
    """Verify orchestration budgets are validated at construction time."""
    with pytest.raises(ValueError, match="positive"):
        OrchestrationGraph(
            retriever=FakeRetriever(),
            sql_executor=FakeSqlExecutor(),
            answerer=FakeAnswerer(),
            max_iterations=0,
        )
