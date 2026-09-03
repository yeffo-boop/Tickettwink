from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def record(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    context: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
        )
    )
    # Caller is responsible for the surrounding commit — audit entries are
    # written in the same transaction as the state change they describe.
