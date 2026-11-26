import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app import models  # noqa: F401 -- registers all models on Base.metadata


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    """A session factory bound to a fresh in-memory database. Use this when
    the code under test opens its own sessions (e.g. scheduler jobs)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    from app.core.circuit_breaker import _breakers

    _breakers.clear()
    yield
    _breakers.clear()
