"""Authentication routes.

First-run architecture (spec item 13): the very first user to log in via
Telegram on a fresh install becomes an admin automatically. Every
subsequent login gets the MEMBER role. There is no separate "setup wizard"
route — the first Telegram login *is* the setup step.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import create_access_token
from app.core.telegram_auth import InvalidTelegramAuthError, verify_telegram_login
from app.models.user import User, UserRole
from app.schemas.auth import TelegramLoginPayload, TokenResponse, UserOut

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.post("/telegram", response_model=TokenResponse)
async def login_with_telegram(payload: TelegramLoginPayload, db: Annotated[AsyncSession, Depends(get_db)]):
    if not settings.telegram_bot_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Telegram login is not configured (TELEGRAM_BOT_TOKEN missing). "
            "Sandbox mode: use POST /api/auth/sandbox-login instead.",
        )

    try:
        verify_telegram_login(payload.model_dump(), settings.telegram_bot_token)
    except InvalidTelegramAuthError as exc:
        logger.warning("auth.telegram_login_rejected", reason=str(exc))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Telegram login verification failed: {exc}") from exc

    user = await db.scalar(select(User).where(User.telegram_user_id == payload.id))
    if user is None:
        user_count = await db.scalar(select(func.count()).select_from(User))
        user = User(
            telegram_user_id=payload.id,
            telegram_username=payload.username,
            display_name=payload.first_name + (f" {payload.last_name}" if payload.last_name else ""),
            role=UserRole.ADMIN if user_count == 0 else UserRole.MEMBER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("auth.user_created", user_id=user.id, role=user.role.value)
    else:
        user.telegram_username = payload.username
        await db.commit()

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@router.post("/sandbox-login", response_model=TokenResponse)
async def sandbox_login(db: Annotated[AsyncSession, Depends(get_db)]):
    """Dev/demo-only login that bypasses Telegram entirely. Disabled in
    live mode so it can never become a real auth bypass in production."""
    if settings.is_live:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not available in live mode")

    user = await db.scalar(select(User).where(User.email == "sandbox@tickettwink.local"))
    if user is None:
        user_count = await db.scalar(select(func.count()).select_from(User))
        user = User(
            email="sandbox@tickettwink.local",
            display_name="Sandbox Admin",
            role=UserRole.ADMIN if user_count == 0 else UserRole.MEMBER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def get_me(user: Annotated[User, Depends(get_current_user)]):
    return UserOut(
        id=user.id,
        display_name=user.display_name,
        telegram_username=user.telegram_username,
        role=user.role.value,
        is_active=user.is_active,
    )
