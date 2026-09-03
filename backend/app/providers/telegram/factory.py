from functools import lru_cache

from app.core.circuit_breaker import get_circuit_breaker
from app.core.config import get_settings
from app.providers.telegram.base import TelegramProvider
from app.providers.telegram.live import TelegramLiveProvider
from app.providers.telegram.sandbox import TelegramSandboxProvider


@lru_cache
def get_telegram_provider() -> TelegramProvider:
    settings = get_settings()
    if settings.telegram_bot_token:
        breaker = get_circuit_breaker(
            "telegram",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            reset_seconds=settings.circuit_breaker_reset_seconds,
        )
        return TelegramLiveProvider(settings.telegram_bot_token, breaker)
    return TelegramSandboxProvider()
