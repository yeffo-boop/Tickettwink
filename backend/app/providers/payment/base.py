"""Payment provider interface.

IMPORTANT — no fabricated API: Venmo does not publish a public API for
verifying incoming peer-to-peer payments (its old public API was
deprecated years ago and its current developer platform is for merchant
"Pay with Venmo" checkout, not P2P reconciliation). So this app cannot
automatically confirm "did user X actually pay me on Venmo" — nothing
honestly can, without violating Venmo's terms via unofficial scraping,
which this project will not do.

What ships instead:
  1. This abstract interface (provider-agnostic on purpose — the core
     payment_service never imports Venmo-specific code).
  2. `VenmoManualProvider` — the organizer's @venmo-handle is shown to
     members with the exact amount owed; the member pays externally in the
     Venmo app; an admin (or the payer, subject to admin confirmation)
     marks the payment as received in Ticket Twink. All reconciliation is
     manual by design.

To activate real automatic verification: integrate a payment processor
that actually supports server-side webhooks/verification (e.g. Stripe),
implement `PaymentProvider` for it in a new module, and wire it in behind
PAYMENT_PROVIDER=<name>.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PaymentInstructions:
    provider_name: str
    display_instructions: str
    handle: str | None


class PaymentProvider(ABC):
    @abstractmethod
    def get_payment_instructions(self, amount_cents: int, memo: str) -> PaymentInstructions:
        """Returns what to show the payer. Never performs a network call —
        must not be able to fail due to provider unavailability."""
