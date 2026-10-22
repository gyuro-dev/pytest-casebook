"""サンプルの対象: 小さなお店の価格計算と在庫確認（CLI と Python 関数の両方で使える）。"""

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
    """価格を計算する。会員は1割引き、5個以上はさらに50円引き。"""
    if item not in PRICES:
        raise LookupError(f"商品がありません: {item}")
    if quantity <= 0:
        raise ValueError("個数は1以上にしてください")
    subtotal = PRICES[item] * quantity
    discount = (subtotal // 10 if member else 0) + (50 if quantity >= 5 else 0)
    return Quote(item, quantity, PRICES[item], discount, subtotal - discount)


def stock(item: str) -> dict[str, object]:
    """在庫を返す。"""
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0}


def _receipt(orders_csv: Path, out: Path) -> int:
    """注文の CSV を読み、明細ファイルを書いて合計を表示する。"""
    if not orders_csv.exists():
        print(f"エラー: ファイルがありません: {orders_csv}", file=sys.stderr)
        return 1
    with orders_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    lines = []
    total = 0
    for row in rows:
        q = quote(row["item"], int(row["quantity"]))
        lines.append(f"{q.item} x {q.quantity}: {q.total} 円")
        total += q.total
    lines.append(f"合計: {total} 円")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} 件の明細を {out} に書きました（合計 {total} 円）")
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
    p_receipt = sub.add_parser("receipt", help="注文の CSV（item,quantity）から明細を作る")
    p_receipt.add_argument("orders_csv")
    p_receipt.add_argument("--out", default="receipt.txt")
    args = parser.parse_args(argv)

    if args.cmd == "receipt":
        return _receipt(Path(args.orders_csv), Path(args.out))
    if args.cmd == "price":
        try:
            q = quote(args.item, args.quantity, args.member)
        except (LookupError, ValueError) as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        print(f"{q.item} x {q.quantity} = {q.total} 円（割引 {q.discount} 円）")
        return 0

    s = stock(args.item)
    print(f"{s['item']}: {s['count']} 個" + ("" if s["available"] else "（在庫切れ）"))
    return 0 if s["available"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
