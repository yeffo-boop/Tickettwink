"""Live TMDB provider — calls the real TMDB API v3 (https://developer.themoviedb.org/reference).

Requires TMDB_API_KEY (a "v3 auth" API key from https://www.themoviedb.org/settings/api).
Wrapped in a circuit breaker + bounded retries so a TMDB outage degrades
gracefully instead of hanging requests or crashing the app (spec:
"TMDB unavailable").
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.tmdb.base import MovieDetails, MovieSearchResult, TMDBProvider

logger = get_logger(__name__)
settings = get_settings()

RETRYABLE_EXCEPTIONS = (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)


class TMDBLiveProvider(TMDBProvider):
    def __init__(self, api_key: str, base_url: str, breaker: CircuitBreaker):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._breaker = breaker

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    async def _get(self, path: str, params: dict) -> dict:
        params = {**params, "api_key": self._api_key}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self._base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def _call(self, path: str, params: dict) -> dict:
        self._breaker.before_call()
        try:
            data = await self._get(path, params)
        except Exception as exc:
            self._breaker.on_failure(exc)
            raise
        else:
            self._breaker.on_success()
            return data

    async def search_movie(self, query: str) -> list[MovieSearchResult]:
        data = await self._call("/search/movie", {"query": query})
        results = []
        for item in data.get("results", [])[:10]:
            release_date = item.get("release_date") or ""
            results.append(
                MovieSearchResult(
                    tmdb_id=item["id"],
                    title=item.get("title", "Unknown"),
                    release_year=release_date[:4] if release_date else None,
                    poster_path=item.get("poster_path"),
                )
            )
        return results

    async def get_movie(self, tmdb_id: int) -> MovieDetails:
        data = await self._call(f"/movie/{tmdb_id}", {})
        return MovieDetails(
            tmdb_id=data["id"],
            title=data.get("title", "Unknown"),
            overview=data.get("overview"),
            release_date=data.get("release_date"),
            runtime_minutes=data.get("runtime"),
            poster_path=data.get("poster_path"),
            genres=[g["name"] for g in data.get("genres", [])],
        )
