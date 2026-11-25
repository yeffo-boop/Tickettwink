"""Small helpers for building rows in tests."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.movie_night import MovieNight, MovieNightStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole


async def make_user(db: AsyncSession, name: str = "Member", telegram_user_id: int | None = None, admin: bool = False) -> User:
    user = User(
        display_name=name,
        telegram_user_id=telegram_user_id,
        role=UserRole.ADMIN if admin else UserRole.MEMBER,
    )
    db.add(user)
    await db.flush()
    return user


async def make_movie_night(db: AsyncSession, creator: User, status: MovieNightStatus = MovieNightStatus.PLANNED, **kwargs) -> MovieNight:
    movie_night = MovieNight(title=kwargs.pop("title", "Test Movie"), created_by_user_id=creator.id, status=status, **kwargs)
    db.add(movie_night)
    await db.flush()
    return movie_night


async def make_ticket(db: AsyncSession, movie_night: MovieNight, user: User, status: TicketStatus = TicketStatus.UPLOADED) -> Ticket:
    ticket = Ticket(movie_night_id=movie_night.id, user_id=user.id, status=status)
    db.add(ticket)
    await db.flush()
    return ticket
