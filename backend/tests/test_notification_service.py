"""Covers FAILURE_SCENARIOS.md "Telegram temporary failure" and "Failed
notification": retry with backoff, dead-lettering, and recipients with no
linked Telegram chat."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import ProviderUnavailableError
from app.core.config import get_settings
from app.models.notification import NotificationStatus
from app.providers.telegram.base import TelegramDeliveryError, TelegramProvider
from app.services import notification_service
from tests.factories import make_user


class FakeTelegram(TelegramProvider):
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = "HTML") -> str:
        if self.error is not None:
            raise self.error
        self.sent.append((chat_id, text))
        return str(len(self.sent))


@pytest.fixture
def telegram(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(notification_service, "get_telegram_provider", lambda: fake)
    return fake


async def _queue(db: AsyncSession, user_id: int, text: str = "hello"):
    return await notification_service.queue_notification(db, user_id=user_id, notification_type="test", payload={"text": text})


async def test_successful_send_marks_sent(db_session: AsyncSession, telegram: FakeTelegram):
    user = await make_user(db_session, telegram_user_id=111)
    notification = await _queue(db_session, user.id, "movie tonight")

    processed = await notification_service.drain_pending(db_session)

    assert processed == 1
    assert notification.status == NotificationStatus.SENT
    assert notification.sent_at is not None
    assert notification.attempt_count == 1
    assert telegram.sent == [("111", "movie tonight")]


async def test_telegram_down_schedules_retry_with_backoff(db_session: AsyncSession, telegram: FakeTelegram):
    telegram.error = ProviderUnavailableError("telegram", "timeout")
    user = await make_user(db_session, telegram_user_id=111)
    notification = await _queue(db_session, user.id)

    before = datetime.now(timezone.utc)
    await notification_service.drain_pending(db_session)

    assert notification.status == NotificationStatus.FAILED_RETRYING
    assert notification.attempt_count == 1
    assert "temporarily unavailable" in notification.error_message
    base = get_settings().notification_retry_base_seconds
    assert notification.next_attempt_at >= before + timedelta(seconds=base)


async def test_retry_not_attempted_before_backoff_expires(db_session: AsyncSession, telegram: FakeTelegram):
    telegram.error = ProviderUnavailableError("telegram", "timeout")
    user = await make_user(db_session, telegram_user_id=111)
    await _queue(db_session, user.id)

    assert await notification_service.drain_pending(db_session) == 1
    # Telegram is back, but the retry isn't due yet.
    telegram.error = None
    assert await notification_service.drain_pending(db_session) == 0
    assert telegram.sent == []


async def test_backoff_doubles_each_attempt():
    base = get_settings().notification_retry_base_seconds
    assert [notification_service._backoff_seconds(n) for n in (1, 2, 3, 4)] == [base, base * 2, base * 4, base * 8]


async def test_dead_letter_after_max_retries(db_session: AsyncSession, telegram: FakeTelegram):
    telegram.error = TelegramDeliveryError("111", "bot was blocked by the user")
    user = await make_user(db_session, telegram_user_id=111)
    notification = await _queue(db_session, user.id)
    max_retries = get_settings().notification_max_retries

    for _ in range(max_retries):
        # Make the retry due immediately instead of waiting out the backoff.
        notification.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.flush()
        await notification_service.drain_pending(db_session)

    assert notification.attempt_count == max_retries
    assert notification.status == NotificationStatus.DEAD_LETTER
    assert "bot was blocked by the user" in notification.error_message

    # Dead-lettered notifications are never picked up again.
    notification.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()
    assert await notification_service.drain_pending(db_session) == 0


async def test_recipient_without_telegram_is_dead_lettered_without_sending(db_session: AsyncSession, telegram: FakeTelegram):
    user = await make_user(db_session, telegram_user_id=None)
    notification = await _queue(db_session, user.id)

    await notification_service.drain_pending(db_session)

    assert notification.status == NotificationStatus.DEAD_LETTER
    assert notification.error_message == "recipient has no linked Telegram chat"
    assert notification.attempt_count == 0
    assert telegram.sent == []
