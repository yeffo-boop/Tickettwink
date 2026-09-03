"""Telegram command handlers.

Kept intentionally thin (architecture rule: "keep business logic out of
Telegram handlers where possible"). Each handler's job is: parse the
Telegram update, open a DB session, call a service function, format a
reply. No business rules live here.
"""
from telegram import Update
from telegram.ext import ContextTypes

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.movie_night import MovieNight, MovieNightStatus
from app.models.user import User, UserRole
from sqlalchemy import func, select

logger = get_logger(__name__)


async def _get_or_create_user(db, tg_user) -> User:
    user = await db.scalar(select(User).where(User.telegram_user_id == tg_user.id))
    if user is None:
        user_count = await db.scalar(select(func.count()).select_from(User))
        user = User(
            telegram_user_id=tg_user.id,
            telegram_username=tg_user.username,
            display_name=tg_user.first_name or tg_user.username or "Member",
            role=UserRole.ADMIN if user_count == 0 else UserRole.MEMBER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        user = await _get_or_create_user(db, update.effective_user)
    role_note = " You're the first user, so you're an admin! 🎟️" if user.role == UserRole.ADMIN else ""
    await update.message.reply_text(
        f"Welcome to Ticket Twink 🎟️💅, {user.display_name}!{role_note}\n"
        "Use /nextmovienight to see what's coming up, or open the Mini App for the full experience."
    )


async def next_movie_night(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MovieNight)
            .where(MovieNight.status.in_([MovieNightStatus.PLANNED, MovieNightStatus.CONFIRMED, MovieNightStatus.SHOWTIME_CHANGED]))
            .order_by(MovieNight.scheduled_at.asc().nulls_last())
            .limit(1)
        )
        movie_night = result.scalars().first()

    if movie_night is None:
        await update.message.reply_text("No Movie Night scheduled yet. Check back soon! 🍿")
        return

    when = movie_night.scheduled_at.strftime("%a %b %d, %I:%M %p") if movie_night.scheduled_at else "TBD"
    await update.message.reply_text(
        f"🎬 {movie_night.title}\n📅 {when}\n📍 {movie_night.venue or 'TBD'}\n"
        f"Status: {movie_night.status.value}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ticket Twink commands:\n"
        "/start — register / get greeted\n"
        "/nextmovienight — see the next scheduled Movie Night\n"
        "Ticket upload, payment confirmation, and admin actions happen in the Mini App."
    )
