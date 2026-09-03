"""Health endpoint: reports app status plus per-provider circuit-breaker state
so operators can see degraded integrations at a glance."""
from fastapi import APIRouter
from sqlalchemy import text

from app.core.circuit_breaker import CircuitState, _breakers
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health():
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive
        db_status = f"unavailable: {exc}"

    providers = {
        name: breaker.state.value if isinstance(breaker.state, CircuitState) else breaker.state
        for name, breaker in _breakers.items()
    }

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": settings.app_name,
        "mode": settings.app_mode.value,
        "database": db_status,
        "providers": providers,
    }
