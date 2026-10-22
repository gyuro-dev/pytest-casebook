"""A CLI and a function that check stock."""

import sys
from datetime import date

STOCK = {"apple": 10, "banana": 0}


def check(item: str) -> dict[str, object]:
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0, "checked_on": str(date.today())}


if __name__ == "__main__":
    result = check(sys.argv[1])
    if not result["available"]:
        print(f"{result['item']}: out of stock", file=sys.stderr)
        sys.exit(3)
    print(f"{result['item']}: {result['count']} in stock")
