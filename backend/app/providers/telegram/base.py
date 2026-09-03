"""Telegram messaging provider interface.

The Telegram Bot API is well-documented and stable
(https://core.telegram.org/bots/api). This abstraction exists so that
`notification_service` (and anything else that sends a message) never
imports `python-telegram-bot` or handles Telegram-specific errors directly
— it just calls `send_message` and handles ProviderUnavailableError /
TelegramDeliveryError generically. That keeps Telegram out of core business
logic per the architecture rules.
"""
from abc import ABC, abstractmethod
from typing import Optional


class TelegramDeliveryError(Exception):
    """A specific, addressed send failed (e.g. user blocked the bot, chat
    not found). Distinct from ProviderUnavailableError, which means the
    Telegram API itself is unreachable. Not retryable in the same way —
    a blocked bot won't unblock itself."""

    def __init__(self, chat_id: str, reason: str):
        self.chat_id = chat_id
        self.reason = reason
        super().__init__(f"Failed to deliver to chat {chat_id}: {reason}")


class TelegramProvider(ABC):
    @abstractmethod
    async def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = "HTML") -> str:
        """Returns the provider's message id on success.

        Raises ProviderUnavailableError if Telegram cannot be reached at
        all (circuit open / network failure). Raises TelegramDeliveryError
        for an address-specific failure (blocked bot, chat not found).
        """
