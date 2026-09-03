"""Telegram webhook endpoint.

Verifies the `X-Telegram-Bot-Api-Secret-Token` header (set on the webhook
via Telegram's setWebhook `secret_token` param — see docs/SETUP.md) so
that only Telegram itself can post updates here. In sandbox mode (no bot
token configured), this returns 503 — there's nothing to dispatch to.
"""
from fastapi import APIRouter, HTTPException, Request, status
from telegram import Update

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.post("/webhook")
async def telegram_webhook(request: Request):
    application = getattr(request.app.state, "telegram_application", None)
    if application is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram integration not configured")

    if settings.telegram_webhook_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != settings.telegram_webhook_secret:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    data = await request.json()
    update = Update.de_json(data, application.bot)
    if update is None:
        logger.warning("telegram_webhook.unparseable_update", data=data)
        return {"ok": True}

    await application.process_update(update)
    return {"ok": True}
