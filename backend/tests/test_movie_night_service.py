"""Covers FAILURE_SCENARIOS.md "TMDB unavailable", "Changed showtime" and
"Cancelled Movie Night" at the service layer."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import ProviderUnavailableError
from app.models.movie_night import MovieNightStatus
from app.models.notification import Notification
from app.models.payment import PaymentStatus
from app.models.ticket import TicketStatus
from app.providers.tmdb.base import MovieDetails, TMDBProvider
from app.services import movie_night_service, payment_service
from tests.factories import make_movie_night, make_ticket, make_user


class FakeTMDB(TMDBProvider):
    def __init__(self, available: bool = True):
        self.available = available

    async def search_movie(self, query: str):
        return []

    async def get_movie(self, tmdb_id: int) -> MovieDetails:
        if not self.available:
            raise ProviderUnavailableError("tmdb", "connection refused")
        return MovieDetails(
            tmdb_id=tmdb_id,
            title="The Real Title",
            overview="An overview.",
            release_date="2026-01-01",
            runtime_minutes=120,
            poster_path="/poster.jpg",
            genres=["Comedy"],
        )


@pytest.fixture
def tmdb(monkeypatch):
    fake = FakeTMDB()
    monkeypatch.setattr(movie_night_service, "get_tmdb_provider", lambda: fake)
    return fake


async def _notifications(db: AsyncSession, notification_type: str) -> list[Notification]:
    result = await db.execute(select(Notification).where(Notification.notification_type == notification_type))
    return list(result.scalars().all())


async def test_create_with_tmdb_available_enriches(db_session: AsyncSession, tmdb: FakeTMDB):
    admin = await make_user(db_session, admin=True)

    movie_night = await movie_night_service.create_movie_night(db_session, admin.id, "typed title", tmdb_id=42)

    assert movie_night.title == "The Real Title"
    assert movie_night.tmdb_cache_stale is False
    assert movie_night.tmdb_cache["runtime_minutes"] == 120


async def test_create_with_tmdb_down_still_creates_and_marks_stale(db_session: AsyncSession, tmdb: FakeTMDB):
    tmdb.available = False
    admin = await make_user(db_session, admin=True)

    movie_night = await movie_night_service.create_movie_night(db_session, admin.id, "typed title", tmdb_id=42)

    assert movie_night.id is not None
    assert movie_night.title == "typed title"
    assert movie_night.tmdb_movie_id == 42
    assert movie_night.tmdb_cache_stale is True


async def test_stale_cache_refreshes_once_tmdb_recovers(db_session: AsyncSession, tmdb: FakeTMDB):
    tmdb.available = False
    admin = await make_user(db_session, admin=True)
    movie_night = await movie_night_service.create_movie_night(db_session, admin.id, "typed title", tmdb_id=42)

    assert await movie_night_service.refresh_stale_tmdb_cache(db_session, movie_night) is False
    assert movie_night.tmdb_cache_stale is True

    tmdb.available = True
    assert await movie_night_service.refresh_stale_tmdb_cache(db_session, movie_night) is True
    assert movie_night.tmdb_cache_stale is False
    assert movie_night.tmdb_cache["overview"] == "An overview."


async def test_first_showtime_plans_without_notifying(db_session: AsyncSession):
    admin = await make_user(db_session, admin=True)
    member = await make_user(db_session)
    movie_night = await make_movie_night(db_session, admin, status=MovieNightStatus.DRAFT)
    await make_ticket(db_session, movie_night, member)

    await movie_night_service.update_showtime(
        db_session, movie_night, datetime(2026, 12, 5, 19, 0, tzinfo=timezone.utc), "Cinema One", admin.id
    )

    assert movie_night.status == MovieNightStatus.PLANNED
    assert await _notifications(db_session, "showtime_changed") == []


async def test_changed_showtime_notifies_each_holder_once(db_session: AsyncSession):
    admin = await make_user(db_session, admin=True)
    alice = await make_user(db_session, "Alice")
    bob = await make_user(db_session, "Bob")
    movie_night = await make_movie_night(db_session, admin, status=MovieNightStatus.DRAFT)
    await make_ticket(db_session, movie_night, alice)
    await make_ticket(db_session, movie_night, alice, status=TicketStatus.DUPLICATE)
    await make_ticket(db_session, movie_night, bob)

    first = datetime(2026, 12, 5, 19, 0, tzinfo=timezone.utc)
    second = datetime(2026, 12, 5, 21, 30, tzinfo=timezone.utc)
    await movie_night_service.update_showtime(db_session, movie_night, first, "Cinema One", admin.id)
    showtime = await movie_night_service.update_showtime(db_session, movie_night, second, "Cinema Two", admin.id)

    assert movie_night.status == MovieNightStatus.SHOWTIME_CHANGED
    assert movie_night.venue == "Cinema Two"
    assert showtime.previous_starts_at.replace(tzinfo=timezone.utc) == first
    notified = await _notifications(db_session, "showtime_changed")
    assert sorted(n.user_id for n in notified) == sorted([alice.id, bob.id])
    assert "Cinema Two" in notified[0].payload["text"]


async def test_cancel_cancels_tickets_flags_refunds_and_notifies(db_session: AsyncSession):
    admin = await make_user(db_session, admin=True)
    paid = await make_user(db_session, "Paid")
    unpaid = await make_user(db_session, "Unpaid")
    movie_night = await make_movie_night(db_session, admin)
    await make_ticket(db_session, movie_night, paid)
    already_refunded_ticket = await make_ticket(db_session, movie_night, unpaid, status=TicketStatus.REFUNDED)

    paid_payment = payment_service.create_payment_record(movie_night.id, paid.id, 1500)
    unpaid_payment = payment_service.create_payment_record(movie_night.id, unpaid.id, 1500)
    db_session.add_all([paid_payment, unpaid_payment])
    await db_session.flush()
    await payment_service.confirm_payment(db_session, paid_payment, additional_amount_cents=1500, admin_user_id=admin.id)

    await movie_night_service.cancel_movie_night(db_session, movie_night, admin.id, "theater closed")

    assert movie_night.status == MovieNightStatus.CANCELLED
    assert movie_night.cancellation_reason == "theater closed"
    assert movie_night.cancelled_at is not None
    # Money was received, so it is owed back; nothing received means simply cancelled.
    assert paid_payment.status == PaymentStatus.REFUND_DUE
    assert unpaid_payment.status == PaymentStatus.CANCELLED
    # An already-refunded ticket keeps its status.
    assert already_refunded_ticket.status == TicketStatus.REFUNDED
    notified = await _notifications(db_session, "movie_night_cancelled")
    assert sorted(n.user_id for n in notified) == sorted([paid.id, unpaid.id])
    assert "theater closed" in notified[0].payload["text"]
