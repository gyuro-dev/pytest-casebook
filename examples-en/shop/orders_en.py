"""Sample target: order processing that uses a DB (sqlite)."""

from __future__ import annotations

import sqlite3


class OutOfStock(Exception):
    """Not enough stock."""


def place_order(conn: sqlite3.Connection, item: str, quantity: int) -> dict[str, object]:
    """Reduce the stock and record the order. Without enough stock, change nothing and raise."""
    row = conn.execute("select count from stock where item = ?", (item,)).fetchone()
    if row is None or row[0] < quantity:
        raise OutOfStock(f"Not enough {item} in stock ({row[0] if row else 0} left)")
    conn.execute("update stock set count = count - ? where item = ?", (quantity, item))
    cur = conn.execute("insert into orders (item, quantity) values (?, ?)", (item, quantity))
    return {"order_id": cur.lastrowid, "item": item, "quantity": quantity}
