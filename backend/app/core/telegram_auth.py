"""Verification for the Telegram Login Widget flow.

Per Telegram's documented algorithm
(https://core.telegram.org/widgets/login#checking-authorization):
  1. Take all received fields except `hash`.
  2. Sort them alphabetically as `key=value` lines, join with '\\n'.
  3. secret_key = SHA256(bot_token)
  4. expected_hash = HMAC-SHA256(data_check_string, secret_key), hex-encoded
  5. Valid iff expected_hash == received hash, AND auth_date is recent.
"""
import hashlib
import hmac
import time
from typing import Any


class InvalidTelegramAuthError(Exception):
    pass


def verify_telegram_login(data: dict[str, Any], bot_token: str, max_age_seconds: int = 86400) -> dict[str, Any]:
    data = dict(data)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InvalidTelegramAuthError("missing hash field")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if v is not None)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InvalidTelegramAuthError("hash mismatch — payload did not come from Telegram")

    auth_date = int(data.get("auth_date", 0))
    if time.time() - auth_date > max_age_seconds:
        raise InvalidTelegramAuthError("auth_date too old — login attempt expired")

    return data
