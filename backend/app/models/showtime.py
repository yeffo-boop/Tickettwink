import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ShowtimeStatus(str, enum.Enum):
    ACTIVE = "active"
    CHANGED = "changed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"  # provider unavailable, last known state stale


class Showtime(TimestampMixin, Base):
    """Cached view of an external showtime-provider record.

    Kept separate from MovieNight so that a showtime-API outage never blocks
    reading/creating a Movie Night — the app operates on the last-synced
    values and flags them stale (spec: "showtime API unavailable").
    """

    __tablename__ = "showtimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_night_id: Mapped[int] = mapped_column(ForeignKey("movie_nights.id"), nullable=False, index=True)

    external_showtime_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cinema_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[ShowtimeStatus] = mapped_column(
        Enum(ShowtimeStatus, name="showtime_status"), default=ShowtimeStatus.UNKNOWN, nullable=False
    )
    raw_provider_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_stale: Mapped[bool] = mapped_column(default=False, nullable=False)
