import pytest

from apps.worker.tool_resilience import (
    CircuitBreaker,
    CircuitOpenError,
    ResilientToolRunner,
    RetryPolicy,
)


@pytest.mark.asyncio
async def test_runner_retries_then_succeeds() -> None:
    """Verify transient failures consume a bounded retry budget."""
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient")
        return "ok"

    runner = ResilientToolRunner(
        retry_policy=RetryPolicy(max_attempts=3, initial_delay_seconds=0),
    )
    assert await runner.run(operation) == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_runner_opens_circuit_after_failures() -> None:
    """Verify repeated failures stop later calls before executing the tool."""
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("downstream unavailable")

    runner = ResilientToolRunner(
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0),
        circuit_breaker=CircuitBreaker(failure_threshold=2, recovery_seconds=60),
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await runner.run(operation)
    with pytest.raises(CircuitOpenError, match="circuit is open"):
        await runner.run(operation)
    assert attempts == 2


@pytest.mark.asyncio
async def test_runner_rejects_invalid_retry_configuration() -> None:
    """Verify resilience limits fail during configuration."""
    with pytest.raises(ValueError, match="positive"):
        ResilientToolRunner(retry_policy=RetryPolicy(max_attempts=0))
