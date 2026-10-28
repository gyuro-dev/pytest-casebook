"""
JSON Schema と読み込み（parse_document）の判定が食い違わないことの確認。

YAML の書き方は Schema（エディタの検証）と model.py（読み込み）の 2 か所で定めているので、
各キーに「型の違う値・偽になる値」をぶつけ、両方が同じように受け入れる・弾くことを
機械的に確かめる。`or {}` のように偽の値を省略と取り違えるすり抜けは、これで見つかる。

意図して違う所（null を省略として読む、など）は KNOWN_DIFFERENCES に理由つきで書く。
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pytest_casebook
from pytest_casebook.model import parse_document

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = json.loads(pytest_casebook.SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)

# 型の違う値と、Python で偽になる値（省略と取り違えやすいもの）
BAD_VALUES: list[Any] = [
    None,
    "",
    "   ",
    "x",
    0,
    1.5,
    False,
    True,
    [],
    [""],
    ["x"],
    {},
    {"x": 1},
    {"x": "y"},
]

CALL = {"name": "a", "call": "m:f"}
COMMAND = {"name": "a", "command": "prog"}
REQUEST = {"name": "a", "request": {"path": "/x"}}
MANUAL = {"name": "a", "manual": "手で確かめる"}

Builder = Callable[[Any], dict[str, Any]]


def _top(key: str) -> Builder:
    return lambda v: {"cases": [CALL], key: v}


def _group(key: str) -> Builder:
    return lambda v: {"cases": [{"group": "g", "cases": [CALL], key: v}]}


def _case(base: dict[str, Any], key: str) -> Builder:
    return lambda v: {"cases": [{**base, key: v}]}


def _request(key: str) -> Builder:
    return lambda v: {"cases": [{"name": "a", "request": {"path": "/x", key: v}}]}


def _setup(key: str) -> Builder:
    return lambda v: {"cases": [{**CALL, "setup": {key: v}}]}


def _state(key: str) -> Builder:
    return lambda v: {"states": {"s": {key: v}}, "cases": [{**CALL, "state": "s"}]}


def _expect(base: dict[str, Any], key: str) -> Builder:
    return lambda v: {"cases": [{**base, "expect": {key: v}}]}


def _param(key: str) -> Builder:
    return lambda v: {"cases": [{**CALL, "params": [{"name": "p", key: v}]}]}


# (場所, キー) -> その値を入れた YAML 全体を作る関数
TARGETS: dict[tuple[str, str], Builder] = {
    **{("file", k): _top(k) for k in pytest_casebook.model._TOP_KEYS - {"cases"}},
    ("file", "cases"): lambda v: {"cases": v},
    **{("group", k): _group(k) for k in pytest_casebook.model._GROUP_KEYS - {"group", "cases"}},
    ("group", "group"): lambda v: {"cases": [{"group": v, "cases": [CALL]}]},
    ("group", "cases"): lambda v: {"cases": [{"group": "g", "cases": v}]},
    ("case", "name"): lambda v: {"cases": [{"name": v, "call": "m:f"}]},
    ("case", "params"): lambda v: {"cases": [{**CALL, "params": v}]},
    **{
        ("case", k): _case(CALL, k)
        for k in (
            "description",
            "call",
            "args",
            "kwargs",
            "timeout",
            "state",
            "marks",
            "golden",
            "setup",
            "observe",
            "expect",
            "meta",
            "skip",
            "xfail",
        )
    },
    **{("case", k): _case(COMMAND, k) for k in ("command", "stdin", "stdin_file", "env")},
    ("case", "request"): _case(REQUEST, "request"),
    ("case", "manual"): _case(MANUAL, "manual"),
    ("case", "result"): _case(MANUAL, "result"),
    ("manual case", "expect"): _case(MANUAL, "expect"),
    **{("request", k): _request(k) for k in ("method", "path", "query", "headers", "json", "body")},
    ("setup", "files"): _setup("files"),
    ("states", "files"): _state("files"),
    **{("expect", k): _expect(COMMAND, k) for k in ("exit_code", "stdout", "stderr")},
    ("expect", "return"): _expect(CALL, "return"),
    ("expect", "raises"): _expect(CALL, "raises"),
    **{("expect", k): _expect(REQUEST, k) for k in ("status", "json", "body", "headers")},
    ("expect", "observe target"): lambda v: {
        "cases": [{**CALL, "observe": ["db.users"], "expect": {"db.users": v}}]
    },
    # 一段深いところ
    ("normalize", "pattern"): lambda v: {"normalize": [{"pattern": v}], "cases": [CALL]},
    ("normalize", "replace"): lambda v: {
        "normalize": [{"pattern": "x", "replace": v}],
        "cases": [CALL],
    },
    ("normalize", "item"): lambda v: {"normalize": [v], "cases": [CALL]},
    ("request_defaults", "headers"): lambda v: {
        "request_defaults": {"headers": v},
        "cases": [REQUEST],
    },
    ("param", "name"): lambda v: {"cases": [{**CALL, "params": [{"name": v}]}]},
    **{("param", k): _param(k) for k in ("description", "args", "expect", "timeout", "skip")},
    ("param", "item"): lambda v: {"cases": [{**CALL, "params": [v]}]},
}


def _is_blank(value: Any) -> bool:
    return isinstance(value, str) and not value.strip()


def _is_null_for_optional(target: tuple[str, str], value: Any) -> bool:
    return value is None and target not in {
        # 書くなら空にできないキー（読み込みも Schema も null を弾く）
        ("group", "group"),
        ("case", "name"),
        ("case", "call"),
        ("case", "manual"),
        ("case", "request"),
        ("case", "params"),
        ("file", "cases"),
        ("group", "cases"),
    }


# 意図して違う所（どのキーでも）
NULL_REASON = (
    "省略できるキーの null（`title:` の下を空にした書き方）は、読み込みでは省略として読み、"
    "Schema は空のキーに印を付ける"
)
BLANK_REASON = (
    "空白だけの文字列は、読み込みでは空と同じに扱って弾くが、Schema は minLength では"
    "見分けられない（エディタでは空白だけの値は見れば分かる）"
)
# 意図して違う所（キーごと）。(場所, キー) -> (値がこの条件なら違ってよい, 理由)
KNOWN_DIFFERENCES: dict[tuple[str, str], tuple[Callable[[Any], bool], str]] = {
    ("case", "golden"): (
        lambda v: v == "x",
        "Schema は文字列なら通す。期待出力の置き場所の中を指すかは読み込みで確かめる",
    ),
    ("case", "command"): (
        lambda v: v == [],
        (
            "command: [] は command_prefix があるときだけ書ける。Schema は ini の "
            "casebook_command_prefix を知らないので、読み込みで確かめる"
        ),
    ),
    ("case", "state"): (
        lambda v: v == "x",
        "state: の名前が states: にあるかは読み込みで確かめる",
    ),
    ("case", "stdin_file"): (
        lambda v: v == "x",
        "stdin_file: のファイルがあるかは読み込みで確かめる（読んで case.stdin にする）",
    ),
    ("group", "state"): (
        lambda v: v == "x",
        "state: の名前が states: にあるかは読み込みで確かめる",
    ),
    ("expect", "observe target"): (
        lambda v: isinstance(v, dict) and bool(v),
        "observe の対象の期待値は、読み込みでは比べ方（$contains など）の書き方も確かめる",
    ),
    ("param", "expect"): (
        lambda v: isinstance(v, str | list),
        (
            "params の要素の expect: が文章でよいかは、テンプレートの操作（manual かどうか）で"
            "決まる。Schema は要素だけを見るので分からない"
        ),
    ),
}


def _schema_accepts(doc: Any) -> bool:
    return not any(VALIDATOR.iter_errors(doc))


def _loading_accepts(doc: Any) -> bool:
    try:
        parse_document(copy.deepcopy(doc), Path("casebook_x.yaml"), golden_dir=Path("g"), levels=())
    except pytest_casebook.CasebookError:
        return False
    return True


def _known_difference(target: tuple[str, str], value: Any) -> str | None:
    if _is_null_for_optional(target, value):
        return NULL_REASON
    if _is_blank(value):
        return BLANK_REASON
    if target in KNOWN_DIFFERENCES:
        matches, reason = KNOWN_DIFFERENCES[target]
        if matches(value):
            return reason
    return None


@pytest.mark.parametrize("value", BAD_VALUES, ids=repr)
@pytest.mark.parametrize("target", sorted(TARGETS), ids=lambda t: f"{t[0]}.{t[1]}")
def test_schema_and_loading_agree(target: tuple[str, str], value: Any) -> None:
    doc = TARGETS[target](value)
    schema_ok = _schema_accepts(doc)
    loading_ok = _loading_accepts(doc)
    if schema_ok == loading_ok:
        return
    reason = _known_difference(target, value)
    assert reason is not None, (
        f"{target[0]}.{target[1]} = {value!r}: schema {'accepts' if schema_ok else 'rejects'}, "
        f"loading {'accepts' if loading_ok else 'rejects'}"
    )
