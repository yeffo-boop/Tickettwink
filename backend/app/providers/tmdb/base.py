"""TMDB provider interface.

The rest of the app (movie_night_service, API routes) depends only on this
abstract class — never on `httpx` or TMDB's response shape directly — so
TMDB going down, changing its API, or being swapped for another movie
database only touches this package.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class MovieSearchResult:
    tmdb_id: int
    title: str
    release_year: Optional[str]
    poster_path: Optional[str]


@dataclass
class MovieDetails:
    tmdb_id: int
    title: str
    overview: Optional[str]
    release_date: Optional[str]
    runtime_minutes: Optional[int]
    poster_path: Optional[str]
    genres: list[str]


class TMDBProvider(ABC):
    @abstractmethod
    async def search_movie(self, query: str) -> list[MovieSearchResult]:
        """Raises ProviderUnavailableError if TMDB cannot be reached."""

    @abstractmethod
    async def get_movie(self, tmdb_id: int) -> MovieDetails:
        """Raises ProviderUnavailableError if TMDB cannot be reached."""
