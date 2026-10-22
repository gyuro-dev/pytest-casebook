"""スクリーンショット用の対象: 小さなお店の価格・在庫・明細（CLI と Python 関数の両方で使える）。"""

from __future__ import annotations

import argparse
import sys
from typing import Any

PRICES = {"りんご": 150, "バナナ": 100, "メロン": 1200}
STOCK = {"りんご": 10, "バナナ": 0, "メロン": 2}
FREE_SHIPPING = 3000
SHIPPING = 500


class OutOfStock(Exception):
    """在庫が足りない。"""


def quote(item: str, quantity: int, member: bool = False) -> dict[str, Any]:
    """価格を計算する。会員は1割引き、5個以上はさらに50円引き。"""
    if item not in PRICES:
        raise LookupError(f"商品がありません: {item}")
    if quantity <= 0:
        raise ValueError("個数は1以上にしてください")
    subtotal = PRICES[item] * quantity
    discount = (subtotal // 10 if member else 0) + (50 if quantity >= 5 else 0)
    return {"item": item, "quantity": quantity, "discount": discount, "total": subtotal - discount}


def stock(item: str) -> dict[str, object]:
    """在庫を返す。"""
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0}


def reserve(item: str, quantity: int) -> int:
    """在庫を引き当て、残りの個数を返す。"""
    if STOCK.get(item, 0) < quantity:
        raise OutOfStock(f"{item} の在庫が足りません")
    STOCK[item] -= quantity
    return STOCK[item]


def points(total: int) -> int:
    """100円ごとに1ポイント。"""
    # 不具合: 端数を切り上げている（切り捨てが正しい）
    return -(-total // 100)


def coupon(code: str, total: int) -> int:
    """クーポンを当てた金額を返す（まだ作っていない）。"""
    raise NotImplementedError


def _receipt(orders: list[str]) -> list[str]:
    lines = []
    subtotal = 0
    for order in orders:
        item, quantity = order.split("=")
        q = quote(item, int(quantity))
        lines.append(f"{item} x {quantity}: {q['total']} 円")
        subtotal += q["total"]
    # 不具合: 「3,000円以上で送料無料」なのに、ちょうど3,000円では送料がかかる
    shipping = 0 if subtotal > FREE_SHIPPING else SHIPPING
    lines += [f"小計: {subtotal} 円", f"送料: {shipping} 円", f"合計: {subtotal + shipping} 円"]
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
    p_receipt = sub.add_parser("receipt", help="「商品=個数」を並べて明細を出す")
    p_receipt.add_argument("orders", nargs="+")
    args = parser.parse_args(argv)

    if args.cmd == "receipt":
        print("\n".join(_receipt(args.orders)))
        return 0
    if args.cmd == "price":
        try:
            q = quote(args.item, args.quantity, args.member)
        except (LookupError, ValueError) as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        print(f"{q['item']} x {q['quantity']} = {q['total']} 円（割引 {q['discount']} 円）")
        return 0

    s = stock(args.item)
    print(f"{s['item']}: {s['count']} 個" + ("" if s["available"] else "（在庫切れ）"))
    return 0 if s["available"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
