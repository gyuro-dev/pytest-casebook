"""
公開する関数・クラス・hook の docstring が、英語のあとに日本語で書かれていることの確認。

公開 API（`pytest_casebook.__all__`、HTTP のアダプター、hook の仕様）は英日の両方で
説明する決まりなので、公開するものを増やしたときに片方の言語が抜けないようにする。
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from typing import Any

import pytest

import pytest_casebook
from pytest_casebook import hookspecs, http, plugin


def _public_objects() -> Iterator[tuple[str, Any]]:
    yield "pytest_casebook", pytest_casebook
    yield "pytest_casebook.http", http
    yield "pytest_casebook.hookspecs", hookspecs
    for name in pytest_casebook.__all__:
        obj = getattr(pytest_casebook, name)
        if not (inspect.isclass(obj) or inspect.isfunction(obj)):
            continue
        yield name, obj
        if inspect.isclass(obj):
            # クラスに直接定義した公開のメソッドとプロパティ（継承したものは見ない）
            for attr, member in vars(obj).items():
                if not attr.startswith("_") and (
                    isinstance(member, property) or inspect.isfunction(member)
                ):
                    yield f"{name}.{attr}", member
    for name, obj in vars(hookspecs).items():
        if name.startswith("pytest_casebook_"):
            yield name, obj
    yield "send_with_httpx_client", http.send_with_httpx_client
    yield "send_with_werkzeug_client", http.send_with_werkzeug_client
    # conftest.py で上書きする公開の fixture
    yield "casebook_env", plugin.casebook_env


PUBLIC = dict(_public_objects())


@pytest.mark.parametrize("name", sorted(PUBLIC))
def test_public_docstring_is_english_then_japanese(name: str) -> None:
    doc = inspect.getdoc(PUBLIC[name])
    assert doc, f"{name} has no docstring"
    paragraphs = [p for p in doc.split("\n\n") if p.strip()]
    # 最初の段落が英語（ASCII）で、日本語の段落がある（:param などの説明より前）
    assert paragraphs[0].isascii(), f"{name}: the first paragraph must be English"
    body = [p for p in paragraphs if not p.lstrip().startswith(":")]
    assert any(not p.isascii() for p in body), f"{name}: no Japanese paragraph"


def test_public_objects_are_covered() -> None:
    """確かめる対象に、公開 API の主なものが入っている（集め方が壊れたら気づく）。"""
    assert {
        "load",
        "run_case",
        "Case.kind",
        "HttpResponse.parse_json",
        "pytest_casebook_request",
    } <= set(PUBLIC)
