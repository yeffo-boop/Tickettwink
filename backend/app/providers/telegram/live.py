"""Live Telegram provider using python-telegram-bot's async Bot client
against the real Telegram Bot API. Requires TELEGRAM_BOT_TOKEN (create one
via @BotFather on Telegram: https://core.telegram.org/bots/tutorial).

Wrapped in the shared circuit breaker so a Telegram outage (spec:
"Telegram temporary failure") degrades gracefully — sends get queued in
the Notification table by notification_service and retried later instead
of the request path hanging or crashing.
"""
from telegram import Bot
from telegram.error import Forbidden, BadRequest, TelegramError, NetworkError, TimedOut

from app.core.circuit_breaker import CircuitBreaker
from app.providers.telegram.base import TelegramDeliveryError, TelegramProvider

# Errors that mean "this specific chat can't be reached" — not a Telegram
# outage, so they should NOT trip the circuit breaker or be retried blindly.
ADDRESS_ERRORS = (Forbidden, BadRequest)
# Errors that mean "Telegram itself is having trouble" — these count
# toward the circuit breaker opening.
TRANSIENT_ERRORS = (NetworkError, TimedOut)


class TelegramLiveProvider(TelegramProvider):
    def __init__(self, bot_token: str, breaker: CircuitBreaker):
        self._bot = Bot(token=bot_token)
        self._breaker = breaker

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = "HTML") -> str:
        self._breaker.before_call()
        try:
            message = await self._bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except ADDRESS_ERRORS as exc:
            # Not a provider outage — don't trip the breaker.
            raise TelegramDeliveryError(chat_id, str(exc)) from exc
        except (TRANSIENT_ERRORS, TelegramError) as exc:  # type: ignore[misc]
            self._breaker.on_failure(exc)
            raise
        except Exception as exc:
            self._breaker.on_failure(exc)
            raise
        else:
            self._breaker.on_success()
            return str(message.message_id)
