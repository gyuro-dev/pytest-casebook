"""サンプルの対象: DB（sqlite）を使う注文の処理。"""

from __future__ import annotations

import sqlite3


class OutOfStock(Exception):
    """在庫が足りない。"""


def place_order(conn: sqlite3.Connection, item: str, quantity: int) -> dict[str, object]:
    """在庫を減らして注文を記録する。在庫が足りなければ何も変えずに OutOfStock を出す。"""
    row = conn.execute("select count from stock where item = ?", (item,)).fetchone()
    if row is None or row[0] < quantity:
        raise OutOfStock(f"{item} の在庫が足りません（在庫 {row[0] if row else 0} 個）")
    conn.execute("update stock set count = count - ? where item = ?", (quantity, item))
    cur = conn.execute("insert into orders (item, quantity) values (?, ?)", (item, quantity))
    return {"order_id": cur.lastrowid, "item": item, "quantity": quantity}
