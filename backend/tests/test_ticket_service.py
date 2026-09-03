import struct
import zlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.movie_night import MovieNight, MovieNightStatus
from app.models.ticket import TicketStatus
from app.models.user import User, UserRole
from app.services import ticket_service
from app.services.ticket_service import DuplicateTicketError, MalformedTicketError


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    body = chunk_type + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _make_valid_png() -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    return signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


_PNG_BYTES = _make_valid_png()


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))
    from app.providers.storage import factory

    factory.get_storage_provider.cache_clear()
    yield
    factory.get_storage_provider.cache_clear()


async def _make_user_and_movie_night(db: AsyncSession):
    user = User(display_name="Member", role=UserRole.MEMBER)
    db.add(user)
    await db.flush()
    movie_night = MovieNight(title="Test Film", created_by_user_id=user.id, status=MovieNightStatus.DRAFT)
    db.add(movie_night)
    await db.flush()
    return user, movie_night


async def test_rejects_wrong_content_type(db_session: AsyncSession):
    user, movie_night = await _make_user_and_movie_night(db_session)
    with pytest.raises(MalformedTicketError):
        await ticket_service.upload_ticket(db_session, movie_night, user.id, b"hello", "text/plain", "ticket.txt")


async def test_rejects_empty_file(db_session: AsyncSession):
    user, movie_night = await _make_user_and_movie_night(db_session)
    with pytest.raises(MalformedTicketError):
        await ticket_service.upload_ticket(db_session, movie_night, user.id, b"", "image/png", "ticket.png")


async def test_rejects_fake_pdf_header(db_session: AsyncSession):
    user, movie_night = await _make_user_and_movie_night(db_session)
    with pytest.raises(MalformedTicketError):
        await ticket_service.upload_ticket(
            db_session, movie_night, user.id, b"not a real pdf", "application/pdf", "ticket.pdf"
        )


async def test_valid_png_upload_succeeds(db_session: AsyncSession):
    user, movie_night = await _make_user_and_movie_night(db_session)
    ticket = await ticket_service.upload_ticket(db_session, movie_night, user.id, _PNG_BYTES, "image/png", "t.png")
    assert ticket.status == TicketStatus.UPLOADED
    assert ticket.file_hash is not None


async def test_duplicate_upload_rejected(db_session: AsyncSession):
    user, movie_night = await _make_user_and_movie_night(db_session)
    await ticket_service.upload_ticket(db_session, movie_night, user.id, _PNG_BYTES, "image/png", "t.png")
    with pytest.raises(DuplicateTicketError):
        await ticket_service.upload_ticket(db_session, movie_night, user.id, _PNG_BYTES, "image/png", "t2.png")
