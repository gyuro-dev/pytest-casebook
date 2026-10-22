"""送料の計算。"""

FREE_LINE = 5000


def fee(region: str, amount: int, member: bool = False) -> int:
    if amount >= FREE_LINE or member:
        return 0
    return {"kanto": 600, "kansai": 700, "okinawa": 1500}[region]
