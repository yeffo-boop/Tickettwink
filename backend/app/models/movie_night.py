import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class MovieNightStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    CONFIRMED = "confirmed"
    SHOWTIME_CHANGED = "showtime_changed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class MovieNight(TimestampMixin, Base):
    __tablename__ = "movie_nights"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # TMDB linkage — nullable because TMDB may be unavailable at creation time
    # (spec: "TMDB unavailable" must not block creating a Movie Night).
    tmdb_movie_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tmdb_cache: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tmdb_cache_stale: Mapped[bool] = mapped_column(default=False, nullable=False)

    venue: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    price_per_ticket_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[MovieNightStatus] = mapped_column(
        Enum(MovieNightStatus, name="movie_night_status"), default=MovieNightStatus.DRAFT, nullable=False
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
