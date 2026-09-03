import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class TicketStatus(str, enum.Enum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    REJECTED_MALFORMED = "rejected_malformed"
    DUPLICATE = "duplicate"
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    MISSING = "missing"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # One file hash can only be a *verified* ticket once per movie night —
        # this is the duplicate-ticket-upload guard (spec: "duplicate ticket").
        UniqueConstraint("movie_night_id", "file_hash", name="uq_ticket_movienight_filehash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_night_id: Mapped[int] = mapped_column(ForeignKey("movie_nights.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"), default=TicketStatus.PENDING_UPLOAD, nullable=False
    )

    storage_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)

    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Populated when status is REJECTED_MALFORMED, MISMATCH, or MISSING —
    # human-readable reason shown back to the uploader and to admins.
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # What the ticket *should* show (e.g. expected movie title / showtime),
    # used to detect a ticket-mismatch (spec: "ticket mismatch").
    expected_movie_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
