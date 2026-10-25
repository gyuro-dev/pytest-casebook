"""Computes the shipping fee from the order subtotal."""

FREE_LINE = 3000
FEE = 500


def fee(subtotal: int) -> int:
    return 0 if subtotal >= FREE_LINE else FEE
