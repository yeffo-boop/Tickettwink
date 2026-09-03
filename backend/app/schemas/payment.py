from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PaymentOut(BaseModel):
    id: int
    movie_night_id: int
    user_id: int
    amount_expected_cents: int
    amount_received_cents: int
    status: str
    provider_reference: Optional[str] = None
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaymentConfirmRequest(BaseModel):
    additional_amount_cents: int
    provider_reference: Optional[str] = None
    notes: Optional[str] = None
