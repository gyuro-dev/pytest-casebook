"""
ディレクトリごとの conftest.py・YAML の隣のモジュール・{casebook_dir}・サンプルの確認。
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_hooks_apply_only_to_their_directory(pytester: pytest.Pytester) -> None:
    """a/ の conftest.py の hook は、b/ のケースには効かない。"""
    for name, answer in (("a", "A の答え"), ("b", None)):
        d = pytester.mkdir(name)
        (d / f"casebook_{name}.yaml").write_text(
            "command_prefix: [prog]\ncases:\n  - name: run\n    command: x\n"
            "    expect: {stdout: " + (answer or "B の答え") + "}\n",
            encoding="utf-8",
        )
        if answer:
            (d / "conftest.py").write_text(
                textwrap.dedent(
                    f"""
                    from pytest_casebook import CommandResult

                    def pytest_casebook_run_command(argv):
                        return CommandResult(0, "{answer}\\n", "")
                    """
                ),
                encoding="utf-8",
            )
    # b/ にも hook を置く（a/ の hook が b/ に効くと、firstresult で a/ の答えが返ってしまう）
    (pytester.path / "b" / "conftest.py").write_text(
        "from pytest_casebook import CommandResult\n\n"
        "def pytest_casebook_run_command(argv):\n"
        "    return CommandResult(0, 'B の答え\\n', '')\n",
        encoding="utf-8",
    )
    # ケース2件と、ファイルごとの期待出力の後始末の確認2件
    pytester.runpytest().assert_outcomes(passed=4)


def test_call_imports_module_next_to_yaml(pytester: pytest.Pytester) -> None:
    """conftest.py がなくても、YAML と同じディレクトリのモジュールを call: で呼べる。"""
    d = pytester.mkdir("sub")
    (d / "nearby.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    (d / "casebook_x.yaml").write_text(
        "cases:\n  - name: a\n    call: nearby:answer\n    expect: {return: 42}\n",
        encoding="utf-8",
    )
    pytester.runpytest().assert_outcomes(passed=2)


def test_casebook_dir_token(pytester: pytest.Pytester) -> None:
    """{casebook_dir} は YAML のディレクトリになり、出力の中では {casebook_dir} に戻る。"""
    d = pytester.mkdir("sub")
    (d / "show.py").write_text(
        "import pathlib, sys\nprint(pathlib.Path(sys.argv[0]).resolve().parent.as_posix())\n",
        encoding="utf-8",
    )
    py = Path(sys.executable).as_posix()
    (d / "casebook_x.yaml").write_text(
        f"command_prefix: [{py}, '{{casebook_dir}}/show.py']\n"
        "cases:\n  - name: where\n    command: ''\n    setup: {files: {in.txt: x}}\n"
        "    expect: {stdout: '{casebook_dir}'}\n",
        encoding="utf-8",
    )
    pytester.runpytest().assert_outcomes(passed=2)


def test_empty_command_needs_prefix(pytester: pytest.Pytester) -> None:
    pytester.makefile(".yaml", casebook_x="cases:\n  - name: a\n    command: ''\n")
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*command is empty (and there is no command_prefix)*"])


def test_update_keeps_handwritten_golden(pytester: pytest.Pytester) -> None:
    """結果が同じなら --casebook-update は期待出力を書き直さない。"""
    pytester.makepyfile(m="def f():\n    return 1\n")
    pytester.makeini("[pytest]\npythonpath = .\n")
    pytester.makefile(".yaml", casebook_m="cases:\n  - name: f\n    call: m:f\n")
    golden = pytester.path / "golden" / "casebook_m" / "f.txt"
    golden.parent.mkdir(parents=True)
    golden.write_text("1\n", encoding="utf-8")
    pytester.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden.read_text(encoding="utf-8") == "1\n"
    # 結果が変われば書き直す
    golden.write_text("2\n", encoding="utf-8")
    pytester.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden.read_text(encoding="utf-8").endswith("----- return -----\n1\n")


# 日本語のサンプルと英語のサンプル。17_targets がどちらも --target を足すので、
# 同じセッションでは流さず、ディレクトリごとに別のプロセスで確かめる
EXAMPLE_DIRS = ["examples", "examples-en"]


@pytest.mark.parametrize("examples", EXAMPLE_DIRS)
def test_examples_pass(examples: str) -> None:
    """サンプルがすべて通る（サンプルが README の説明どおりに動くことの確認）。"""
    if not (ROOT / examples).is_dir():
        pytest.skip(f"{examples} がない")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", examples, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:]


def _code_blocks(text: str, lang: str) -> list[str]:
    """Markdown の ```lang のコードブロックの中身を、出てくる順に返す。"""
    return re.findall(rf"^```{lang}\n(.*?)^```$", text, flags=re.MULTILINE | re.DOTALL)


@pytest.mark.parametrize(
    ("readme", "heading"),
    [("README.md", "## Getting started"), ("README.ja.md", "## はじめかた")],
)
def test_readme_getting_started_runs(pytester: pytest.Pytester, readme: str, heading: str) -> None:
    """
    README の「はじめかた」を書いてあるとおりに写すと動く（README の最初の例が実際に動くこと）。

    hello.py と YAML を README のコードブロックから写し、--casebook-update で作られた
    期待出力が README に載せたものと同じになることを確かめる。
    """
    text = (ROOT / readme).read_text(encoding="utf-8")
    section = text[text.index(heading) :]
    section = section[: section.index("\n## ", 1)]
    script = _code_blocks(section, "python")[0]
    yaml_text = _code_blocks(section, "yaml")[0]
    golden = next(b for b in _code_blocks(section, "text") if b.startswith("# case: greet"))
    tests = pytester.mkdir("tests")
    (tests / "hello.py").write_text(script, encoding="utf-8")
    (tests / "casebook_hello.yaml").write_text(yaml_text, encoding="utf-8")

    pytester.runpytest("--casebook-update").assert_outcomes(passed=3)
    written = tests / "golden" / "casebook_hello" / "greet.txt"
    assert written.read_text(encoding="utf-8") == golden
    pytester.runpytest().assert_outcomes(passed=3)


def test_setup_hook_runs_for_every_case(pytester: pytest.Pytester) -> None:
    """setup: のないケースでも pytest_casebook_setup を呼び、後片付けが毎回行われる。"""
    pytester.makepyfile(
        store="ITEMS = []\n\ndef add(x):\n    ITEMS.append(x)\n    return len(ITEMS)\n"
    )
    pytester.makeini("[pytest]\npythonpath = .\n")
    pytester.makeconftest(
        """
        import contextlib
        import store

        @contextlib.contextmanager
        def _clean():
            try:
                yield
            finally:
                store.ITEMS.clear()

        def pytest_casebook_setup(data):
            assert data == {}
            return _clean()
        """
    )
    pytester.makefile(
        ".yaml",
        casebook_s="cases:\n"
        "  - {name: first, call: 'store:add', args: [a], expect: {return: 1}}\n"
        "  - {name: second, call: 'store:add', args: [b], expect: {return: 1}}\n",
    )
    pytester.runpytest().assert_outcomes(passed=3)


def _run_examples(examples: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"{examples}/17_targets",
            "-q",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


@pytest.mark.parametrize("examples", EXAMPLE_DIRS)
def test_examples_targets(examples: str) -> None:
    """17_targets: 環境ごとに期待出力を分け、local でしか流さないケースを除ける。"""
    if not (ROOT / examples).is_dir():
        pytest.skip(f"{examples} がない")
    staging = ("--target", "staging", "-o", "casebook_golden_dir=golden_staging")
    ok = _run_examples(examples, *staging, "-m", "not local_only")
    assert ok.returncode == 0, ok.stdout[-2000:]
    assert "1 deselected" in ok.stdout
    # staging を local の期待出力と比べると、値が違うので失敗する（置き場所が本当に分かれている）
    mixed = _run_examples(examples, "--target", "staging", "-m", "not local_only")
    assert mixed.returncode == 1
    assert "list_items" in mixed.stdout


@pytest.mark.parametrize("examples", EXAMPLE_DIRS)
def test_examples_reports(examples: str, tmp_path: Path) -> None:
    """21_reports: lang: のある 2 本の YAML を、言語ごとの表に分けて書ける。"""
    if not (ROOT / examples).is_dir():
        pytest.skip(f"{examples} がない")
    out = tmp_path.as_posix()
    reports = (
        f"{out}/ja.html = {examples}/21_reports/*_ja.yaml\n"
        f"{out}/en.html = {examples}/21_reports/*_en.yaml"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"{examples}/21_reports",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            f"casebook_html_reports={reports}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    ja = (tmp_path / "ja.html").read_text(encoding="utf-8")
    en = (tmp_path / "en.html").read_text(encoding="utf-8")
    assert '<html lang="ja">' in ja
    assert "casebook_hello_ja.yaml" in ja
    assert "casebook_hello_en.yaml" not in ja
    assert '<html lang="en">' in en
    assert "<th>Preconditions</th>" in en
    assert "casebook_hello_en.yaml" in en
