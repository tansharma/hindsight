# orders-svc

Order intake service for the storefront.

## Guarantees

- **Exactly-once intake.** Every order is created exactly once. Clients send
  an `Idempotency-Key` header, and `orders/intake.py` returns the existing
  order when a key is seen again, so a retried request never creates a
  duplicate.
- **Asynchronous refunds.** Refunds are queued and processed by a background
  worker, so a slow payment provider never blocks the request.

## Layout

- `orders/intake.py` — HTTP-facing order creation.
- `orders/store.py` — order persistence.
- `orders/payments.py` — calls to the payment provider.
- `orders/refunds.py` — refund handling.

## Configuration

`PAYMENTS_API_KEY` is read from the environment (see `.env` locally).
