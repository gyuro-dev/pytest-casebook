"""公開 API run_case()（ケースを1件実行して、期待出力の形式の文字列を返す）の確認。"""

from __future__ import annotations

import contextlib
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from helpers import PY, golden, write_casebook

import pytest_casebook
from pytest_casebook import Case, CasebookRunError, run_case


def test_command_case_equals_the_updated_golden(project: pytest.Pytester) -> None:
    """command のケースの戻り値は、--casebook-update が書く期待出力と同じ文字列になる。"""
    path = write_casebook(
        project,
        f"""
        cases:
          - name: add
            command: ["{PY}", "-c", "print(1 + 2)"]
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)

    doc = pytest_casebook.load(path)
    text = run_case(doc, doc.cases[0])
    lines = text.splitlines()
    assert lines[0] == "# case: add"
    assert lines[1].startswith("# command: ")
    assert lines[2] == "# exit_code: 0"
    assert lines[3] == "----- stdout -----"
    assert lines[4] == "3"
    # 正規化まで同じなので、pytest が書いた期待出力とそのまま一致する
    assert text == golden(project, "add")


def test_hooks_object_with_partial_signatures(project: pytest.Pytester) -> None:
    """
    hooks には pytest_casebook_* の関数を属性に持つだけのオブジェクトを渡せる。

    conftest.py と同じく、各関数には宣言した引数だけが渡る。setup が返した
    コンテキストマネージャは後片付けに使われ、placeholders の置き換えは出力に当たる。
    """
    path = write_casebook(
        project,
        """
        cases:
          - name: point
            call: calc:point
            args: [7, 9]
        """,
    )
    doc = pytest_casebook.load(path)
    seen: list[str] = []

    @contextlib.contextmanager
    def prepared(case: Case) -> Iterator[None]:
        seen.append(f"setup:{case.name}")
        yield
        seen.append("cleanup")

    def placeholders() -> list[tuple[str, str]]:  # 引数を1つも宣言しない
        return [("point を作ります", "<creating>")]

    hooks = types.SimpleNamespace(
        pytest_casebook_setup=lambda case, data: prepared(case),  # case と data だけを宣言する
        pytest_casebook_placeholders=placeholders,
    )
    text = run_case(doc, doc.cases[0], hooks=hooks)
    assert seen == ["setup:point", "cleanup"]  # 後片付けまで行われた
    assert "----- return -----" in text
    assert "----- stdout -----\n<creating>\n" in text  # placeholders の置き換えが効いている


def test_manual_case_raises(tmp_path: Path) -> None:
    path = tmp_path / "casebook_manual.yaml"
    path.write_text(
        "cases:\n  - name: layout\n    manual: 印刷プレビューを目で確かめる\n"
        "    expect: 罫線が出る\n",
        encoding="utf-8",
    )
    doc = pytest_casebook.load(path)
    with pytest.raises(CasebookRunError) as e:
        run_case(doc, doc.cases[0])
    assert str(e.value) == "a manual case cannot be run: layout"


def test_lang_ja_makes_run_errors_japanese(tmp_path: Path) -> None:
    path = tmp_path / "casebook_missing.yaml"
    path.write_text("cases:\n  - name: missing\n    command: no-such-program-123\n", "utf-8")
    doc = pytest_casebook.load(path)
    with pytest.raises(CasebookRunError, match="コマンドが見つかりません: no-such-program-123"):
        run_case(doc, doc.cases[0], lang="ja")
    # lang は load() と同じように確かめる
    with pytest.raises(ValueError, match="lang must be one of"):
        run_case(doc, doc.cases[0], lang="fr")


def test_workdir_case_replaces_the_path_with_tmp(project: pytest.Pytester) -> None:
    """setup.files と observe の files が使え、作業ディレクトリのパスは <tmp> になる。"""
    path = write_casebook(
        project,
        f"""
        cases:
          - name: copy
            setup:
              files: {{in.txt: hello}}
            command:
              - "{PY}"
              - -c
              - "import os, shutil; shutil.copy('in.txt', 'out.txt'); print(os.getcwd())"
            observe: [files]
        """,
    )
    doc = pytest_casebook.load(path)
    text = run_case(doc, doc.cases[0])
    assert "----- stdout -----\n<tmp>\n" in text
    assert "=== in.txt ===\nhello" in text
    assert "=== out.txt ===\nhello" in text
