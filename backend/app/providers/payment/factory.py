from functools import lru_cache

from app.core.config import get_settings
from app.providers.payment.base import PaymentProvider
from app.providers.payment.venmo_manual import VenmoManualProvider


@lru_cache
def get_payment_provider() -> PaymentProvider:
    settings = get_settings()
    if settings.payment_provider == "venmo_manual":
        return VenmoManualProvider(settings.venmo_handle)
    raise ValueError(f"Unknown PAYMENT_PROVIDER '{settings.payment_provider}'. Only 'venmo_manual' is implemented.")
