"""Manual showtime provider: the source of truth is whatever an admin typed
into the Showtime record. `get_showtime` never calls out to the network, so
it cannot fail with a provider outage — the corresponding failure scenario
("showtime API unavailable") is handled by never depending on one unless
SHOWTIME_PROVIDER is set to a real integration. Admin-driven changes go
through movie_night_service.update_showtime(), which is what actually
flags a MovieNight as SHOWTIME_CHANGED and fires notifications.
"""
from typing import Optional

from app.providers.showtime.base import ShowtimeProvider, ShowtimeResult


class ManualShowtimeProvider(ShowtimeProvider):
    async def get_showtime(self, external_showtime_id: str) -> Optional[ShowtimeResult]:
        # Nothing to poll — manual showtimes only change when an admin
        # edits them directly, which happens via the service layer.
        return None
