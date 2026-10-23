"""確かめる対象の関数（請求書の金額）。"""


def total(amounts: list[int]) -> int:
    """明細の合計に、消費税（10%）を足した金額（円未満は切り捨て）。"""
    return sum(amounts) * 110 // 100
