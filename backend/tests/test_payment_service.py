import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentStatus
from app.models.user import User, UserRole
from app.services import payment_service


async def _make_admin(db: AsyncSession) -> User:
    admin = User(display_name="Admin", role=UserRole.ADMIN)
    db.add(admin)
    await db.flush()
    return admin


async def test_partial_payment(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=500, admin_user_id=admin.id)

    assert payment.status == PaymentStatus.PARTIAL
    assert payment.amount_received_cents == 500


async def test_exact_payment_marks_paid(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=1500, admin_user_id=admin.id)

    assert payment.status == PaymentStatus.PAID


async def test_overpayment(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=2000, admin_user_id=admin.id)

    assert payment.status == PaymentStatus.OVERPAID
    assert payment.amount_received_cents == 2000


async def test_partial_then_topped_up_to_paid(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=500, admin_user_id=admin.id)
    assert payment.status == PaymentStatus.PARTIAL

    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=1000, admin_user_id=admin.id)
    assert payment.status == PaymentStatus.PAID
    assert payment.amount_received_cents == 1500


async def test_zero_or_negative_amount_rejected(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    with pytest.raises(ValueError):
        await payment_service.confirm_payment(db_session, payment, additional_amount_cents=0, admin_user_id=admin.id)


async def test_refund_due_marks_cancelled_when_nothing_paid(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()

    await payment_service.mark_refund_due(db_session, payment, reason="cancelled", admin_user_id=admin.id)
    assert payment.status == PaymentStatus.CANCELLED


async def test_refund_due_when_something_was_paid(db_session: AsyncSession):
    admin = await _make_admin(db_session)
    payment = payment_service.create_payment_record(movie_night_id=1, user_id=admin.id, amount_expected_cents=1500)
    db_session.add(payment)
    await db_session.flush()
    await payment_service.confirm_payment(db_session, payment, additional_amount_cents=2000, admin_user_id=admin.id)

    await payment_service.mark_refund_due(db_session, payment, reason="cancelled", admin_user_id=admin.id)
    assert payment.status == PaymentStatus.REFUND_DUE
