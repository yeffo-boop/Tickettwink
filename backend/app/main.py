"""Ticket Twink API entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, movie_nights, tickets, payments, telegram_webhook, admin
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.scheduler.jobs import shutdown_scheduler, start_scheduler

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", mode=settings.app_mode.value, environment=settings.environment)
    start_scheduler()

    if settings.telegram_bot_token:
        from app.telegram_bot.bootstrap import build_application

        telegram_app = build_application()
        await telegram_app.initialize()
        app.state.telegram_application = telegram_app
        logger.info("app.telegram_bot_initialized")
    else:
        app.state.telegram_application = None
        logger.info("app.telegram_bot_skipped", reason="TELEGRAM_BOT_TOKEN not set (sandbox mode)")

    yield

    if app.state.telegram_application is not None:
        await app.state.telegram_application.shutdown()
    shutdown_scheduler()
    logger.info("app.shutdown")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(movie_nights.router, prefix="/api/movie-nights", tags=["movie-nights"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["tickets"])
app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(telegram_webhook.router, prefix="/api/telegram", tags=["telegram"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
