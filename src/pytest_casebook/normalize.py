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


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff]")
# 改行として扱うもの（str.splitlines は \x0c や \u2028 でも行を分けるので使わない）
_NEWLINE_RE = re.compile(r"\r\n|\r|\n")


def show_controls(text: str) -> str:
    """
    制御文字（ANSI の色の ESC など）を `\\x1b` の形にして見えるようにする（改行とタブは残す）。

    失敗の差分に生のまま出すと、端末が色として解釈して、どこが違うのか見えないため。
    `\\u2028` のような行の区切りと、UTF-8 にできないサロゲート文字も `\\u2028` の形にする
    （サロゲート文字は pytest-xdist の結果の受け渡しや、レポートの書き込みで例外になる）。
    """

    def escaped(match: re.Match[str]) -> str:
        code = ord(match.group())
        return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"

    return _CONTROL_RE.sub(escaped, text)


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
    3. 改行（CRLF・CR・LF）を LF にそろえ、行末の空白を消す（末尾の改行もなくなる）。
       `\\x0c` や `\\u2028` は改行にしない（出力の違いを見逃さないように）
    """

    placeholders: list[tuple[str, str]] = field(default_factory=list)
    patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list)

    def __call__(self, text: str) -> str:
        lines = _NEWLINE_RE.sub("\n", self.replace(text)).removesuffix("\n").split("\n")
        return "\n".join(line.rstrip() for line in lines)

    def replace(self, text: str) -> str:
        """1 と 2 だけを当てる（改行や空白はそのまま。値の中の文字列に使う）。"""
        pairs = [(real, repl) for real, repl in self.placeholders if real and real != repl]
        for real, repl in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
            text = text.replace(real, repl)
        for pattern, repl in self.patterns:
            text = pattern.sub(repl, text)
        return text
