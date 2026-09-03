from typing import Optional

from pydantic import BaseModel


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    display_name: str
    telegram_username: Optional[str] = None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
