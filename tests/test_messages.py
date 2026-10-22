"""日本語と英語の文言（messages.py）と、英語で出る比較の失敗のメッセージを確かめる。"""

from __future__ import annotations

import re
import string
from typing import Any

import pytest
from helpers import CALC_MODULE, golden, write_casebook

from pytest_casebook.messages import LANGS, MESSAGES, TEXTS

JAPANESE = re.compile("[぀-ヿ一-鿿]")


def _shape(value: Any) -> Any:
    """文言の「形」（キー・要素の数・{...} の名前）。言語によらず同じになるはず。"""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return len(value)
    return sorted({name for _, name, _, _ in string.Formatter().parse(value) if name})


@pytest.mark.parametrize("table", [TEXTS, MESSAGES], ids=["TEXTS", "MESSAGES"])
def test_languages_have_same_keys_and_placeholders(table: dict[str, Any]) -> None:
    assert tuple(table) == LANGS
    shapes = {lang: _shape(texts) for lang, texts in table.items()}
    assert shapes["en"] == shapes["ja"]


@pytest.mark.parametrize("table", [TEXTS, MESSAGES], ids=["TEXTS", "MESSAGES"])
def test_english_has_no_japanese(table: dict[str, Any]) -> None:
    assert not JAPANESE.search(repr(table["en"]))


def test_missing_files_in_english(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: no_output
            call: "calc:add"
            args: [1, 2]
            observe: [files]
            expect: {files: {out.txt: done}}
        """,
    )
    result = project.runpytest("-o", "casebook_lang=en")
    result.stdout.fnmatch_lines(
        [
            "*  - files.out.txt: missing in the actual value",
            "*----- actual files -----",
            "*(no files)",
        ]
    )
    assert not JAPANESE.search(result.stdout.str())


def test_golden_orphans_in_english(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    project.runpytest("--casebook-update")
    (project.path / "golden" / "casebook_calc" / "removed.txt").write_text("3\n", encoding="utf-8")

    result = project.runpytest("-o", "casebook_lang=en")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(
        ["*golden files not used by casebook_calc.yaml are left in *: [[]'removed.txt'[]]"]
    )


def test_english_is_the_default(pytester: pytest.Pytester) -> None:
    """casebook_lang を書かなければ、レポートと比較の失敗のメッセージは英語になる。"""
    pytester.makepyfile(calc=CALC_MODULE)
    pytester.makeini("[pytest]\npythonpath = .\n")
    write_casebook(
        pytester,
        """
        cases:
          - group: Arithmetic
            cases:
              - {name: wrong, call: "calc:add", args: [1, 2], expect: {return: 4}}
        """,
    )
    report = pytester.path / "report.html"
    result = pytester.runpytest(f"--casebook-html={report}")
    result.assert_outcomes(failed=1, passed=1)  # passed は golden_orphans
    result.stdout.fnmatch_lines(
        ["*Differs from the expected result:", "*return: expected 4 / actual 3"]
    )
    page = report.read_text(encoding="utf-8")
    assert '<html lang="en">' in page
    assert "<title>Test Specification</title>" in page
    assert "<th class='level'>Category</th>" in page


@pytest.mark.parametrize("lang", LANGS)
def test_golden_no_files_does_not_depend_on_language(project: pytest.Pytester, lang: str) -> None:
    """期待出力ファイルの「ファイルなし」の表記は、言語を変えても変わらない。"""
    write_casebook(
        project,
        "cases:\n  - {name: empty, call: calc:add, args: [1, 2], observe: [files]}\n",
    )
    project.runpytest("--casebook-update", "-o", f"casebook_lang={lang}")
    assert "----- observe: files -----\n(no files)\n" in golden(project, "empty")
