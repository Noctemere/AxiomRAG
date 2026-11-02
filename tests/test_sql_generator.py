from uuid import uuid4

import httpx
import pytest

from apps.worker.sql_generator import OpenAICompatibleSqlGenerator
from packages.contracts.models import Query


@pytest.mark.asyncio
async def test_sql_generator_extracts_markdown_fenced_sql() -> None:
    """Verify provider output is cleaned before AST validation."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "```sql\nSELECT 1\n```"}}]},
            )
        )
    )
    generator = OpenAICompatibleSqlGenerator(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
        schema_description="documents(id)",
        client=client,
    )
    sql = await generator.generate_sql(Query(text="count rows", tenant_id=uuid4()))
    assert sql == "SELECT 1"
    await client.aclose()


def test_sql_generator_rejects_empty_key() -> None:
    """Verify real SQL generation requires credentials."""
    with pytest.raises(ValueError, match="API key"):
        OpenAICompatibleSqlGenerator(
            api_key="",
            base_url="https://example.test/v1",
            model_name="test-model",
            schema_description="documents(id)",
        )