"""Sandbox TMDB provider: deterministic canned data, no network calls, no
API key required. Used whenever APP_MODE=sandbox or TMDB_API_KEY is unset,
so local development and CI never depend on TMDB being reachable."""
from app.providers.tmdb.base import MovieDetails, MovieSearchResult, TMDBProvider

_MOCK_MOVIES = [
    MovieDetails(
        tmdb_id=101,
        title="The Sandbox Movie",
        overview="A placeholder movie returned by the sandbox TMDB provider.",
        release_date="2024-01-01",
        runtime_minutes=110,
        poster_path=None,
        genres=["Comedy"],
    ),
    MovieDetails(
        tmdb_id=102,
        title="Another Test Feature",
        overview="Second placeholder movie for search-result testing.",
        release_date="2023-06-15",
        runtime_minutes=95,
        poster_path=None,
        genres=["Drama"],
    ),
]


class TMDBSandboxProvider(TMDBProvider):
    async def search_movie(self, query: str) -> list[MovieSearchResult]:
        matches = [m for m in _MOCK_MOVIES if query.lower() in m.title.lower()] or _MOCK_MOVIES
        return [
            MovieSearchResult(tmdb_id=m.tmdb_id, title=m.title, release_year=m.release_date[:4], poster_path=None)
            for m in matches
        ]

    async def get_movie(self, tmdb_id: int) -> MovieDetails:
        for m in _MOCK_MOVIES:
            if m.tmdb_id == tmdb_id:
                return m
        return _MOCK_MOVIES[0]
