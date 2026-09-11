import pytest

from people_agent_mesh.tools.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
    IdempotencyManager,
)


def _get_circuit_state(breaker: CircuitBreaker) -> CircuitState:
    return breaker.state


def test_circuit_breaker_trips_and_recovers() -> None:
    breaker = CircuitBreaker("TestAPI", failure_threshold=2, recovery_timeout_seconds=0.1)

    def failing_call() -> str:
        raise ConnectionError("Upstream API down")

    def success_call() -> str:
        return "SUCCESS"

    def fallback_call() -> str:
        return "FALLBACK_DATA"

    # Call 1 fails
    with pytest.raises(ConnectionError):
        breaker.execute(failing_call)
    assert _get_circuit_state(breaker) == CircuitState.CLOSED
    assert breaker.consecutive_failures == 1

    # Call 2 fails -> trips breaker to OPEN
    with pytest.raises(ConnectionError):
        breaker.execute(failing_call)
    assert _get_circuit_state(breaker) == CircuitState.OPEN

    # Call 3 while OPEN: fails fast or uses fallback
    with pytest.raises(CircuitBreakerOpenException):
        breaker.execute(failing_call)

    # Call with fallback succeeds
    res = breaker.execute(failing_call, fallback=fallback_call)
    assert res == "FALLBACK_DATA"


def test_idempotency_manager() -> None:
    mgr = IdempotencyManager()
    key = "idem_tx_9981"

    assert mgr.is_processed(key) is False
    assert mgr.get(key) is None

    mgr.store(key, {"status": "SUCCESS", "id": 123})

    assert mgr.is_processed(key) is True
    assert mgr.get(key) == {"status": "SUCCESS", "id": 123}
