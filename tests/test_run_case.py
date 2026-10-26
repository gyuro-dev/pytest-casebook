"""公開 API run_case()（ケースを1件実行して、期待出力の形式の文字列を返す）の確認。"""

from __future__ import annotations

import contextlib
import textwrap
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


# =============================================================================
# files: {}（空でも作業ディレクトリを作る）
# =============================================================================


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# out/ を作ってカレントディレクトリを出す（同じディレクトリで2回動くと mkdir が失敗する）
MKDIR_OUT = f'["{PY}", "-c", "import os; os.mkdir(\'out\'); print(os.getcwd())"]'


def test_empty_setup_files_gives_a_fresh_workdir(tmp_path: Path) -> None:
    """
    files: {} を書くと、空でもケースごとに新しい作業ディレクトリで動く。

    files: を書かないケースは、これまでどおり YAML のディレクトリで動く。
    """
    path = _write(
        tmp_path / "casebook_fresh.yaml",
        f"""
        states:
          default: {{}}
          clean: {{files: {{}}}}
        cases:
          - name: first
            setup: {{files: {{}}}}
            command: {MKDIR_OUT}
          - name: second
            setup: {{files: {{}}}}
            command: {MKDIR_OUT}
          - name: by_state
            state: clean
            command: {MKDIR_OUT}
          - name: here
            command: ["{PY}", "-c", "import os; print(os.getcwd())"]
        """,
    )
    doc = pytest_casebook.load(path)
    assert [c.needs_workdir for c in doc.cases] == [True, True, True, False]
    assert [c.setup_files for c in doc.cases] == [{}, {}, {}, {}]
    for case in doc.cases[:3]:
        text = run_case(doc, case)
        # 2件目以降も、前のケースの out/ が残っていない新しいディレクトリで動く
        assert "# exit_code: 0\n" in text
        assert "----- stdout -----\n<tmp>\n" in text
    assert "----- stdout -----\n{casebook_dir}\n" in run_case(doc, doc.cases[3])
    assert not (tmp_path / "out").exists()


# =============================================================================
# load(ini=True)（pytest の設定ファイルの casebook_* を読む）
# =============================================================================

INI_CASEBOOK = f"""
cases:
  - name: hello
    description: あいさつを出す
    command: ["{PY}", "-c", "print('hi')"]
  - name: missing
    command: no-such-program-123
"""


def test_load_ini_reads_pyproject(tmp_path: Path) -> None:
    """pyproject.toml の [tool.pytest.ini_options] の casebook_* が load と run_case に効く。"""
    _write(
        tmp_path / "pyproject.toml",
        """
        [tool.pytest.ini_options]
        casebook_lang = "ja"
        casebook_golden_description = true
        casebook_levels = ["機能", "項目"]
        casebook_golden_dir = "expected"
        casebook_command_prefix = "tool --verbose"
        casebook_builtin_patterns = "false"
        casebook_encoding = "cp932"
        """,
    )
    path = _write(tmp_path / "casebook_x.yaml", INI_CASEBOOK)
    doc = pytest_casebook.load(path, ini=True)
    assert doc.levels == ("機能", "項目")
    assert doc.golden_path(doc.cases[0]) == tmp_path / "expected" / "casebook_x" / "hello.txt"
    assert doc.command_prefix == ("tool", "--verbose")
    assert doc.options == {
        "lang": "ja",
        "encoding": "cp932",
        "builtin_patterns": False,
        "description": True,
    }

    # run_case() の既定が ini の値になる（description の行が出て、誤りは日本語）
    plain = pytest_casebook.load(path, ini=True, command_prefix=())
    assert "# description: あいさつを出す\n" in run_case(plain, plain.cases[0])
    with pytest.raises(CasebookRunError, match="コマンドが見つかりません"):
        run_case(plain, plain.cases[1])
    # 引数で渡したものが ini の値より優先する
    assert "# description:" not in run_case(plain, plain.cases[0], description=False)
    with pytest.raises(CasebookRunError, match="command not found"):
        run_case(plain, plain.cases[1], lang="en")

    # 書き方の誤りも ini の casebook_lang の言語になる
    wrong = _write(tmp_path / "casebook_wrong.yaml", "cases:\n  - name: a\n")
    with pytest.raises(
        pytest_casebook.CasebookError, match="command・call・request・manual のどれか1つ"
    ):
        pytest_casebook.load(wrong, ini=True)


