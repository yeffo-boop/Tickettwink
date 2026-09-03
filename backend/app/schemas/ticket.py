from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TicketOut(BaseModel):
    id: int
    movie_night_id: int
    user_id: int
    status: str
    original_filename: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    verification_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class TicketVerifyRequest(BaseModel):
    matches: bool
    notes: Optional[str] = None
