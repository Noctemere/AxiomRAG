from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import TypeVar


class CircuitOpenError(RuntimeError):
    """Raised when a tool circuit is open after repeated failures."""


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry and exponential-backoff configuration."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.1
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0 or self.backoff_multiplier < 1:
            raise ValueError(
                "retry delays must be non-negative and multiplier must be at least one"
            )


class CircuitBreaker:
    """Open a circuit after consecutive failures and recover after a cooldown."""

    def __init__(self, *, failure_threshold: int = 3, recovery_seconds: float = 30.0) -> None:
        if failure_threshold < 1 or recovery_seconds <= 0:
            raise ValueError("circuit limits must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        """Return whether calls should currently be rejected."""
        if self._opened_at is None:
            return False
        if monotonic() - self._opened_at >= self.recovery_seconds:
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        """Reset consecutive failures after a successful call."""
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Count a failure and open the circuit at the configured threshold."""
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = monotonic()


class ResilientToolRunner:
    """Run an async tool operation with bounded retries and circuit breaking."""

    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self._sleep = sleep

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Retry transient failures and fail fast while the circuit is open."""
        if self.circuit_breaker.is_open:
            raise CircuitOpenError("tool circuit is open")
        delay = self.retry_policy.initial_delay_seconds
        last_error: Exception | None = None
        for attempt in range(self.retry_policy.max_attempts):
            try:
                result = await operation()
            except Exception as exc:
                last_error = exc
                self.circuit_breaker.record_failure()
                if attempt + 1 == self.retry_policy.max_attempts:
                    break
                if delay > 0:
                    await self._sleep(delay)
                delay *= self.retry_policy.backoff_multiplier
            else:
                self.circuit_breaker.record_success()
                return result
        raise last_error or RuntimeError("tool operation failed")
