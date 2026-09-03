from functools import lru_cache

from app.core.config import get_settings
from app.providers.showtime.base import ShowtimeProvider
from app.providers.showtime.manual import ManualShowtimeProvider


@lru_cache
def get_showtime_provider() -> ShowtimeProvider:
    settings = get_settings()
    if settings.showtime_provider == "manual":
        return ManualShowtimeProvider()
    # A real integration would be selected here, e.g.:
    # if settings.showtime_provider == "some_vendor": return SomeVendorProvider(...)
    raise ValueError(
        f"Unknown SHOWTIME_PROVIDER '{settings.showtime_provider}'. "
        "Only 'manual' is implemented — see providers/showtime/base.py for how to add a real one."
    )
