"""The function under test (the amount of an invoice)."""


def total(amounts: list[int]) -> int:
    """The sum of the lines plus 10% tax (fractions are dropped)."""
    return sum(amounts) * 110 // 100
