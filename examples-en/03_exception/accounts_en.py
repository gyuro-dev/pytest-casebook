"""Functions that raise exceptions."""


class AccountError(Exception):
    """An account operation failed."""


class InsufficientFunds(AccountError):
    """The balance is too low."""


def withdraw(balance: int, amount: int) -> int:
    if amount <= 0:
        raise ValueError("The amount must be at least 1 yen")
    if amount > balance:
        raise InsufficientFunds(f"Insufficient funds (balance: {balance} yen)")
    return balance - amount
