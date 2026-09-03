"""Payment tracking. Reconciliation is manual (see providers/payment) —
this service is where "partial payment" and "overpayment" become explicit,
first-class states instead of a single opaque "paid/unpaid" boolean.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.payment import Payment, PaymentStatus
from app.services import audit_service

logger = get_logger(__name__)


def create_payment_record(movie_night_id: int, user_id: int, amount_expected_cents: int, ticket_id: Optional[int] = None) -> Payment:
    return Payment(
        movie_night_id=movie_night_id,
        user_id=user_id,
        ticket_id=ticket_id,
        amount_expected_cents=amount_expected_cents,
        amount_received_cents=0,
        status=PaymentStatus.PENDING,
    )


def _status_for_amounts(expected_cents: int, received_cents: int) -> PaymentStatus:
    if received_cents <= 0:
        return PaymentStatus.PENDING
    if received_cents < expected_cents:
        return PaymentStatus.PARTIAL
    if received_cents == expected_cents:
        return PaymentStatus.PAID
    return PaymentStatus.OVERPAID


async def confirm_payment(
    db: AsyncSession,
    payment: Payment,
    additional_amount_cents: int,
    admin_user_id: int,
    provider_reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> Payment:
    """Records money actually received (cumulative — a member may pay in
    more than one Venmo transaction). Recomputes status from the running
    total every time, so a partial payment topped up later correctly
    transitions PARTIAL -> PAID -> OVERPAID as more comes in."""
    if additional_amount_cents <= 0:
        raise ValueError("additional_amount_cents must be positive")

    payment.amount_received_cents += additional_amount_cents
    payment.status = _status_for_amounts(payment.amount_expected_cents, payment.amount_received_cents)
    payment.provider_reference = provider_reference
    payment.notes = notes
    payment.confirmed_by_user_id = admin_user_id
    payment.confirmed_at = datetime.now(timezone.utc)

    await audit_service.record(
        db,
        "payment.confirmed",
        "payment",
        payment.id,
        actor_user_id=admin_user_id,
        context={
            "additional_amount_cents": additional_amount_cents,
            "total_received_cents": payment.amount_received_cents,
            "expected_cents": payment.amount_expected_cents,
            "resulting_status": payment.status.value,
        },
    )
    if payment.status == PaymentStatus.OVERPAID:
        logger.info(
            "payment.overpaid",
            payment_id=payment.id,
            overage_cents=payment.amount_received_cents - payment.amount_expected_cents,
        )
    await db.flush()
    return payment


async def mark_refund_due(db: AsyncSession, payment: Payment, reason: str, admin_user_id: Optional[int] = None) -> Payment:
    """Used for both overpayment refunds and Movie Night cancellations."""
    if payment.amount_received_cents > 0:
        payment.status = PaymentStatus.REFUND_DUE
    else:
        payment.status = PaymentStatus.CANCELLED
    await audit_service.record(
        db, "payment.refund_due", "payment", payment.id, actor_user_id=admin_user_id, context={"reason": reason}
    )
    await db.flush()
    return payment


async def mark_refunded(db: AsyncSession, payment: Payment, admin_user_id: int, notes: Optional[str] = None) -> Payment:
    payment.status = PaymentStatus.REFUNDED
    payment.notes = notes
    await audit_service.record(db, "payment.refunded", "payment", payment.id, actor_user_id=admin_user_id)
    await db.flush()
    return payment
