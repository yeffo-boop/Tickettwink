"""Covers FAILURE_SCENARIOS.md "Missing ticket": find_missing_tickets,
mark_ticket_missing, and the hourly scheduler job that sends reminders."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.movie_night import MovieNightStatus
from app.models.notification import Notification
from app.models.payment import PaymentStatus
from app.models.ticket import TicketStatus
from app.scheduler import jobs
from app.services import payment_service, ticket_service
from tests.factories import make_movie_night, make_ticket, make_user


async def test_find_missing_tickets(db_session: AsyncSession):
    admin = await make_user(db_session, admin=True)
    uploaded = await make_user(db_session, "Uploaded")
    verified = await make_user(db_session, "Verified")
    mismatched = await make_user(db_session, "Mismatched")
    nothing = await make_user(db_session, "Nothing")
    movie_night = await make_movie_night(db_session, admin)
    await make_ticket(db_session, movie_night, uploaded, TicketStatus.UPLOADED)
    await make_ticket(db_session, movie_night, verified, TicketStatus.VERIFIED)
    mismatch_ticket = await make_ticket(db_session, movie_night, mismatched, TicketStatus.MISMATCH)

    missing = await ticket_service.find_missing_tickets(
        db_session, movie_night, [uploaded.id, verified.id, mismatched.id, nothing.id]
    )

    by_user = {entry.user_id: entry.ticket_id for entry in missing}
    # A mismatched ticket doesn't count as covered, and points at the existing row.
    assert by_user == {mismatched.id: mismatch_ticket.id, nothing.id: None}


async def test_mark_ticket_missing_creates_or_updates(db_session: AsyncSession):
    admin = await make_user(db_session, admin=True)
    no_row = await make_user(db_session, "No row")
    pending = await make_user(db_session, "Pending")
    movie_night = await make_movie_night(db_session, admin)
    pending_ticket = await make_ticket(db_session, movie_night, pending, TicketStatus.PENDING_UPLOAD)

    created = await ticket_service.mark_ticket_missing(db_session, movie_night, no_row.id)
    updated = await ticket_service.mark_ticket_missing(db_session, movie_night, pending.id)

    assert created.id is not None
    assert created.status == TicketStatus.MISSING
    assert updated.id == pending_ticket.id
    assert updated.status == TicketStatus.MISSING
    assert updated.verification_notes == "No ticket uploaded before the cutoff."


@pytest.fixture
def job_sessions(monkeypatch, session_factory):
    monkeypatch.setattr(jobs, "AsyncSessionLocal", session_factory)
    return session_factory


async def test_missing_ticket_job_reminds_paid_users_without_tickets(job_sessions):
    async with job_sessions() as db:
        admin = await make_user(db, admin=True)
        has_ticket = await make_user(db, "Has ticket")
        no_ticket = await make_user(db, "No ticket")
        unpaid = await make_user(db, "Unpaid")
        soon = await make_movie_night(db, admin, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=24))
        far = await make_movie_night(db, admin, scheduled_at=datetime.now(timezone.utc) + timedelta(days=10))
        cancelled = await make_movie_night(
            db, admin, status=MovieNightStatus.CANCELLED, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        await make_ticket(db, soon, has_ticket)
        for movie_night in (soon, far, cancelled):
            for user in (has_ticket, no_ticket):
                payment = payment_service.create_payment_record(movie_night.id, user.id, 1500)
                payment.amount_received_cents = 1500
                payment.status = PaymentStatus.PAID
                db.add(payment)
            db.add(payment_service.create_payment_record(movie_night.id, unpaid.id, 1500))
        await db.commit()
        soon_id, no_ticket_id = soon.id, no_ticket.id

    await jobs._job_check_missing_tickets()

    async with job_sessions() as db:
        reminders = (
            await db.execute(select(Notification).where(Notification.notification_type == "ticket_reminder"))
        ).scalars().all()
    assert [(n.user_id, n.movie_night_id) for n in reminders] == [(no_ticket_id, soon_id)]
