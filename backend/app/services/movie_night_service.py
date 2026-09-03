"""Movie Night lifecycle. Depends only on the TMDB/showtime provider
*interfaces* (never on TMDB or a specific showtime vendor directly), per
the architecture rule that core business logic must not depend on a
specific provider.

Handles three spec failure scenarios:
  - "TMDB unavailable": creating/refreshing a Movie Night never blocks on
    TMDB. If the provider raises ProviderUnavailableError, the Movie Night
    is still created (title as typed by the organizer) with
    tmdb_cache_stale=True; a scheduler job retries enrichment later.
  - "changed showtime": `update_showtime` is the single place a showtime
    changes, so it's also the single place notifications and the
    SHOWTIME_CHANGED status get set.
  - "cancelled Movie Night": `cancel_movie_night` cancels every ticket,
    flags every payment for refund, and notifies every participant —
    Telegram failures during that notification fan-out are handled by
    notification_service's retry queue, not here.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import ProviderUnavailableError
from app.core.logging import get_logger
from app.models.movie_night import MovieNight, MovieNightStatus
from app.models.payment import Payment, PaymentStatus
from app.models.showtime import Showtime, ShowtimeStatus
from app.models.ticket import Ticket, TicketStatus
from app.providers.tmdb.factory import get_tmdb_provider
from app.services import audit_service, notification_service, payment_service

logger = get_logger(__name__)


async def create_movie_night(
    db: AsyncSession,
    created_by_user_id: int,
    title: str,
    tmdb_id: Optional[int] = None,
) -> MovieNight:
    movie_night = MovieNight(title=title, created_by_user_id=created_by_user_id, status=MovieNightStatus.DRAFT)

    if tmdb_id is not None:
        try:
            details = await get_tmdb_provider().get_movie(tmdb_id)
        except ProviderUnavailableError as exc:
            logger.warning("movie_night.tmdb_unavailable_on_create", tmdb_id=tmdb_id, error=str(exc))
            movie_night.tmdb_movie_id = tmdb_id
            movie_night.tmdb_cache_stale = True
        else:
            movie_night.tmdb_movie_id = tmdb_id
            movie_night.title = details.title
            movie_night.tmdb_cache = {
                "overview": details.overview,
                "release_date": details.release_date,
                "runtime_minutes": details.runtime_minutes,
                "poster_path": details.poster_path,
                "genres": details.genres,
            }
            movie_night.tmdb_cache_stale = False

    db.add(movie_night)
    await db.flush()
    await audit_service.record(db, "movie_night.created", "movie_night", movie_night.id, actor_user_id=created_by_user_id)
    return movie_night


async def refresh_stale_tmdb_cache(db: AsyncSession, movie_night: MovieNight) -> bool:
    """Retries TMDB enrichment for a Movie Night created while TMDB was
    down. Returns True if it succeeded. Called by the scheduler."""
    if not movie_night.tmdb_cache_stale or movie_night.tmdb_movie_id is None:
        return False
    try:
        details = await get_tmdb_provider().get_movie(movie_night.tmdb_movie_id)
    except ProviderUnavailableError:
        return False
    movie_night.tmdb_cache = {
        "overview": details.overview,
        "release_date": details.release_date,
        "runtime_minutes": details.runtime_minutes,
        "poster_path": details.poster_path,
        "genres": details.genres,
    }
    movie_night.tmdb_cache_stale = False
    await db.flush()
    logger.info("movie_night.tmdb_cache_refreshed", movie_night_id=movie_night.id)
    return True


async def update_showtime(
    db: AsyncSession,
    movie_night: MovieNight,
    new_starts_at: datetime,
    cinema_name: str,
    admin_user_id: int,
    external_showtime_id: Optional[str] = None,
) -> Showtime:
    showtime = await db.scalar(select(Showtime).where(Showtime.movie_night_id == movie_night.id))
    is_change = showtime is not None and showtime.starts_at is not None and showtime.starts_at != new_starts_at

    if showtime is None:
        showtime = Showtime(movie_night_id=movie_night.id)
        db.add(showtime)

    if is_change:
        showtime.previous_starts_at = showtime.starts_at

    showtime.starts_at = new_starts_at
    showtime.cinema_name = cinema_name
    showtime.external_showtime_id = external_showtime_id
    showtime.status = ShowtimeStatus.ACTIVE
    showtime.last_synced_at = datetime.now(timezone.utc)
    showtime.is_stale = False

    movie_night.scheduled_at = new_starts_at
    movie_night.venue = cinema_name
    if is_change:
        movie_night.status = MovieNightStatus.SHOWTIME_CHANGED
    elif movie_night.status == MovieNightStatus.DRAFT:
        movie_night.status = MovieNightStatus.PLANNED

    await audit_service.record(
        db,
        "showtime.changed" if is_change else "showtime.set",
        "movie_night",
        movie_night.id,
        actor_user_id=admin_user_id,
        context={"new_starts_at": new_starts_at.isoformat(), "cinema_name": cinema_name},
    )
    await db.flush()

    if is_change:
        await _notify_all_ticket_holders(
            db,
            movie_night,
            "showtime_changed",
            f"Showtime changed for '{movie_night.title}': now {new_starts_at.strftime('%a %b %d, %I:%M %p')} at {cinema_name}.",
        )
    return showtime


async def cancel_movie_night(db: AsyncSession, movie_night: MovieNight, admin_user_id: int, reason: str) -> MovieNight:
    movie_night.status = MovieNightStatus.CANCELLED
    movie_night.cancellation_reason = reason
    movie_night.cancelled_at = datetime.now(timezone.utc)

    tickets = (await db.execute(select(Ticket).where(Ticket.movie_night_id == movie_night.id))).scalars().all()
    for ticket in tickets:
        if ticket.status not in (TicketStatus.CANCELLED, TicketStatus.REFUNDED):
            ticket.status = TicketStatus.CANCELLED

    payments = (await db.execute(select(Payment).where(Payment.movie_night_id == movie_night.id))).scalars().all()
    for payment in payments:
        if payment.status not in (PaymentStatus.REFUNDED, PaymentStatus.CANCELLED):
            await payment_service.mark_refund_due(db, payment, reason=f"Movie Night cancelled: {reason}", admin_user_id=admin_user_id)

    await audit_service.record(
        db, "movie_night.cancelled", "movie_night", movie_night.id, actor_user_id=admin_user_id, context={"reason": reason}
    )
    await db.flush()

    await _notify_all_ticket_holders(
        db, movie_night, "movie_night_cancelled", f"'{movie_night.title}' has been cancelled. Reason: {reason}"
    )
    return movie_night


async def _notify_all_ticket_holders(db: AsyncSession, movie_night: MovieNight, notification_type: str, text: str) -> None:
    tickets = (await db.execute(select(Ticket).where(Ticket.movie_night_id == movie_night.id))).scalars().all()
    notified_user_ids = set()
    for ticket in tickets:
        if ticket.user_id in notified_user_ids:
            continue
        notified_user_ids.add(ticket.user_id)
        await notification_service.queue_notification(
            db, user_id=ticket.user_id, notification_type=notification_type, payload={"text": text}, movie_night_id=movie_night.id
        )
    await db.flush()
