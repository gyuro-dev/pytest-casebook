"""An item catalog. Its content depends on where it connects (local sample data or staging data)."""

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
        """Local sample data (runs right away on your machine)."""
        return cls("local", {"apple": 120, "banana": 80})

    @classmethod
    def staging(cls) -> Catalog:
        """Staging data (a real project reads it from an API or DB; a file stands in here)."""
        path = Path(__file__).with_name("staging_prices.json")
        return cls("staging", json.loads(path.read_text(encoding="utf-8")))


def list_items(catalog: Catalog) -> list[dict[str, object]]:
    return [{"item": k, "price": v} for k, v in sorted(catalog.prices.items())]


def price(catalog: Catalog, item: str) -> int:
    if item not in catalog.prices:
        raise LookupError(f"No such item: {item}")
    return catalog.prices[item]


def reset(catalog: Catalog) -> str:
    """Reset the data (an operation that must only be used locally)."""
    if catalog.name != "local":
        raise PermissionError("Reset is only allowed on local")
    return "Reset done"
