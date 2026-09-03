from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MovieNightCreate(BaseModel):
    title: str
    tmdb_id: Optional[int] = None
    price_per_ticket_cents: Optional[int] = None


class ShowtimeUpdate(BaseModel):
    starts_at: datetime
    cinema_name: str
    external_showtime_id: Optional[str] = None


class MovieNightCancel(BaseModel):
    reason: str


class MovieNightOut(BaseModel):
    id: int
    title: str
    status: str
    venue: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    price_per_ticket_cents: Optional[int] = None
    tmdb_cache_stale: bool
    cancellation_reason: Optional[str] = None

    model_config = {"from_attributes": True}
