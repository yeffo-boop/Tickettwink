"""Admin-only visibility and control routes — the surface an organizer uses
to see and act on failure states the system couldn't resolve on its own
(dead-lettered notifications, provider outages, refunds due)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.circuit_breaker import _breakers
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.notification import Notification, NotificationStatus
from app.models.payment import Payment, PaymentStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.services import payment_service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/provider-health")
async def provider_health():
    return {name: breaker.state.value for name, breaker in _breakers.items()}


@router.get("/notifications/dead-letter")
async def dead_lettered_notifications(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Notification).where(Notification.status == NotificationStatus.DEAD_LETTER))
    notifications = result.scalars().all()
    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "notification_type": n.notification_type,
            "attempt_count": n.attempt_count,
            "error_message": n.error_message,
            "created_at": n.created_at,
        }
        for n in notifications
    ]


@router.post("/notifications/{notification_id}/requeue")
async def requeue_notification(notification_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    notification = await db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    notification.status = NotificationStatus.PENDING
    notification.attempt_count = 0
    from datetime import datetime, timezone

    notification.next_attempt_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "requeued"}


@router.get("/tickets/mismatched-or-missing")
async def flagged_tickets(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(Ticket).where(Ticket.status.in_([TicketStatus.MISMATCH, TicketStatus.MISSING, TicketStatus.REJECTED_MALFORMED]))
    )
    return result.scalars().all()


@router.get("/payments/refunds-due")
async def refunds_due(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Payment).where(Payment.status == PaymentStatus.REFUND_DUE))
    return result.scalars().all()


@router.post("/payments/{payment_id}/mark-refunded")
async def mark_refunded(
    payment_id: int, db: Annotated[AsyncSession, Depends(get_db)], admin: Annotated[User, Depends(require_admin)]
):
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    await payment_service.mark_refunded(db, payment, admin_user_id=admin.id)
    await db.commit()
    return {"status": "refunded"}


@router.get("/audit-log")
async def recent_audit_log(db: Annotated[AsyncSession, Depends(get_db)], limit: int = 100):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return result.scalars().all()
