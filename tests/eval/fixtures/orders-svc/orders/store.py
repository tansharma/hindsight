"""Order persistence. In-memory for now; swapped for Postgres in production."""

import itertools

_orders = {}
_ids = itertools.count(1)


def insert(order):
    """Store a new order and return its id."""
    order_id = next(_ids)
    _orders[order_id] = dict(order, id=order_id)
    return order_id


def get(order_id):
    return _orders.get(order_id)


def find_by_key(idempotency_key):
    """Return the order created with this idempotency key, if any."""
    for order in _orders.values():
        if order.get("idempotency_key") == idempotency_key:
            return order
    return None
