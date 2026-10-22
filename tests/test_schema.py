"""
JSON Schema（casebook.schema.json）の確認。

サンプルの YAML がすべて通ること（スキーマが実際の書き方からずれていないこと）と、
よくある書き間違いを見つけられることを確かめる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import pytest_casebook

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads(pytest_casebook.SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def errors(doc: Any) -> list[str]:
    return [e.message for e in VALIDATOR.iter_errors(doc)]


def test_schema_itself_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    "path",
    [
        *sorted((ROOT / "examples").glob("*/casebook_*.yaml")),
        *sorted((ROOT / "examples-en").glob("*/casebook_*.yaml")),
        *sorted((ROOT / "integration").glob("casebook_*.yaml")),
        *sorted((ROOT / "docs" / "screenshots").glob("casebook_*.yaml")),
        *sorted((ROOT / "docs" / "screenshots-en").glob("casebook_*.yaml")),
    ],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_examples_follow_schema(path: Path) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert errors(doc) == []


@pytest.mark.parametrize(
    "doc",
    [
        {"cases": [{"name": "a", "call": "m:f", "arg": [1]}]},  # 打ち間違い
        {"cases": [{"name": "a", "command": "x", "call": "m:f"}]},  # 操作が2つ
        {"cases": [{"name": "a"}]},  # 操作がない
        {"cases": [{"name": "a b", "call": "m:f"}]},  # 名前に空白
        {"cases": [{"name": "a", "call": "f"}]},  # モジュールがない
        {"cases": [{"name": "a", "request": "users"}]},  # / で始まらない
        {"cases": [{"name": "a", "request": {"path": "/x", "json": {}, "body": "b"}}]},
        {"cases": [{"name": "a", "call": "m:f", "expect": {"return": 1, "raises": "E"}}]},
        {"cases": [{"name": "a", "call": "m:f", "expect": {"stdout": {"starts": "x"}}}]},
        {"cases": [{"group": "g", "cases": [], "colour": "red"}]},
        {"title": "no cases"},
    ],
)
def test_schema_rejects_mistakes(doc: Any) -> None:
    assert errors(doc)


def test_schema_path_is_packaged() -> None:
    assert pytest_casebook.SCHEMA_PATH.is_file()


@pytest.mark.parametrize(
    "path",
    [
        *sorted((ROOT / "examples").glob("*/casebook_*.yaml")),
        *sorted((ROOT / "examples-en").glob("*/casebook_*.yaml")),
    ],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_samples_point_to_the_published_schema(path: Path) -> None:
    """サンプルの1行目のスキーマの URL が、スキーマの $id（公開している URL）と同じ。"""
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first == f"# yaml-language-server: $schema={SCHEMA['$id']}"


def test_schema_descriptions_have_english() -> None:
    """エディタで出る説明は、英語のあとに日本語を書く（「English / 日本語」）。"""
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("title", "description") and isinstance(value, str):
                    texts.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(SCHEMA)
    assert texts
    for text in texts:
        english, _, japanese = text.partition(" / ")
        assert english.isascii(), text
        assert japanese, text


@pytest.mark.parametrize(
    "request_text",
    [
        "/users",
        "GET /users",
        "get /users?page=2",
        "Get /users",  # model.py は大文字小文字を区別しない
        "  POST   /users  ",
        "DELETE /",
        "GET /users extra",  # 3つに分かれる
        "FETCH /users",  # HTTP のメソッドではない
        "GET users",  # / で始まらない
        "GET",
        "",
    ],
)
def test_request_string_schema_matches_model(request_text: str, tmp_path: Path) -> None:
    """文字列で書く request: を、スキーマと model.py が同じように判定する。"""
    doc = {"cases": [{"name": "a", "request": request_text}]}
    path = tmp_path / "casebook_x.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    try:
        pytest_casebook.load(path)
        model_ok = True
    except pytest_casebook.CasebookError:
        model_ok = False
    assert (errors(doc) == []) == model_ok
