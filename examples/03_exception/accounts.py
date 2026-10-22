"""例外を出す関数。"""


class AccountError(Exception):
    """口座の処理の失敗。"""


class InsufficientFunds(AccountError):
    """残高が足りない。"""


def withdraw(balance: int, amount: int) -> int:
    if amount <= 0:
        raise ValueError("金額は1円以上にしてください")
    if amount > balance:
        raise InsufficientFunds(f"残高が足りません（残高 {balance} 円）")
    return balance - amount
