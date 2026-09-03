import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class NotificationChannel(str, enum.Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"  # not implemented yet; reserved for future fallback channel


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED_RETRYING = "failed_retrying"
    DEAD_LETTER = "dead_letter"  # exhausted retries — needs manual attention


class Notification(TimestampMixin, Base):
    """Outbound-message queue with retry bookkeeping.

    Every notification (Telegram message, etc.) is written here *before*
    attempting delivery, so a Telegram outage or crash mid-send never loses
    the message — the scheduler's retry-drain job keeps trying with
    exponential backoff until NOTIFICATION_MAX_RETRIES is hit, at which
    point it becomes DEAD_LETTER and is surfaced to admins instead of
    silently vanishing (spec: "failed notification").
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    movie_night_id: Mapped[Optional[int]] = mapped_column(ForeignKey("movie_nights.id"), nullable=True)

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"), default=NotificationChannel.TELEGRAM, nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"), default=NotificationStatus.PENDING, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
