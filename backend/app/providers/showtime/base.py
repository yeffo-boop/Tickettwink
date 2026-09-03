"""Showtime provider interface.

IMPORTANT — no fabricated API: there is no standard, publicly-available
"movie showtime" API that this app can integrate against out of the box.
(Fandango, AMC, and Atom Tickets do not publish open public APIs for
third-party showtime lookup; aggregator products exist but are paid,
region-limited, and change terms often.) Per the project rules ("do not
fabricate APIs, endpoints, credentials, or capabilities"), this package
ships only:

  1. This abstract interface, so a real provider can be plugged in later
     without touching any calling code.
  2. A "manual" provider — an admin types in the cinema name and start
     time by hand (via the API or Telegram) and the app treats that as
     the source of truth, checking it periodically the same way a real
     provider's data would be checked.

To activate a real provider: implement `ShowtimeProvider` in a new module
(e.g. `live.py`) against the specific vendor's documented API, wire it into
`factory.py` behind `SHOWTIME_PROVIDER=<name>`, and set the corresponding
API key/base URL in configuration. Until then, `SHOWTIME_PROVIDER=manual`
is what runs, in both sandbox and live app modes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ShowtimeResult:
    external_showtime_id: Optional[str]
    cinema_name: str
    starts_at: datetime
    raw: Optional[dict] = None


class ShowtimeProvider(ABC):
    @abstractmethod
    async def get_showtime(self, external_showtime_id: str) -> Optional[ShowtimeResult]:
        """Look up the current state of a previously-recorded showtime.

        Returns None if the provider no longer has any record of it (may
        indicate the showing was pulled/cancelled). Raises
        ProviderUnavailableError if the provider cannot be reached at all —
        callers must treat that as "unknown", not "cancelled".
        """
