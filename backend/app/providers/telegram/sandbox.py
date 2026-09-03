"""Sandbox Telegram provider: logs the message instead of sending it. Used
whenever TELEGRAM_BOT_TOKEN is unset, so the whole notification pipeline
(queueing, retry, dead-lettering) can be exercised without a real bot."""
import itertools

from app.core.logging import get_logger
from app.providers.telegram.base import TelegramProvider

logger = get_logger(__name__)
_ids = itertools.count(1)


class TelegramSandboxProvider(TelegramProvider):
    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = "HTML") -> str:
        message_id = next(_ids)
        logger.info("telegram.sandbox_send", chat_id=chat_id, text=text, message_id=message_id)
        return str(message_id)
