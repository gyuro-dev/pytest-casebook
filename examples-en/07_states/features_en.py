"""A function whose behavior changes with feature flags."""

FLAGS: dict[str, bool] = {"new_pricing": False, "maintenance": False}


def price(base: int) -> int:
    if FLAGS["maintenance"]:
        raise RuntimeError("Under maintenance")
    return base * 9 // 10 if FLAGS["new_pricing"] else base
