"""機能フラグで動きが変わる関数。"""

FLAGS: dict[str, bool] = {"new_pricing": False, "maintenance": False}


def price(base: int) -> int:
    if FLAGS["maintenance"]:
        raise RuntimeError("メンテナンス中です")
    return base * 9 // 10 if FLAGS["new_pricing"] else base
