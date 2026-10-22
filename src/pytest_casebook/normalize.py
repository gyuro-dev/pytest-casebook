"""実行ごとに変わる値（ID・日時など）を、決まった表記に置き換える。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# ini の casebook_builtin_patterns = true（既定）のときに使う置き換え
BUILTIN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
        "<datetime>",
    ),
    (re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), "<uuid>"),
]


def compile_patterns(
    patterns: Iterable[tuple[str | re.Pattern[str], str]],
) -> list[tuple[re.Pattern[str], str]]:
    """文字列の正規表現をコンパイルする（コンパイル済みのものはそのまま）。"""
    return [(re.compile(p) if isinstance(p, str) else p, repl) for p, repl in patterns]


@dataclass
class Normalizer:
    """
    出力を正規化する。

    1. `placeholders`（実際の値 -> 置き換え後）を、長い値から順に置き換える
       （短い ID が長い ID の一部を先に置き換えてしまわないように）
    2. `patterns`（正規表現 -> 置き換え後）を順に当てる
    3. 改行を LF にそろえ、行末の空白を消す（末尾の改行もなくなる）
    """

    placeholders: list[tuple[str, str]] = field(default_factory=list)
    patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list)

    def __call__(self, text: str) -> str:
        return "\n".join(line.rstrip() for line in self.replace(text).splitlines())

    def replace(self, text: str) -> str:
        """1 と 2 だけを当てる（改行や空白はそのまま。値の中の文字列に使う）。"""
        pairs = [(real, repl) for real, repl in self.placeholders if real and real != repl]
        for real, repl in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
            text = text.replace(real, repl)
        for pattern, repl in self.patterns:
            text = pattern.sub(repl, text)
        return text
