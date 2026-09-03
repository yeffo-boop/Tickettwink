from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.movie_night import MovieNight
from app.models.user import User
from app.schemas.movie_night import MovieNightCancel, MovieNightCreate, MovieNightOut, ShowtimeUpdate
from app.services import movie_night_service

router = APIRouter()


async def _get_movie_night_or_404(db: AsyncSession, movie_night_id: int) -> MovieNight:
    movie_night = await db.get(MovieNight, movie_night_id)
    if movie_night is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie Night not found")
    return movie_night


@router.get("", response_model=list[MovieNightOut])
async def list_movie_nights(db: Annotated[AsyncSession, Depends(get_db)], _: Annotated[User, Depends(get_current_user)]):
    result = await db.execute(select(MovieNight).order_by(MovieNight.scheduled_at.desc().nulls_last()))
    return result.scalars().all()


@router.post("", response_model=MovieNightOut, status_code=status.HTTP_201_CREATED)
async def create_movie_night(
    payload: MovieNightCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    movie_night = await movie_night_service.create_movie_night(
        db, created_by_user_id=admin.id, title=payload.title, tmdb_id=payload.tmdb_id
    )
    movie_night.price_per_ticket_cents = payload.price_per_ticket_cents
    await db.commit()
    await db.refresh(movie_night)
    return movie_night


@router.get("/{movie_night_id}", response_model=MovieNightOut)
async def get_movie_night(movie_night_id: int, db: Annotated[AsyncSession, Depends(get_db)], _: Annotated[User, Depends(get_current_user)]):
    return await _get_movie_night_or_404(db, movie_night_id)


@router.put("/{movie_night_id}/showtime", response_model=MovieNightOut)
async def set_showtime(
    movie_night_id: int,
    payload: ShowtimeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    movie_night = await _get_movie_night_or_404(db, movie_night_id)
    await movie_night_service.update_showtime(
        db,
        movie_night,
        new_starts_at=payload.starts_at,
        cinema_name=payload.cinema_name,
        admin_user_id=admin.id,
        external_showtime_id=payload.external_showtime_id,
    )
    await db.commit()
    await db.refresh(movie_night)
    return movie_night


@router.post("/{movie_night_id}/cancel", response_model=MovieNightOut)
async def cancel_movie_night(
    movie_night_id: int,
    payload: MovieNightCancel,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    movie_night = await _get_movie_night_or_404(db, movie_night_id)
    await movie_night_service.cancel_movie_night(db, movie_night, admin_user_id=admin.id, reason=payload.reason)
    await db.commit()
    await db.refresh(movie_night)
    return movie_night
