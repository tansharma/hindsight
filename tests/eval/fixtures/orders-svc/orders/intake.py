"""HTTP-facing order creation."""

import time

from orders import payments, store


def create_order(request):
    """Create an order from an HTTP request dict and charge the customer."""
    key = request["headers"].get("Idempotency-Key")
    order = {
        "customer": request["body"]["customer"],
        "amount_cents": request["body"]["amount_cents"],
        "idempotency_key": key,
    }
    order_id = store.insert(order)

    last_error = None
    for attempt in range(3):
        try:
            payments.charge(order["amount_cents"], reference=order_id)
            break
        except payments.ProviderTimeout as e:
            last_error = e
            time.sleep(0.5 * (attempt + 1))
    else:
        raise last_error
    return {"status": 201, "order_id": order_id}
