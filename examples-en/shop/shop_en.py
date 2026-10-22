"""Sample target: pricing and stock for a small shop (usable as a CLI and as Python functions)."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

PRICES = {"apple": 120, "banana": 80, "melon": 980}
STOCK = {"apple": 10, "banana": 0, "melon": 2}


@dataclass
class Quote:
    item: str
    quantity: int
    unit_price: int
    discount: int
    total: int


def quote(item: str, quantity: int, member: bool = False) -> Quote:
    """Calculate the price. Members get 10% off, and 5 or more gets another 50 yen off."""
    if item not in PRICES:
        raise LookupError(f"no such item: {item}")
    if quantity <= 0:
        raise ValueError("the quantity must be at least 1")
    subtotal = PRICES[item] * quantity
    discount = (subtotal // 10 if member else 0) + (50 if quantity >= 5 else 0)
    return Quote(item, quantity, PRICES[item], discount, subtotal - discount)


def stock(item: str) -> dict[str, object]:
    """Return the stock."""
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0}


def _receipt(orders_csv: Path, out: Path) -> int:
    """Read the order CSV, write the receipt file and show the total."""
    if not orders_csv.exists():
        print(f"error: file not found: {orders_csv}", file=sys.stderr)
        return 1
    with orders_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    lines = []
    total = 0
    for row in rows:
        q = quote(row["item"], int(row["quantity"]))
        lines.append(f"{q.item} x {q.quantity}: {q.total} yen")
        total += q.total
    lines.append(f"Total: {total} yen")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} line(s) to {out} (total {total} yen)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_price = sub.add_parser("price")
    p_price.add_argument("item")
    p_price.add_argument("quantity", type=int)
    p_price.add_argument("--member", action="store_true")
    p_stock = sub.add_parser("stock")
    p_stock.add_argument("item")
    p_receipt = sub.add_parser("receipt", help="make a receipt from an order CSV (item,quantity)")
    p_receipt.add_argument("orders_csv")
    p_receipt.add_argument("--out", default="receipt.txt")
    args = parser.parse_args(argv)

    if args.cmd == "receipt":
        return _receipt(Path(args.orders_csv), Path(args.out))
    if args.cmd == "price":
        try:
            q = quote(args.item, args.quantity, args.member)
        except (LookupError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"{q.item} x {q.quantity} = {q.total} yen (discount {q.discount} yen)")
        return 0

    s = stock(args.item)
    print(f"{s['item']}: {s['count']} in stock" + ("" if s["available"] else " (out of stock)"))
    return 0 if s["available"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
