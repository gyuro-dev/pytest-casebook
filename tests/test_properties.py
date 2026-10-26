"""
どんな値でも成り立つべき性質（Hypothesis で値を自動生成して確かめる）。

固定の例では思いつかない値（改行・区切りの行に似た出力・NaN など）で壊れないことを見る。
"""

from __future__ import annotations

import dataclasses
import enum
import json
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from pytest_casebook.golden import INFO_KEYS, RESULT_KEYS, parse_golden, render
from pytest_casebook.model import Case
from pytest_casebook.serialize import serialize, to_jsonable

# CI の遅い runner で時間切れにならないよう、1 例あたりの制限は付けない
settings.register_profile("casebook", deadline=None)
settings.load_profile("casebook")


# =============================================================================
# to_jsonable: どんな値でも落ちず、結果は JSON にできる
# =============================================================================


class Color(enum.Enum):
    RED = 1


@dataclasses.dataclass
class Point:
    x: Any
    y: Any


class Model:
    """pydantic のように model_dump() を持つもの。"""

    def __init__(self, value: Any) -> None:
        self.value = value

    def model_dump(self) -> Any:
        return {"value": self.value}


SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(),  # NaN・Infinity も含む
    st.text(),
    st.decimals(),  # NaN・sNaN・Infinity も含む
    st.dates(),
    st.times(),
    st.datetimes(),
    st.binary(),
    st.sampled_from([Color.RED, PurePosixPath("a/b"), PureWindowsPath(r"c:\a\b")]),
)
VALUES = st.recursive(
    SCALARS,
    lambda inner: st.one_of(
        st.lists(inner),
        st.tuples(inner, inner),
        st.dictionaries(st.one_of(st.text(), st.integers(), st.none()), inner),
        # set の要素はハッシュできるもの（sNaN の Decimal はハッシュできない）
        st.sets(st.one_of(st.integers(), st.text(), st.decimals(allow_nan=False))),
        st.frozensets(st.integers()),
        st.builds(Point, inner, inner),
        st.builds(Model, inner),
    ),
    max_leaves=20,
)


@given(VALUES)
def test_to_jsonable_never_raises_and_is_json(value: Any) -> None:
    result = to_jsonable(value)
    json.dumps(result, ensure_ascii=False)
    # 整形した文字列にもできる（期待出力に書く形）
    assert serialize(value)


@given(VALUES)
def test_to_jsonable_is_stable(value: Any) -> None:
    """同じ値からは同じ結果になる（set の並びが実行ごとに変わらない）。"""
    assert serialize(value) == serialize(value)


# =============================================================================
# 期待出力: render() した文字列を parse_golden() で読むと、比べる部分が元に戻る
# =============================================================================

SECTION_TITLES = ["stdout", "stderr", "return", "raises", "json", "body", "observe: db.users"]
_SECTION_LINE = re.compile(r"^----- (stdout|stderr|return|raises|json|body|observe: .+) -----$")
# 本文の文字。\r は正規化で消えている前提（比べる側も \r\n を \n にそろえる）
BODY_TEXT = st.text(alphabet=st.characters(exclude_characters="\r")).filter(
    # 出力の途中に見出しとまったく同じ行があると、書かれた見出しと区別できない（仕様）
    lambda s: not any(_SECTION_LINE.match(line) for line in s.split("\n"))
)
HEADER_VALUE = st.text()


@given(
    name=st.from_regex(r"\A\w[\w.\-]{0,10}\Z", alphabet=st.characters(categories=("L", "Nd"))),
    info=st.lists(st.tuples(st.sampled_from(sorted(INFO_KEYS - {"case"})), HEADER_VALUE)),
    result=st.one_of(st.none(), st.tuples(st.sampled_from(sorted(RESULT_KEYS)), st.integers())),
    sections=st.dictionaries(st.sampled_from(SECTION_TITLES), BODY_TEXT, min_size=1),
    default_section=st.sampled_from(["stdout", "return", "json"]),
)
def test_golden_round_trip(
    name: str,
    info: list[tuple[str, str]],
    result: tuple[str, int] | None,
    sections: dict[str, str],
    default_section: str,
) -> None:
    header = [*info, *([(result[0], str(result[1]))] if result else [])]
    text = render(Case(name=name), header, list(sections.items()))
    assert text.endswith("\n")
    content = parse_golden(text, default_section)
    # 比べるヘッダー（exit_code / status）は値ごと戻り、説明のヘッダーは比べる部分に入らない
    assert content.results == ({result[0]: str(result[1])} if result else {})
    # 本文は、末尾の空白を除いて元に戻る（ファイルの末尾は改行 1 つにそろえる）。
    # 既定の見出しの空の本文は「書いていない」のと同じなので、戻らなくてよい
    for title, body in sections.items():
        assert content.sections.get(title, "").rstrip() == body.rstrip(), title
    assert set(content.sections) <= set(sections)


@given(info=st.lists(st.tuples(st.sampled_from(sorted(INFO_KEYS)), HEADER_VALUE)))
def test_golden_headers_stay_one_line_each(info: list[tuple[str, str]]) -> None:
    """ヘッダーの値に改行があっても、ヘッダーは 1 行ずつで、本文はその下から始まる。"""
    text = render(Case(name="a"), [*info, ("exit_code", "0")], [("stdout", "out")])
    lines = text.split("\n")
    assert lines[: len(info) + 2] == [
        line for line in lines[: len(info) + 2] if line.startswith("# ")
    ]
    assert lines[len(info) + 1] == "# exit_code: 0"
    assert lines[len(info) + 2] == "----- stdout -----"
