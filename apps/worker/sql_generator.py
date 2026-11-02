from __future__ import annotations

from typing import Any

import httpx

from packages.contracts.models import Query


class OpenAICompatibleSqlGenerator:
    """Generate SQL candidates through an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        schema_description: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SQL API key must not be empty")
        if not schema_description.strip():
            raise ValueError("SQL schema description must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._schema_description = schema_description
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def generate_sql(self, query: Query) -> str:
        """Request SQL and extract a single candidate for downstream validation."""
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model_name,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Generate one PostgreSQL SELECT statement only. "
                            "Never write, alter, or delete data. Do not explain.\n"
                            f"Schema:\n{self._schema_description}"
                        ),
                    },
                    {"role": "user", "content": query.text},
                ],
            },
        )
        response.raise_for_status()
        payload: Any = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("SQL provider returned empty content")
        return self._clean_sql(content)

    async def aclose(self) -> None:
        """Close the HTTP client when this generator created it."""
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _clean_sql(content: str) -> str:
        """Remove optional Markdown fences without weakening SQL validation."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return cleaned.strip()
