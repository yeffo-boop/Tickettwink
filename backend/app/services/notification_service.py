"""Notification queueing and delivery with retry/backoff/dead-letter.

Handles two failure scenarios from the spec:
  - "Telegram temporary failure": a send that fails because Telegram (or
    the network) is temporarily down gets requeued with exponential
    backoff instead of being lost or blocking the caller.
  - "failed notification": once NOTIFICATION_MAX_RETRIES is exhausted, the
    notification is marked DEAD_LETTER (never silently dropped) and is
    visible to admins via the admin API / dashboard for manual follow-up.

Callers never talk to the Telegram provider directly — they call
`queue_notification`, which writes a row and returns immediately. Actual
delivery happens via `drain_pending`, invoked by the scheduler on a short
interval, so a request handler is never blocked on an outbound network
call to a third party.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import ProviderUnavailableError
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.models.user import User
from app.providers.telegram.base import TelegramDeliveryError
from app.providers.telegram.factory import get_telegram_provider

logger = get_logger(__name__)
settings = get_settings()


async def queue_notification(
    db: AsyncSession,
    user_id: Optional[int],
    notification_type: str,
    payload: dict,
    movie_night_id: Optional[int] = None,
    channel: NotificationChannel = NotificationChannel.TELEGRAM,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        movie_night_id=movie_night_id,
        channel=channel,
        notification_type=notification_type,
        payload=payload,
        status=NotificationStatus.PENDING,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.flush()
    return notification


def _backoff_seconds(attempt_count: int) -> int:
    return settings.notification_retry_base_seconds * (2 ** max(0, attempt_count - 1))


async def _deliver_one(db: AsyncSession, notification: Notification) -> None:
    user = await db.scalar(select(User).where(User.id == notification.user_id))
    if user is None or not user.telegram_user_id:
        notification.status = NotificationStatus.DEAD_LETTER
        notification.error_message = "recipient has no linked Telegram chat"
        logger.warning("notification.dead_letter_no_recipient", notification_id=notification.id)
        return

    provider = get_telegram_provider()
    notification.attempt_count += 1
    notification.last_attempt_at = datetime.now(timezone.utc)

    try:
        await provider.send_message(str(user.telegram_user_id), notification.payload.get("text", ""))
    except TelegramDeliveryError as exc:
        # Address-specific (e.g. user blocked the bot) — retrying identically
        # will not help, but we still respect max_retries before giving up
        # so a transient block/unblock has a chance to resolve.
        notification.error_message = str(exc)
        _schedule_retry_or_deadletter(notification)
    except ProviderUnavailableError as exc:
        notification.error_message = f"Telegram temporarily unavailable: {exc}"
        _schedule_retry_or_deadletter(notification)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        notification.error_message = f"unexpected error: {exc}"
        _schedule_retry_or_deadletter(notification)
    else:
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(timezone.utc)
        notification.error_message = None


def _schedule_retry_or_deadletter(notification: Notification) -> None:
    if notification.attempt_count >= settings.notification_max_retries:
        notification.status = NotificationStatus.DEAD_LETTER
        logger.warning(
            "notification.dead_letter",
            notification_id=notification.id,
            attempts=notification.attempt_count,
            error=notification.error_message,
        )
    else:
        notification.status = NotificationStatus.FAILED_RETRYING
        delay = _backoff_seconds(notification.attempt_count)
        notification.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        logger.info(
            "notification.retry_scheduled",
            notification_id=notification.id,
            attempt=notification.attempt_count,
            retry_in_seconds=delay,
        )


async def drain_pending(db: AsyncSession, limit: int = 50) -> int:
    """Delivers everything due for (re)send. Returns count processed.
    Called by the scheduler; safe to call concurrently since each row is
    only ever picked up by one drain within the same process."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Notification)
        .where(
            Notification.status.in_([NotificationStatus.PENDING, NotificationStatus.FAILED_RETRYING]),
            Notification.next_attempt_at <= now,
        )
        .limit(limit)
    )
    notifications = result.scalars().all()
    for notification in notifications:
        await _deliver_one(db, notification)
    await db.commit()
    return len(notifications)
