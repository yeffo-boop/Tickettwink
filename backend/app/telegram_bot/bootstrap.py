"""Builds and owns the python-telegram-bot Application used for webhook
processing. A single instance lives on `app.state.telegram_application`,
created at API startup and torn down at shutdown (see main.py).
"""
from telegram.ext import Application, CommandHandler

from app.core.config import get_settings
from app.core.logging import get_logger
from app.telegram_bot import handlers

logger = get_logger(__name__)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("nextmovienight", handlers.next_movie_night))
    application.add_handler(CommandHandler("help", handlers.help_command))
    return application
