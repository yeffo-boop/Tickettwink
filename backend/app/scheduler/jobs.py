"""Scheduler architecture (spec item 17).

A single in-process APScheduler instance runs background jobs that must
happen without a request in flight: draining the notification retry
queue, retrying stale TMDB enrichment, and checking for missing tickets
ahead of a Movie Night. Kept in its own module so it never imports
anything Telegram-specific — the scheduler doesn't know what a Telegram
message is, it just calls services.

Deliberate tradeoff: this runs inside the API process (one worker). For a
small private group that's simpler to deploy and operate than a separate
worker process/Redis queue, and is documented here rather than silently
assumed — if Ticket Twink is ever run with multiple API workers behind a
load balancer, move these jobs to a single dedicated worker process so
they don't run N times.
"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.movie_night import MovieNight, MovieNightStatus
from app.models.payment import Payment, PaymentStatus
from app.services import movie_night_service, notification_service, ticket_service

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _job_drain_notifications() -> None:
    async with AsyncSessionLocal() as db:
        count = await notification_service.drain_pending(db)
        if count:
            logger.info("scheduler.notifications_drained", count=count)


async def _job_refresh_stale_tmdb() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MovieNight).where(MovieNight.tmdb_cache_stale.is_(True)))
        stale = result.scalars().all()
        for movie_night in stale:
            await movie_night_service.refresh_stale_tmdb_cache(db, movie_night)
        if stale:
            await db.commit()


async def _job_check_missing_tickets() -> None:
    """~48h before an upcoming Movie Night, find anyone with a confirmed
    payment but no uploaded ticket and nudge them; flags a MISSING ticket
    record so admins can see the gap on the dashboard."""
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(timezone.utc) + timedelta(hours=48)
        result = await db.execute(
            select(MovieNight).where(
                MovieNight.status.in_([MovieNightStatus.PLANNED, MovieNightStatus.CONFIRMED]),
                MovieNight.scheduled_at.is_not(None),
                MovieNight.scheduled_at <= cutoff,
            )
        )
        for movie_night in result.scalars().all():
            paid_result = await db.execute(
                select(Payment.user_id).where(
                    Payment.movie_night_id == movie_night.id,
                    Payment.status.in_([PaymentStatus.PAID, PaymentStatus.OVERPAID, PaymentStatus.PARTIAL]),
                )
            )
            expected_user_ids = [row[0] for row in paid_result.all()]
            if not expected_user_ids:
                continue
            missing = await ticket_service.find_missing_tickets(db, movie_night, expected_user_ids)
            for entry in missing:
                await notification_service.queue_notification(
                    db,
                    user_id=entry.user_id,
                    notification_type="ticket_reminder",
                    payload={"text": f"Reminder: upload your ticket for '{movie_night.title}' before showtime!"},
                    movie_night_id=movie_night.id,
                )
        await db.commit()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_job_drain_notifications, "interval", seconds=30, id="drain_notifications", max_instances=1)
    _scheduler.add_job(_job_refresh_stale_tmdb, "interval", minutes=15, id="refresh_stale_tmdb", max_instances=1)
    _scheduler.add_job(_job_check_missing_tickets, "interval", hours=1, id="check_missing_tickets", max_instances=1)
    _scheduler.start()
    logger.info("scheduler.started", jobs=[job.id for job in _scheduler.get_jobs()])


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler.stopped")
