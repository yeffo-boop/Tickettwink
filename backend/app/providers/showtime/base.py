"""Showtime provider interface.

CORRECTION (see docs/FAILURE_SCENARIOS.md): an earlier version of this
docstring claimed no public showtime API exists at all. That was wrong —
real options exist:

  - AMC Developer Portal (developers.amctheatres.com) — free, self-serve
    API key, real showtime/theatre/movie catalog data. AMC theaters only.
  - MovieGlu (developer.movieglu.com) — paid, self-serve API key, broad
    multi-chain/multi-country coverage.
  - Fandango API (developer.fandango.com, via Fabric/Origin Nexus) — paid,
    requires sales approval, most comprehensive US coverage.
  - SerpApi Google Showtimes (serpapi.com/showtimes-results) — paid
    ($25/mo+), wraps Google's aggregated showtime search results rather
    than any single chain's own data.

None of these were integrated in the initial build because no provider had
been chosen yet and none had credentials available to test against — not
because no option exists. Per the project rules ("do not fabricate APIs,
endpoints, credentials, or capabilities"), this package still ships only:

  1. This abstract interface, so a real provider can be plugged in later
     without touching any calling code.
  2. A "manual" provider — an admin types in the cinema name and start
     time by hand (via the API or Telegram) and the app treats that as
     the source of truth. This is free for any theater/chain and remains
     a reasonable default for a small private group even after a real
     provider is wired in for AMC/etc. — it's the fallback for whichever
     theater isn't covered by whatever automated provider is configured.

To activate a real provider: implement `ShowtimeProvider` in a new module
(e.g. `live.py`) against the specific vendor's documented API (AMC's is the
only one with genuinely free access — see links above), wire it into
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
