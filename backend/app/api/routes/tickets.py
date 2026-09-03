from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.movie_night import MovieNight
from app.models.ticket import Ticket
from app.models.user import User
from app.providers.storage.factory import get_storage_provider
from app.schemas.ticket import TicketOut, TicketVerifyRequest
from app.services import ticket_service
from app.services.ticket_service import DuplicateTicketError, MalformedTicketError

router = APIRouter()


@router.post("/movie-nights/{movie_night_id}/upload", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def upload_ticket(
    movie_night_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    movie_night = await db.get(MovieNight, movie_night_id)
    if movie_night is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie Night not found")

    content = await file.read()
    try:
        ticket = await ticket_service.upload_ticket(
            db, movie_night, user.id, content, file.content_type or "application/octet-stream", file.filename or "ticket"
        )
    except MalformedTicketError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DuplicateTicketError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/movie-nights/{movie_night_id}", response_model=list[TicketOut])
async def list_tickets_for_movie_night(
    movie_night_id: int, db: Annotated[AsyncSession, Depends(get_db)], admin: Annotated[User, Depends(require_admin)]
):
    result = await db.execute(select(Ticket).where(Ticket.movie_night_id == movie_night_id))
    return result.scalars().all()


@router.get("/mine/{movie_night_id}", response_model=list[TicketOut])
async def list_my_tickets(
    movie_night_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(select(Ticket).where(Ticket.movie_night_id == movie_night_id, Ticket.user_id == user.id))
    return result.scalars().all()


async def _get_ticket_or_404(db: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


@router.post("/{ticket_id}/verify", response_model=TicketOut)
async def verify_ticket(
    ticket_id: int,
    payload: TicketVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
):
    ticket = await _get_ticket_or_404(db, ticket_id)
    await ticket_service.verify_ticket_manual(db, ticket, admin.id, matches=payload.matches, notes=payload.notes)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}/file")
async def get_ticket_file(
    ticket_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[User, Depends(get_current_user)]
):
    """The only way to read a ticket file back — never exposed via a static
    mount. Ownership (or admin) is required."""
    ticket = await _get_ticket_or_404(db, ticket_id)
    if ticket.user_id != user.id and user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your ticket")
    if not ticket.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file on this ticket")

    storage = get_storage_provider()
    try:
        content = await storage.read(ticket.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket file missing from storage")

    import io

    return StreamingResponse(io.BytesIO(content), media_type=ticket.content_type or "application/octet-stream")
