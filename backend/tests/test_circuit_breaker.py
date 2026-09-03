import time

from app.core.circuit_breaker import CircuitBreaker, CircuitState, ProviderUnavailableError


def test_closes_after_success():
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_seconds=60)
    breaker.before_call()
    breaker.on_success()
    assert breaker.state == CircuitState.CLOSED


def test_opens_after_threshold_failures():
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_seconds=60)
    for _ in range(3):
        breaker.on_failure(Exception("boom"))
    assert breaker.state == CircuitState.OPEN


def test_open_breaker_rejects_calls_fast():
    breaker = CircuitBreaker(name="test", failure_threshold=1, reset_seconds=60)
    breaker.on_failure(Exception("boom"))
    try:
        breaker.before_call()
        assert False, "expected ProviderUnavailableError"
    except ProviderUnavailableError as exc:
        assert exc.provider_name == "test"


def test_half_opens_after_reset_window():
    breaker = CircuitBreaker(name="test", failure_threshold=1, reset_seconds=0.01)
    breaker.on_failure(Exception("boom"))
    assert breaker.state == CircuitState.OPEN
    time.sleep(0.02)
    assert breaker.state == CircuitState.HALF_OPEN


def test_half_open_failure_reopens():
    breaker = CircuitBreaker(name="test", failure_threshold=1, reset_seconds=0.01)
    breaker.on_failure(Exception("boom"))
    time.sleep(0.02)
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.on_failure(Exception("still down"))
    assert breaker.state == CircuitState.OPEN
