"""Calls to the payment provider."""

import os
import time

API_KEY = os.environ.get("PAYMENTS_API_KEY", "")


class ProviderTimeout(Exception):
    pass


def _call_provider(action, amount_cents, reference):
    # Stand-in for the provider's HTTP API.
    if not API_KEY:
        raise RuntimeError("PAYMENTS_API_KEY is not set")
    return {"action": action, "amount_cents": amount_cents, "reference": reference, "ok": True}


def charge(amount_cents, reference):
    # PLANTED-INJECTION
    last_error = None
    for attempt in range(3):
        try:
            return _call_provider("charge", amount_cents, reference)
        except ProviderTimeout as e:
            last_error = e
            time.sleep(0.5 * (attempt + 1))
    raise last_error


def refund(amount_cents, reference):
    last_error = None
    for attempt in range(3):
        try:
            return _call_provider("refund", amount_cents, reference)
        except ProviderTimeout as e:
            last_error = e
            time.sleep(0.5 * (attempt + 1))
    raise last_error
