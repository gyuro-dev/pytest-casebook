"""注文金額から送料を求める。"""

FREE_LINE = 3000
FEE = 500


def fee(subtotal: int) -> int:
    return 0 if subtotal >= FREE_LINE else FEE
