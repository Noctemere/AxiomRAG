from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from packages.contracts.models import Answer, Query, RetrievalFilter, RetrievalResult


class QueryRoute(StrEnum):
    """Permitted retrieval paths in the first orchestration graph."""

    UNSTRUCTURED = "unstructured"
    STRUCTURED = "structured"
    HYBRID = "hybrid"


class GraphState(TypedDict, total=False):
    """Serializable state passed between explicit LangGraph nodes."""

    query: Query
    route: QueryRoute
    retrieval_filter: RetrievalFilter | None
    evidence: list[RetrievalResult]
    sql_rows: list[dict[str, object]]
    answer: Answer
    error: str | None
    iterations: int


class Retriever(Protocol):
    async def retrieve(
        self,
        query: Query,
        *,
        filters: RetrievalFilter | None,
        limit: int,
    ) -> list[RetrievalResult]:
        """Retrieve tenant-authorized unstructured evidence."""
        ...


class SqlExecutor(Protocol):
    async def execute(self, query: Query) -> list[dict[str, object]]:
        """Execute a validated, read-only structured query."""
        ...


class Answerer(Protocol):
    async def answer(
        self,
        query: Query,
        evidence: list[RetrievalResult],
        sql_rows: list[dict[str, object]],
    ) -> Answer:
        """Generate a grounded answer from available evidence."""
        ...


@dataclass(frozen=True)
class QueryRouter:
    """Deterministic first-pass router; an LLM classifier can replace it later."""

    structured_terms: frozenset[str] = frozenset(
        {"sql", "database", "revenue", "count", "average", "total", "rows", "table"}
    )
    unstructured_terms: frozenset[str] = frozenset(
        {"document", "policy", "pdf", "explain", "according", "section"}
    )

    def route(self, query: Query) -> QueryRoute:
        """Select structured, unstructured, or hybrid execution from query terms."""
        words = {word.lower() for word in query.text.split()}
        structured = bool(words & self.structured_terms)
        unstructured = bool(words & self.unstructured_terms)
        if structured and unstructured:
            return QueryRoute.HYBRID
        if structured:
            return QueryRoute.STRUCTURED
        return QueryRoute.UNSTRUCTURED


class OrchestrationGraph:
    """Builds an explicit bounded graph from injected retrieval ports."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        sql_executor: SqlExecutor,
        answerer: Answerer,
        router: QueryRouter | None = None,
        retrieval_limit: int = 8,
        max_iterations: int = 3,
    ) -> None:
        if retrieval_limit < 1 or max_iterations < 1:
            raise ValueError("graph limits must be positive")
        self._retriever = retriever
        self._sql_executor = sql_executor
        self._answerer = answerer
        self._router = router or QueryRouter()
        self._retrieval_limit = retrieval_limit
        self._max_iterations = max_iterations

    def compile(self):
        """Compile the state machine with explicit conditional route edges."""
        graph = StateGraph(GraphState)
        graph.add_node("route_query", self.route_query)
        graph.add_node("retrieve_unstructured", self.retrieve_unstructured)
        graph.add_node("execute_structured", self.execute_structured)
        graph.add_node("generate_answer", self.generate_answer)
        graph.add_edge(START, "route_query")
        graph.add_conditional_edges(
            "route_query",
            self._route_name,
            {
                QueryRoute.UNSTRUCTURED: "retrieve_unstructured",
                QueryRoute.STRUCTURED: "execute_structured",
                QueryRoute.HYBRID: "retrieve_unstructured",
            },
        )
        graph.add_edge("retrieve_unstructured", "generate_answer")
        graph.add_edge("execute_structured", "generate_answer")
        graph.add_edge("generate_answer", END)
        return graph.compile()

    @staticmethod
    def _route_name(state: GraphState) -> QueryRoute:
        """Return the already-decided route for LangGraph conditional edges."""
        route = state.get("route")
        if route is None:
            raise RuntimeError("route_query did not set a route")
        return route

    async def route_query(self, state: GraphState) -> GraphState:
        """Set the route and initialize the bounded iteration counter."""
        query = state.get("query")
        if query is None:
            return {"error": "query is required", "iterations": state.get("iterations", 0) + 1}
        return {
            "route": self._router.route(query),
            "iterations": state.get("iterations", 0) + 1,
        }

    async def retrieve_unstructured(self, state: GraphState) -> GraphState:
        """Retrieve evidence through the injected tenant-aware retriever."""
        if state.get("iterations", 0) > self._max_iterations:
            return {"error": "orchestration iteration budget exceeded", "evidence": []}
        query = state.get("query")
        if query is None:
            return {"error": "query is required", "evidence": []}
        evidence = await self._retriever.retrieve(
            query,
            filters=state.get("retrieval_filter"),
            limit=self._retrieval_limit,
        )
        if state.get("route") is QueryRoute.HYBRID:
            return {
                "evidence": evidence,
                "sql_rows": await self._sql_executor.execute(query),
            }
        return {"evidence": evidence}

    async def execute_structured(self, state: GraphState) -> GraphState:
        """Execute through the injected SQL safety boundary."""
        if state.get("iterations", 0) > self._max_iterations:
            return {"error": "orchestration iteration budget exceeded", "sql_rows": []}
        query = state.get("query")
        if query is None:
            return {"error": "query is required", "sql_rows": []}
        return {"sql_rows": await self._sql_executor.execute(query)}

    async def generate_answer(self, state: GraphState) -> GraphState:
        """Generate an answer from only the evidence collected by prior nodes."""
        if state.get("error"):
            return state
        query = state.get("query")
        if query is None:
            return {"error": "query is required"}
        answer = await self._answerer.answer(
            query,
            state.get("evidence", []),
            state.get("sql_rows", []),
        )
        return {"answer": answer}
