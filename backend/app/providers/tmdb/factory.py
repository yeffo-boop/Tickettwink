from functools import lru_cache

from app.core.circuit_breaker import get_circuit_breaker
from app.core.config import get_settings
from app.providers.tmdb.base import TMDBProvider
from app.providers.tmdb.live import TMDBLiveProvider
from app.providers.tmdb.sandbox import TMDBSandboxProvider


@lru_cache
def get_tmdb_provider() -> TMDBProvider:
    settings = get_settings()
    if settings.tmdb_api_key:
        breaker = get_circuit_breaker(
            "tmdb",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            reset_seconds=settings.circuit_breaker_reset_seconds,
        )
        return TMDBLiveProvider(settings.tmdb_api_key, settings.tmdb_api_base_url, breaker)
    return TMDBSandboxProvider()
