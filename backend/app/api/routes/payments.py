from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.movie_night import MovieNight
from app.models.payment import Payment
from app.models.user import User
from app.providers.payment.factory import get_payment_provider
from app.schemas.payment import PaymentConfirmRequest, PaymentOut
from app.services import payment_service

router = APIRouter()


@router.get("/movie-nights/{movie_night_id}", response_model=list[PaymentOut])
async def list_payments(
    movie_night_id: int, db: Annotated[AsyncSession, Depends(get_db)], admin: Annotated[User, Depends(require_admin)]
):
    result = await db.execute(select(Payment).where(Payment.movie_night_id == movie_night_id))
    return result.scalars().all()


@router.get("/movie-nights/{movie_night_id}/instructions")
async def get_payment_instructions(
    movie_night_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[User, Depends(get_current_user)]
):
    movie_night = await db.get(MovieNight, movie_night_id)
    if movie_night is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie Night not found")
    if not movie_night.price_per_ticket_cents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This Movie Night has no price set yet")

    instructions = get_payment_provider().get_payment_instructions(
        movie_night.price_per_ticket_cents, memo=f"Ticket Twink: {movie_night.title}"
    )
    return instructions


@router.post("/movie-nights/{movie_night_id}/for-user/{user_id}", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment_for_user(
    movie_night_id: int,
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    movie_night = await db.get(MovieNight, movie_night_id)
    if movie_night is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie Night not found")
    if not movie_night.price_per_ticket_cents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This Movie Night has no price set yet")

    payment = payment_service.create_payment_record(movie_night_id, user_id, movie_night.price_per_ticket_cents)
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
async def confirm_payment(
    payment_id: int,
    payload: PaymentConfirmRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

    try:
        await payment_service.confirm_payment(
            db,
            payment,
            additional_amount_cents=payload.additional_amount_cents,
            admin_user_id=admin.id,
            provider_reference=payload.provider_reference,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await db.commit()
    await db.refresh(payment)
    return payment
