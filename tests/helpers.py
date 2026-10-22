"""テストで共通に使う、ケースファイルを作る・期待出力を読むための関数。"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# YAML の command に書く Python のパス
# （Windows でも \ が shell の書き方として消えないよう、/ 区切りにする）
PY = Path(sys.executable).as_posix()

# テストで call: と command: の対象にする calc モジュールの中身
CALC_MODULE = """
import dataclasses
import sys


@dataclasses.dataclass
class Point:
    x: int
    y: int


def add(a, b):
    return a + b


def divide(a, b):
    return a / b


def point(x, y):
    print("point を作ります")
    return Point(x, y)


def tags():
    return {"b", "a"}


def main(argv):
    if not argv:
        print("引数がありません", file=sys.stderr)
        return 2
    print(sum(int(a) for a in argv))
    return 0
"""


def write_casebook(pytester: pytest.Pytester, text: str, name: str = "casebook_calc") -> Path:
    """ケースファイル（<name>.yaml）を pytester の一時ディレクトリに書く。"""
    return pytester.makefile(".yaml", **{name: textwrap.dedent(text)})


def golden(pytester: pytest.Pytester, case: str, stem: str = "casebook_calc") -> str:
    """既定の置き場所（golden/<stem>/）にある期待出力ファイルを読む。"""
    return (pytester.path / "golden" / stem / f"{case}.txt").read_text(encoding="utf-8")
