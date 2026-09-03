import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERPAID = "overpaid"
    REFUND_DUE = "refund_due"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class Payment(TimestampMixin, Base):
    """Tracks amount owed vs. amount actually received.

    Venmo has no public API for verifying incoming payments, so amounts are
    reconciled by manual admin confirmation (see providers/payment). This
    model is provider-agnostic on purpose — swapping in a real payment API
    later only touches the provider implementation, not this schema.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_night_id: Mapped[int] = mapped_column(ForeignKey("movie_nights.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), nullable=True)

    amount_expected_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_received_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False
    )

    provider_name: Mapped[str] = mapped_column(String(50), default="venmo_manual", nullable=False)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
