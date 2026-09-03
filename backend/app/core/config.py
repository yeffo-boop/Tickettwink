"""
Central application configuration.

Sandbox/LIVE mode separation (spec item 18):
APP_MODE=sandbox is the default and safe for local development / demos.
In sandbox mode, provider credentials are optional and every provider
falls back to its manual/mock implementation. APP_MODE=live requires
real credentials for any provider that is enabled; the app refuses to
start in live mode with a provider enabled but missing credentials for it.
"""
from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    SANDBOX = "sandbox"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "Ticket Twink"
    app_mode: AppMode = AppMode.SANDBOX
    environment: str = "development"
    secret_key: str = Field(default="CHANGE_ME_DEV_ONLY_INSECURE", description="JWT signing key")
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    api_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Database ---
    database_url: str = "postgresql+asyncpg://tickettwink:tickettwink_dev_local@localhost:5432/tickettwink_dev"
    database_url_sync: str = "postgresql+psycopg2://tickettwink:tickettwink_dev_local@localhost:5432/tickettwink_dev"

    # --- Telegram ---
    telegram_bot_token: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    telegram_bot_username: Optional[str] = None

    # --- TMDB ---
    tmdb_api_key: Optional[str] = None
    tmdb_api_base_url: str = "https://api.themoviedb.org/3"

    # --- Showtime provider ---
    showtime_provider: str = "manual"  # "manual" | future: "fandango", "atom", etc.
    showtime_api_key: Optional[str] = None
    showtime_api_base_url: Optional[str] = None

    # --- Payments (Venmo is manual-confirmation only; no Venmo public API exists) ---
    payment_provider: str = "venmo_manual"
    venmo_handle: Optional[str] = None

    # --- Storage ---
    storage_backend: str = "local"  # "local" | future: "s3"
    storage_local_path: str = "./data/tickets"
    storage_s3_bucket: Optional[str] = None
    storage_s3_region: Optional[str] = None

    # --- Notifications / retry policy ---
    notification_max_retries: int = 5
    notification_retry_base_seconds: int = 30  # exponential backoff base

    # --- Circuit breaker defaults for external providers ---
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_reset_seconds: int = 120

    @model_validator(mode="after")
    def validate_live_mode_requirements(self) -> "Settings":
        if self.app_mode == AppMode.LIVE:
            missing = []
            if self.secret_key == "CHANGE_ME_DEV_ONLY_INSECURE":
                missing.append("SECRET_KEY")
            if not self.telegram_bot_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not self.tmdb_api_key:
                missing.append("TMDB_API_KEY")
            if missing:
                raise ValueError(
                    "APP_MODE=live requires the following configuration to be set: "
                    + ", ".join(missing)
                    + ". Set APP_MODE=sandbox to run without them."
                )
        return self

    @property
    def is_live(self) -> bool:
        return self.app_mode == AppMode.LIVE


@lru_cache
def get_settings() -> Settings:
    return Settings()
