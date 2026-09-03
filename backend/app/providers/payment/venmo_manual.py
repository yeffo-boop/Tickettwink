from app.providers.payment.base import PaymentInstructions, PaymentProvider


class VenmoManualProvider(PaymentProvider):
    def __init__(self, venmo_handle: str | None):
        self._handle = venmo_handle

    def get_payment_instructions(self, amount_cents: int, memo: str) -> PaymentInstructions:
        dollars = amount_cents / 100
        handle = self._handle or "(organizer Venmo handle not configured — set VENMO_HANDLE)"
        return PaymentInstructions(
            provider_name="venmo_manual",
            display_instructions=(
                f"Send ${dollars:.2f} to {handle} on Venmo with the note '{memo}', "
                "then tap 'I paid' — an organizer will confirm receipt."
            ),
            handle=self._handle,
        )
