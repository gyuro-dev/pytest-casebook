"""商品のカタログ。どこにつなぐか（ローカルの見本のデータか、ステージングのデータか）で中身が変わる。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Catalog:
    name: str
    prices: dict[str, int]

    @classmethod
    def local(cls) -> Catalog:
        """ローカルの見本のデータ（手元ですぐ動かせる）。"""
        return cls("local", {"apple": 120, "banana": 80})

    @classmethod
    def staging(cls) -> Catalog:
        """ステージングのデータ（本物では API や DB から取る。ここではファイルで代わりにする）。"""
        path = Path(__file__).with_name("staging_prices.json")
        return cls("staging", json.loads(path.read_text(encoding="utf-8")))


def list_items(catalog: Catalog) -> list[dict[str, object]]:
    return [{"item": k, "price": v} for k, v in sorted(catalog.prices.items())]


def price(catalog: Catalog, item: str) -> int:
    if item not in catalog.prices:
        raise LookupError(f"{item} はありません")
    return catalog.prices[item]


def reset(catalog: Catalog) -> str:
    """データを初期化する（ローカルでしか使ってはいけない操作）。"""
    if catalog.name != "local":
        raise PermissionError("ローカル以外では初期化できません")
    return "初期化しました"
