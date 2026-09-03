"""
Shared circuit breaker used by every outbound provider integration.

This is the core mechanism behind "graceful handling of TMDB/showtime-API/
Telegram unavailability": after N consecutive failures within a window, the
breaker OPENs and callers get a fast, typed failure (ProviderUnavailableError)
instead of hammering a dead upstream and blocking request threads on
timeouts. After `reset_seconds`, the breaker moves to HALF_OPEN and allows a
single trial call through; success CLOSES it again, failure re-OPENs it.

State is kept in-process (per-worker). That's a deliberate, documented
tradeoff for a single-small-deployment app: it avoids adding Redis just for
this. If Ticket Twink is ever run with multiple API workers, move this state
to a shared store (Redis) so breakers agree across processes.
"""
import time
from dataclasses import dataclass, field
from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProviderUnavailableError(Exception):
    """Raised when a provider's circuit breaker is open."""

    def __init__(self, provider_name: str, message: str = ""):
        self.provider_name = provider_name
        super().__init__(message or f"{provider_name} is currently unavailable (circuit open)")


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    reset_seconds: int = 120
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and (time.monotonic() - self._opened_at) >= self.reset_seconds:
            self._state = CircuitState.HALF_OPEN
            logger.info("circuit_breaker.half_open", provider=self.name)
        return self._state

    def before_call(self) -> None:
        if self.state == CircuitState.OPEN:
            raise ProviderUnavailableError(self.name)

    def on_success(self) -> None:
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("circuit_breaker.closed", provider=self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def on_failure(self, error: Exception) -> None:
        self._failure_count += 1
        logger.warning(
            "circuit_breaker.failure",
            provider=self.name,
            failure_count=self._failure_count,
            threshold=self.failure_threshold,
            error=str(error),
        )
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("circuit_breaker.opened", provider=self.name)


_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, failure_threshold: int = 3, reset_seconds: int = 120) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name, failure_threshold=failure_threshold, reset_seconds=reset_seconds)
    return _breakers[name]
