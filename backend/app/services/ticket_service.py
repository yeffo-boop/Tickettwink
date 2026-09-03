"""Ticket upload and verification.

Handles four spec failure scenarios:

  - "malformed ticket upload": content-type/size/structural validation
    rejects the file up front with a clear reason; nothing bad is ever
    written to storage or the DB as a real ticket.
  - "duplicate ticket": the same file (by content hash) can't be uploaded
    twice for the same Movie Night — checked before hitting the DB unique
    constraint, which is the belt-and-suspenders backstop against races.
  - "ticket mismatch": there is no reliable free OCR available to
    automatically confirm a ticket photo shows the right movie/showtime,
    so verification is a deliberate manual step — an admin reviews the
    uploaded file and marks it VERIFIED or MISMATCH with notes. This is
    the same "implement the manual fallback, document what's needed to
    activate automation" pattern used for showtimes/payments; wiring in
    an OCR provider later only touches `verify_ticket_automated` (a stub
    below) without changing the upload path.
  - "missing ticket": see `find_missing_tickets`, invoked by the scheduler
    ahead of a Movie Night to nudge anyone who hasn't uploaded yet.
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.movie_night import MovieNight
from app.models.ticket import Ticket, TicketStatus
from app.providers.storage.factory import get_storage_provider
from app.services import audit_service

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_WEBP_MAGIC = b"RIFF"


class MalformedTicketError(Exception):
    pass


class DuplicateTicketError(Exception):
    def __init__(self, existing_ticket_id: int):
        self.existing_ticket_id = existing_ticket_id
        super().__init__(f"This exact file was already uploaded as ticket #{existing_ticket_id}")


def _validate_structure(content: bytes, content_type: str) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise MalformedTicketError(
            f"Unsupported file type '{content_type}'. Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )
    if not content:
        raise MalformedTicketError("Uploaded file is empty")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise MalformedTicketError(f"File too large ({len(content)} bytes, max {MAX_FILE_SIZE_BYTES})")

    if content_type == "application/pdf" and not content.startswith(_PDF_MAGIC):
        raise MalformedTicketError("File claims to be a PDF but doesn't start with a PDF header")
    if content_type == "image/jpeg" and not content.startswith(_JPEG_MAGIC):
        raise MalformedTicketError("File claims to be JPEG but has an invalid header")
    if content_type == "image/png" and not content.startswith(_PNG_MAGIC):
        raise MalformedTicketError("File claims to be PNG but has an invalid header")
    if content_type == "image/webp" and not content.startswith(_WEBP_MAGIC):
        raise MalformedTicketError("File claims to be WEBP but has an invalid header")

    if content_type in ("image/jpeg", "image/png", "image/webp"):
        try:
            from PIL import Image, UnidentifiedImageError
            import io

            with Image.open(io.BytesIO(content)) as img:
                img.verify()
        except UnidentifiedImageError as exc:
            raise MalformedTicketError("File could not be decoded as a valid image") from exc
        except ImportError:  # pragma: no cover - Pillow always installed via requirements.txt
            pass


async def upload_ticket(
    db: AsyncSession,
    movie_night: MovieNight,
    user_id: int,
    content: bytes,
    content_type: str,
    original_filename: str,
) -> Ticket:
    _validate_structure(content, content_type)

    file_hash = hashlib.sha256(content).hexdigest()

    existing = await db.scalar(
        select(Ticket).where(
            Ticket.movie_night_id == movie_night.id,
            Ticket.file_hash == file_hash,
            Ticket.status != TicketStatus.REJECTED_MALFORMED,
        )
    )
    if existing is not None:
        raise DuplicateTicketError(existing.id)

    storage = get_storage_provider()
    extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
        content_type
    ]
    storage_key = f"movie_night_{movie_night.id}/user_{user_id}/{file_hash}.{extension}"
    await storage.save(storage_key, content, content_type)

    ticket = Ticket(
        movie_night_id=movie_night.id,
        user_id=user_id,
        status=TicketStatus.UPLOADED,
        storage_key=storage_key,
        original_filename=original_filename,
        content_type=content_type,
        file_hash=file_hash,
        file_size_bytes=len(content),
        uploaded_at=datetime.now(timezone.utc),
        expected_movie_title=movie_night.title,
    )
    db.add(ticket)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Race: two concurrent uploads of the same file. The DB unique
        # constraint is the final backstop after the pre-check above.
        await db.rollback()
        raise DuplicateTicketError(-1) from exc

    await audit_service.record(
        db, "ticket.uploaded", "ticket", ticket.id, actor_user_id=user_id, context={"file_hash": file_hash}
    )
    return ticket


async def verify_ticket_manual(
    db: AsyncSession, ticket: Ticket, admin_user_id: int, matches: bool, notes: Optional[str] = None
) -> Ticket:
    """Admin-driven verification (see module docstring re: no OCR)."""
    ticket.status = TicketStatus.VERIFIED if matches else TicketStatus.MISMATCH
    ticket.verified_at = datetime.now(timezone.utc)
    ticket.verified_by_user_id = admin_user_id
    ticket.verification_notes = notes
    await audit_service.record(
        db,
        "ticket.verified" if matches else "ticket.mismatch",
        "ticket",
        ticket.id,
        actor_user_id=admin_user_id,
        context={"notes": notes},
    )
    await db.flush()
    return ticket


@dataclass
class MissingTicketEntry:
    user_id: int
    ticket_id: Optional[int]


async def find_missing_tickets(db: AsyncSession, movie_night: MovieNight, expected_user_ids: list[int]) -> list[MissingTicketEntry]:
    """Users expected to attend (e.g. anyone who paid) who have no
    UPLOADED/VERIFIED ticket yet. Called by the scheduler ahead of a Movie
    Night so reminders go out, and again at a cutoff so remaining gaps are
    marked MISSING and flagged to admins rather than discovered at the
    door."""
    result = await db.execute(
        select(Ticket).where(
            Ticket.movie_night_id == movie_night.id,
            Ticket.status.in_([TicketStatus.UPLOADED, TicketStatus.VERIFIED]),
        )
    )
    covered_user_ids = {t.user_id for t in result.scalars().all()}
    missing = [uid for uid in expected_user_ids if uid not in covered_user_ids]

    entries = []
    for user_id in missing:
        existing_pending = await db.scalar(
            select(Ticket).where(Ticket.movie_night_id == movie_night.id, Ticket.user_id == user_id)
        )
        entries.append(MissingTicketEntry(user_id=user_id, ticket_id=existing_pending.id if existing_pending else None))
    return entries


async def mark_ticket_missing(db: AsyncSession, movie_night: MovieNight, user_id: int) -> Ticket:
    ticket = await db.scalar(
        select(Ticket).where(Ticket.movie_night_id == movie_night.id, Ticket.user_id == user_id)
    )
    if ticket is None:
        ticket = Ticket(movie_night_id=movie_night.id, user_id=user_id, status=TicketStatus.MISSING)
        db.add(ticket)
    else:
        ticket.status = TicketStatus.MISSING
    ticket.verification_notes = "No ticket uploaded before the cutoff."
    await audit_service.record(db, "ticket.marked_missing", "ticket", ticket.id if ticket.id else None, context={"user_id": user_id})
    await db.flush()
    return ticket
