import httpx
import pytest

from apps.worker.embedding import OpenAICompatibleEmbeddingProvider


@pytest.mark.asyncio
async def test_openai_compatible_provider_batches_and_restores_order() -> None:
    """Verify request batching, authentication, and indexed response ordering."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.read().decode("utf-8")
        assert '"model":"test-model"' in body
        input_count = len(httpx.Response(200, content=body).json()["input"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [0.2 + index, 0.3 + index]}
                    for index in reversed(range(input_count))
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.test/v1/",
        model_name="test-model",
        dimension=2,
        batch_size=2,
        client=client,
    )
    vectors = await provider.embed(["one", "two", "three"])

    assert len(requests) == 2
    assert requests[0].url == "https://example.test/v1/embeddings"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert vectors == [[0.2, 0.3], [1.2, 1.3], [0.2, 0.3]]
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_wrong_dimension() -> None:
    """Verify malformed provider responses fail before indexing."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0]}]},
            )
        )
    )
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
        dimension=2,
        client=client,
    )

    with pytest.raises(ValueError, match="vector dimension"):
        await provider.embed(["text"])
    await client.aclose()


def test_openai_compatible_provider_rejects_empty_key() -> None:
    """Verify credentials are required when the real provider is selected."""
    with pytest.raises(ValueError, match="API key"):
        OpenAICompatibleEmbeddingProvider(
            api_key=" ",
            base_url="https://example.test/v1",
            model_name="test-model",
            dimension=2,
        )
