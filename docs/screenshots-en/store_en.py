"""The target for the screenshots: prices, stock and receipts of a small shop (CLI + functions)."""

from __future__ import annotations

import argparse
import sys
from typing import Any

PRICES = {"apple": 15, "banana": 10, "melon": 120}
STOCK = {"apple": 10, "banana": 0, "melon": 2}
FREE_SHIPPING = 300
SHIPPING = 50


class OutOfStock(Exception):
    """Not enough stock."""


def quote(item: str, quantity: int, member: bool = False) -> dict[str, Any]:
    """Calculate the price. Members get 10% off, and 5 or more items get another $5 off."""
    if item not in PRICES:
        raise LookupError(f"no such item: {item}")
    if quantity <= 0:
        raise ValueError("quantity must be 1 or more")
    subtotal = PRICES[item] * quantity
    discount = (subtotal // 10 if member else 0) + (5 if quantity >= 5 else 0)
    return {"item": item, "quantity": quantity, "discount": discount, "total": subtotal - discount}


def stock(item: str) -> dict[str, object]:
    """Return the stock."""
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0}


def reserve(item: str, quantity: int) -> int:
    """Reserve stock and return how many are left."""
    if STOCK.get(item, 0) < quantity:
        raise OutOfStock(f"not enough {item} in stock")
    STOCK[item] -= quantity
    return STOCK[item]


def points(total: int) -> int:
    """1 point per $10."""
    # Bug: rounds up (it should round down)
    return -(-total // 10)


def coupon(code: str, total: int) -> int:
    """Return the total after a coupon (not implemented yet)."""
    raise NotImplementedError


def _receipt(orders: list[str]) -> list[str]:
    lines = []
    subtotal = 0
    for order in orders:
        item, quantity = order.split("=")
        q = quote(item, int(quantity))
        lines.append(f"{item} x {quantity}: ${q['total']}")
        subtotal += q["total"]
    # Bug: shipping should be free from $300, but exactly $300 still pays shipping
    shipping = 0 if subtotal > FREE_SHIPPING else SHIPPING
    lines += [f"Subtotal: ${subtotal}", f"Shipping: ${shipping}", f"Total: ${subtotal + shipping}"]
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_price = sub.add_parser("price")
    p_price.add_argument("item")
    p_price.add_argument("quantity", type=int)
    p_price.add_argument("--member", action="store_true")
    p_stock = sub.add_parser("stock")
    p_stock.add_argument("item")
    p_receipt = sub.add_parser("receipt", help="print a receipt for item=quantity pairs")
    p_receipt.add_argument("orders", nargs="+")
    args = parser.parse_args(argv)

    if args.cmd == "receipt":
        print("\n".join(_receipt(args.orders)))
        return 0
    if args.cmd == "price":
        try:
            q = quote(args.item, args.quantity, args.member)
        except (LookupError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"{q['item']} x {q['quantity']} = ${q['total']} (discount ${q['discount']})")
        return 0

    s = stock(args.item)
    print(f"{s['item']}: {s['count']}" + ("" if s["available"] else " (out of stock)"))
    return 0 if s["available"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
