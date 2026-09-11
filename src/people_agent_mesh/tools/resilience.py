"""
Resilience & Operability Middleware for Agent Tools.
Implements Circuit Breakers, Idempotency Protection, and Fallback Handlers
to ensure production uptime and failure isolation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "CLOSED"  # Normal healthy operation
    OPEN = "OPEN"  # Tripped; requests fail fast to protect upstream
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with trial request


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is blocked because the circuit breaker is OPEN."""


class CircuitBreaker:
    """
    Sliding-window failure detector and circuit breaker.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds

        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_execution(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            now = time.time()
            if now - self.last_failure_time > self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN: allow trial request
        return True

    def execute(self, func: Callable[[], T], fallback: Callable[[], T] | None = None) -> T:
        if not self.allow_execution():
            if fallback:
                return fallback()
            raise CircuitBreakerOpenException(
                f"Circuit breaker '{self.name}' is OPEN. Call blocked."
            )

        try:
            result = func()
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            if fallback:
                return fallback()
            raise


class IdempotencyManager:
    """
    Guarantees mutating agent actions execute at most once per unique idempotency key.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._cache.get(key)

    def store(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def is_processed(self, key: str) -> bool:
        return key in self._cache
