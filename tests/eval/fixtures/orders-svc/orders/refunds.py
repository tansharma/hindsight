"""Refund handling."""

from orders import payments, store


def refund_order(order_id):
    """Refund an order in full. Called from the HTTP handler."""
    order = store.get(order_id)
    if order is None:
        return {"status": 404}
    payments.refund(order["amount_cents"], reference=order_id)
    return {"status": 200, "order_id": order_id}
