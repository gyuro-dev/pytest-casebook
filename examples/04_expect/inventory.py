"""在庫を確かめる CLI と関数。"""

import sys
from datetime import date

STOCK = {"apple": 10, "banana": 0}


def check(item: str) -> dict[str, object]:
    count = STOCK.get(item, 0)
    return {"item": item, "count": count, "available": count > 0, "checked_on": str(date.today())}


if __name__ == "__main__":
    result = check(sys.argv[1])
    if not result["available"]:
        print(f"{result['item']}: 在庫切れ", file=sys.stderr)
        sys.exit(3)
    print(f"{result['item']}: {result['count']} 個")
