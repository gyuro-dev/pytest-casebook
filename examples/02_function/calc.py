"""確かめたい Python の関数。"""

from dataclasses import dataclass


@dataclass
class Summary:
    count: int
    total: int
    average: float


def add(a: int, b: int) -> int:
    return a + b


def summarize(values: list[int]) -> Summary:
    total = sum(values)
    return Summary(count=len(values), total=total, average=total / len(values))
