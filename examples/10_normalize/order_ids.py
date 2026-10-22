"""実行のたびに変わる値（ID・日時・UUID）を出す関数。"""

import itertools
import uuid
from datetime import UTC, datetime

_counter = itertools.count(1000 + int(datetime.now().timestamp()) % 1000)


def create(item: str) -> dict[str, object]:
    return {
        "order_id": f"ord-{next(_counter)}",
        "request_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "item": item,
    }


def receipt(item: str) -> str:
    order = create(item)
    return f"注文 {order['order_id']}（{order['created_at']}）: {item}"
