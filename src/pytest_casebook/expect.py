"""
YAML の `expect:` に書いた期待値と、実際の結果を比べる。

- 文字列（stdout / stderr / raises / body）: そのまま書けば完全一致（末尾の改行は無視）、
  `{contains: ...}` なら含まれていればよい、`{regex: ...}` なら正規表現に合えばよい
- 値（return / json / observe の対象）: 辞書は書いたキーだけを比べ、リストは件数と各要素を比べ、
  それ以外は完全一致。値の中では、`$` で始まる1つのキーだけの辞書を「比べ方」として扱う
  （データのキーと紛れないように `$` を付ける）

  - `{$contains: ...}` / `{$regex: ...}`: 文字列が含む / 正規表現に合う
  - `{$unordered: [...]}`: 順序を問わず、件数と各要素が一致する
  - `{$includes: [...]}`: 書いた要素がすべて含まれていればよい（ほかの要素があってもよい）
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from typing import Any

from .messages import MESSAGES, error
from .serialize import compact

# 値の中に書ける比べ方
VALUE_MATCHERS = ("$contains", "$regex", "$unordered", "$includes")


def _show(value: Any) -> str:
    return compact(value)


def value_matcher(expected: Any) -> tuple[str, Any] | None:
    """`{$contains: ...}` のような比べ方なら `(名前, 中身)` を返す。そうでなければ None。"""
    if isinstance(expected, dict) and len(expected) == 1:
        ((key, body),) = expected.items()
        if isinstance(key, str) and key.startswith("$"):
            return key, body
    return None


def match_text(expected: Any, actual: str, label: str, lang: str = "en") -> list[str]:
    """
    文字列の期待値と比べ、違いの説明のリストを返す（一致すれば空）。

    expected は YAML を読むときに確かめ済みのもの（文字列か {contains} / {regex}）。
    """
    m = MESSAGES[lang]
    actual = actual.rstrip("\n")
    if isinstance(expected, str):
        expected = expected.rstrip("\n")
        if expected == actual:
            return []
        if "\n" in expected or "\n" in actual:
            # 末尾の改行は取り除いてあるので、行は改行なしで比べて、あとで改行でつなぐ
            # （keepends で比べると、最後の行どうしが1行につながってしまう）
            diff = "\n".join(
                difflib.unified_diff(
                    expected.splitlines(),
                    actual.splitlines(),
                    fromfile=m["diff_expected"].format(label=label),
                    tofile=m["diff_actual"].format(label=label),
                    lineterm="",
                )
            )
            return [m["text_differs"].format(label=label) + f"\n{diff.rstrip()}"]
        return [_mismatch(m, label, expected, actual)]

    ((matcher, pattern),) = expected.items()
    matcher = matcher.lstrip("$")  # {contains} と {$contains} は同じ
    if matcher == "contains" and pattern not in actual:
        return [
            m["not_contained"].format(label=label, pattern=_show(pattern), actual=_show(actual))
        ]
    if matcher == "regex" and not re.search(pattern, actual, re.MULTILINE):
        return [
            m["no_regex_match"].format(label=label, pattern=_show(pattern), actual=_show(actual))
        ]
    return []


def _mismatch(m: dict[str, str], label: str, expected: Any, actual: Any) -> str:
    return m["mismatch"].format(label=label, expected=_show(expected), actual=_show(actual))


def match_value(expected: Any, actual: Any, label: str, lang: str = "en") -> list[str]:
    """
    値の期待値と比べ、違いの説明のリストを返す（一致すれば空）。

    :param expected: YAML に書いた期待値
    :param actual: 実際の値（`to_jsonable` で変換し、正規化したもの）
    :param label: 説明に使う場所の名前（例: `db.users[1].name`）
    :param lang: 説明の言語（`ja` か `en`）
    :return: 違いの説明のリスト（一致すれば空）
    """
    m = MESSAGES[lang]
    matcher = value_matcher(expected)
    if matcher is not None:
        return _match_with(matcher[0], matcher[1], actual, label, lang)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [_mismatch(m, label, expected, actual)]
        problems: list[str] = []
        for key, value in expected.items():
            if key not in actual:
                problems.append(m["missing_key"].format(label=f"{label}.{key}"))
            else:
                problems += match_value(value, actual[key], f"{label}.{key}", lang)
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [_mismatch(m, label, expected, actual)]
        problems = []
        if len(expected) != len(actual):
            problems.append(
                m["count_differs"].format(label=label, expected=len(expected), actual=len(actual))
            )
        for i, (e, a) in enumerate(zip(expected, actual, strict=False)):
            problems += match_value(e, a, f"{label}[{i}]", lang)
        return problems
    if isinstance(expected, str) and isinstance(actual, str):
        # ファイルの内容などは末尾の改行の有無を問わない（YAML の書き方で変わりやすいため）
        if expected.rstrip("\n") != actual.rstrip("\n"):
            return [_mismatch(m, label, expected, actual)]
        return []
    # True == 1 にならないよう、真偽値は型も比べる
    if isinstance(expected, bool) != isinstance(actual, bool) or expected != actual:
        return [_mismatch(m, label, expected, actual)]
    return []


def _match_with(name: str, body: Any, actual: Any, label: str, lang: str) -> list[str]:
    """`$` で始まる比べ方で比べる。"""
    m = MESSAGES[lang]
    if name in ("$contains", "$regex"):
        if not isinstance(actual, str):
            return [m["not_string"].format(label=label, actual=_show(actual))]
        return match_text({name: body}, actual, label, lang)
    if not isinstance(actual, list):
        return [m["not_list"].format(label=label, actual=_show(actual))]
    if name == "$unordered" and len(body) != len(actual):
        return [m["count_differs"].format(label=label, expected=len(body), actual=len(actual))]
    # 期待の要素と実際の要素を、1対1で、できるだけ多く組み合わせる（二部グラフの最大マッチング）。
    # 先頭から順に貪欲に組むと、{type: A} のような広い条件が先にあるときに、
    # 後ろの細かい条件に合うはずの要素を取ってしまい、書く順番によって失敗してしまう
    fits = [
        [j for j, value in enumerate(actual) if not match_value(item, value, label, lang)]
        for item in body
    ]
    owner: dict[int, int] = {}  # 実際の要素 -> 組んだ期待の要素

    def assign(i: int, seen: set[int]) -> bool:
        """期待の i 番目を、空いている（または付け替えられる）実際の要素に割り当てる。"""
        for j in fits[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or assign(owner[j], seen):
                owner[j] = i
                return True
        return False

    matched = {i for i in range(len(body)) if assign(i, set())}
    return [
        m["no_element"].format(label=label, item=_show(item), index=i)
        for i, item in enumerate(body)
        if i not in matched
    ]


def find_matcher_errors(value: Any, label: str) -> list[str]:
    """期待値の中の `$` で始まる比べ方の書き間違いを探す（YAML を読むときに確かめる）。"""
    matcher = value_matcher(value)
    if matcher is not None:
        name, body = matcher
        if name not in VALUE_MATCHERS:
            known = " / ".join(VALUE_MATCHERS)
            return [error("unknown_matcher", where=label, name=name, known=known)]
        if name in ("$contains", "$regex") and not isinstance(body, str):
            return [error("matcher_string", where=label, name=name)]
        if name == "$regex":
            try:
                re.compile(body)
            except re.error as e:
                return [error("bad_regex", where=label, error=e)]
        if name in ("$unordered", "$includes"):
            if not isinstance(body, list):
                return [error("matcher_list", where=label, name=name)]
            return [
                err for i, v in enumerate(body) for err in find_matcher_errors(v, f"{label}[{i}]")
            ]
        return []
    if isinstance(value, dict):
        return [err for k, v in value.items() for err in find_matcher_errors(v, f"{label}.{k}")]
    if isinstance(value, list):
        return [err for i, v in enumerate(value) for err in find_matcher_errors(v, f"{label}[{i}]")]
    return []


def map_strings(value: Any, func: Callable[[str], str]) -> Any:
    """JSON にできる値の中の文字列すべてに func を当てる（正規化に使う）。"""
    if isinstance(value, str):
        return func(value)
    if isinstance(value, list):
        return [map_strings(v, func) for v in value]
    if isinstance(value, dict):
        return {k: map_strings(v, func) for k, v in value.items()}
    return value