def test_load_ini_explicit_arguments_win(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        """
        [tool.pytest.ini_options]
        casebook_lang = "ja"
        casebook_levels = ["機能"]
        casebook_golden_dir = "expected"
        casebook_command_prefix = "tool"
        """,
    )
    path = _write(tmp_path / "casebook_x.yaml", INI_CASEBOOK)
    doc = pytest_casebook.load(
        path, ini=True, lang="en", levels=("A",), golden_dir=tmp_path / "g", command_prefix=()
    )
    assert doc.levels == ("A",)
    assert doc.golden_dir == tmp_path / "g"
    assert doc.command_prefix == ()
    assert doc.options["lang"] == "en"
    # levels を渡さなければ、lang ではなく ini の casebook_levels を使う
    assert pytest_casebook.load(path, ini=True, lang="en").levels == ("機能",)


def test_load_without_ini_ignores_the_config(tmp_path: Path) -> None:
    """ini=False（既定）では、設定ファイルがあってもこれまでどおり読まない。"""
    _write(
        tmp_path / "pyproject.toml",
        """
        [tool.pytest.ini_options]
        casebook_lang = "ja"
        casebook_golden_description = true
        casebook_golden_dir = "expected"
        """,
    )
    path = _write(tmp_path / "casebook_x.yaml", INI_CASEBOOK)
    doc = pytest_casebook.load(path)
    assert doc.options == {}
    assert doc.levels == ("Category", "Subcategory", "Item")
    assert doc.golden_dir == tmp_path / "golden" / "casebook_x"
    assert "# description:" not in run_case(doc, doc.cases[0])
    with pytest.raises(CasebookRunError, match="command not found"):
        run_case(doc, doc.cases[1])


def test_pytest_ini_wins_over_pyproject(tmp_path: Path) -> None:
    """同じディレクトリでは pytest.ini を使う（casebook_* がなくても、節がなくても）。"""
    _write(tmp_path / "pyproject.toml", '[tool.pytest.ini_options]\ncasebook_lang = "ja"\n')
    _write(tmp_path / "tox.ini", "[pytest]\ncasebook_lang = ja\n")
    path = _write(tmp_path / "casebook_x.yaml", INI_CASEBOOK)
    ini = _write(tmp_path / "pytest.ini", "[pytest]\naddopts = -q\n")
    assert pytest_casebook.load(path, ini=True).options["lang"] == "en"
    ini.write_text("# 節のない pytest.ini\n", encoding="utf-8")
    assert pytest_casebook.load(path, ini=True).options["lang"] == "en"
    # pytest.ini がなければ pyproject.toml
    ini.unlink()
    assert pytest_casebook.load(path, ini=True).options["lang"] == "ja"


def test_parent_config_is_found_from_a_nested_yaml(tmp_path: Path) -> None:
    """上のディレクトリの設定ファイルを使い、casebook_golden_dir は YAML からの相対パスになる。"""
    _write(
        tmp_path / "pytest.ini",
        """
        [pytest]
        casebook_lang = ja
        casebook_golden_dir = expected
        casebook_levels =
            機能
            小項目
        casebook_golden_description = yes
        """,
    )
    path = _write(tmp_path / "tests" / "sub" / "casebook_x.yaml", INI_CASEBOOK)
    doc = pytest_casebook.load(path, ini=True)
    assert doc.levels == ("機能", "小項目")
    assert doc.golden_dir == tmp_path / "tests" / "sub" / "expected" / "casebook_x"
    assert doc.options["lang"] == "ja"
    assert doc.options["description"] is True


def test_pyproject_without_pytest_table_is_skipped(tmp_path: Path) -> None:
    """
    [tool.pytest.ini_options] のない pyproject.toml は飛ばし、上のディレクトリの設定を使う
    （tox.ini の [pytest]・setup.cfg の [tool:pytest] も、節がなければ飛ばす）。
    """
    _write(tmp_path / "setup.cfg", "[tool:pytest]\ncasebook_lang = ja\ncasebook_encoding = cp932\n")
    pkg = tmp_path / "pkg"
    _write(pkg / "pyproject.toml", '[project]\nname = "pkg"\n\n[tool.ruff]\nline-length = 99\n')
    _write(pkg / "tox.ini", "[tox]\nenv_list = py311\n")
    _write(pkg / "setup.cfg", "[metadata]\nname = pkg\n")
    path = _write(pkg / "casebook_x.yaml", INI_CASEBOOK)
    doc = pytest_casebook.load(path, ini=True)
    assert doc.options["lang"] == "ja"
    assert doc.options["encoding"] == "cp932"


def test_invalid_ini_bool_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path / "tox.ini", "[pytest]\ncasebook_golden_description = maybe\n")
    path = _write(tmp_path / "casebook_x.yaml", INI_CASEBOOK)
    with pytest.raises(ValueError, match="casebook_golden_description must be true or false"):
        pytest_casebook.load(path, ini=True)
