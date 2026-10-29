"""
pytester で一時ディレクトリにケースファイルを作り、プラグインの動きを確認する。
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest
from helpers import PY, golden, write_casebook

from pytest_casebook.messages import LANGS, TEXTS

# =============================================================================
# 期待出力の作成と比較
# =============================================================================


def test_missing_golden_fails_then_update_creates_it(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix: [{PY}, -c]
        cases:
          - name: hello
            description: あいさつを出す
            command: "'print(\\"こんにちは\\")'"
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*期待出力 golden/casebook_calc/hello.txt がありません*"])

    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    text = golden(project, "hello")
    # description は書かない（説明の文を直しても期待出力に差分が出ないように）
    assert text.startswith("# case: hello\n# command: ")
    assert text.endswith("# exit_code: 0\n----- stdout -----\nこんにちは\n")

    project.runpytest().assert_outcomes(passed=2)


def test_changed_output_shows_diff(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: add
            call: calc:add
            args: [1, 2]
        """,
    )
    project.runpytest("--casebook-update")
    path = project.path / "golden" / "casebook_calc" / "add.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("3", "4"), encoding="utf-8")

    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*出力が期待と異なります*", "*-4*", "*+3*"])


def test_crlf_golden_still_matches(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    project.runpytest("--casebook-update")
    path = project.path / "golden" / "casebook_calc" / "add.txt"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    project.runpytest().assert_outcomes(passed=2)


def test_orphan_golden_is_reported(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    project.runpytest("--casebook-update")
    (project.path / "golden" / "casebook_calc" / "old.txt").write_text("x", encoding="utf-8")

    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*使われていない期待出力ファイルが*['old.txt']*"])


def test_orphan_check_follows_golden_extensions(project: pytest.Pytester) -> None:
    """golden: で使った拡張子（.json）の消し忘れも見つけ、関係のないファイルは見ない。"""
    write_casebook(
        project,
        "cases:\n"
        "  - {name: add, call: calc:add, args: [1, 2], golden: add.json}\n"
        "  - {name: sub, call: calc:add, args: [1, -1]}\n",
    )
    project.runpytest("--casebook-update")
    golden_dir = project.path / "golden" / "casebook_calc"
    assert (golden_dir / "add.json").exists()
    (golden_dir / "old.json").write_text("{}", encoding="utf-8")
    (golden_dir / "NOTES.md").write_text("期待出力のメモ", encoding="utf-8")
    (golden_dir / ".gitkeep").write_text("", encoding="utf-8")

    result = project.runpytest()
    result.assert_outcomes(passed=2, failed=1)
    result.stdout.fnmatch_lines(["*使われていない期待出力ファイルが*[[]'old.json'[]]*"])


# =============================================================================
# CLI のケース
# =============================================================================


def test_command_records_exit_code_and_stderr(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix:
          - {PY}
          - -c
          - "import calc, sys; sys.exit(calc.main([a for a in sys.argv[1:] if a != '-']))"
        cases:
          - name: sum
            command: 1 2 3
          - name: no_args
            command: "-"
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    assert golden(project, "sum").endswith("# exit_code: 0\n----- stdout -----\n6\n")
    assert golden(project, "no_args").endswith(
        "# exit_code: 2\n----- stdout -----\n\n----- stderr -----\n引数がありません\n"
    )


def test_command_stdin(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix: [{PY}, -c, "import sys; print(sys.stdin.read().upper())"]
        cases:
          - name: upper
            command: "-"
            stdin: abc
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden(project, "upper").endswith("----- stdout -----\nABC\n")


def test_command_stdin_file(project: pytest.Pytester) -> None:
    """YAML の隣に置いたファイルを標準入力に渡す（長い入力を YAML に書かずに済む）。"""
    project.makefile(".txt", stdin_data="hello,世界")
    write_casebook(
        project,
        f"""
        command_prefix: [{PY}, -c, "import sys; print(sys.stdin.read().strip().upper())"]
        cases:
          - name: from_file
            command: "-"
            stdin_file: stdin_data.txt
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden(project, "from_file").endswith("----- stdout -----\nHELLO,世界\n")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (
            "{name: a, command: x, stdin: abc, stdin_file: in.txt}",
            "stdin と stdin_file は同時に書けません",
        ),
        (
            "{name: a, call: 'calc:add', stdin_file: in.txt}",
            "stdin_file は command のケースにだけ書けます",
        ),
        (
            "{name: a, command: x, stdin_file: ../in.txt}",
            "stdin_file は YAML のディレクトリの中を指す相対パスで書いてください",
        ),
    ],
)
def test_invalid_stdin_file(project: pytest.Pytester, case: str, message: str) -> None:
    write_casebook(project, f"cases:\n  - {case}\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*{message}*"])


def test_missing_stdin_file_fails_the_case(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix: [{PY}, -c, "import sys; print(sys.stdin.read())"]
        cases:
          - name: missing
            command: "-"
            stdin_file: no_such.txt
        """,
    )
    # 中身は読み込みのときに読む（hook も run_case() も case.stdin を読むだけでよい）ので、
    # ないファイルは書き方の誤りと同じく、集めるときに知らせる
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        ["*casebook_calc.yaml*missing*stdin_file が見つかりません: no_such.txt*"]
    )


def test_stdin_file_is_read_into_case_stdin(project: pytest.Pytester) -> None:
    """stdin_file: の中身は case.stdin に入るので、hook は自分でファイルを読まなくてよい。"""
    project.makefile(".txt", stdin_data="from file")
    project.makeconftest(
        """
        from pytest_casebook import CommandResult

        def pytest_casebook_run_command(case):
            return CommandResult(0, f"stdin={case.stdin!r}", "")
        """
    )
    write_casebook(
        project,
        """
        cases:
          - {name: a, command: x, stdin_file: stdin_data.txt, expect: {stdout: "stdin='from file'"}}
        """,
    )
    project.runpytest().assert_outcomes(passed=2)  # 2 つ目は unused_golden_files


def test_command_env(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        env: {{CASEBOOK_X: file, CASEBOOK_Y: file}}
        command_prefix:
          - {PY}
          - -c
          - "import os; print(os.environ['CASEBOOK_X'], os.environ.get('CASEBOOK_Y'))"
        cases:
          - group: g
            env: {{CASEBOOK_X: group}}
            cases:
              - name: from_group
                command: ""
                expect: {{stdout: {{contains: group file}}}}
              - name: from_case
                command: ""
                env: {{CASEBOOK_Y: null, CASEBOOK_X: case}}
                expect: {{stdout: {{contains: case None}}}}
          - name: from_file
            command: ""
        """,
    )
    report = project.path / "report.html"
    project.runpytest("--casebook-update", f"--casebook-html={report}").assert_outcomes(passed=4)
    # 期待出力の見出しには env を書かない（環境変数を足しても期待出力が変わらないように）
    assert golden(project, "from_file").endswith("----- stdout -----\nfile file\n")
    assert not any(line.startswith("# env") for line in golden(project, "from_file").splitlines())
    # レポートの前提条件には、ファイル全体の env と違う変数だけを出す
    page = report.read_text(encoding="utf-8")
    assert "<div class='line'>環境変数: CASEBOOK_X=group</div>" in page
    assert "<div class='line'>環境変数: CASEBOOK_X=case</div>" in page
    assert "CASEBOOK_X=file" not in page


def test_missing_command_fails_with_message(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: x\n    command: no-such-command-xyz\n")
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=1, failed=1)
    # 理由だけで止めず、どこで実行したかと直し方も添える
    line = (
        f"*コマンドが見つかりません: no-such-command-xyz（{project.path} で実行しました。"
        "*command_prefix: [[]python, my_cli.py] など*"
    )
    result.stdout.fnmatch_lines([line])


def test_run_command_hook_runs_in_process(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import calc
        from pytest_casebook import run_in_process

        def pytest_casebook_run_command(argv):
            assert argv[0] == "calc"
            return run_in_process(calc.main, argv[1:])
        """
    )
    write_casebook(
        project,
        """
        command_prefix: calc
        cases:
          - name: sum
            command: 4 5
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    text = golden(project, "sum")
    assert "# command: calc 4 5\n" in text
    assert text.endswith("----- stdout -----\n9\n")


# =============================================================================
# Python 関数のケース
# =============================================================================


def test_call_return_raises_and_stdout(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: point
            call: calc:point
            kwargs: {x: 1, y: 2}
          - name: divide_by_zero
            call: calc:divide
            args: [1, 0]
          - name: tags
            call: calc:tags
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=4)
    assert golden(project, "point") == textwrap.dedent(
        """\
        # case: point
        # call: calc:point
        # kwargs: {"x": 1, "y": 2}
        ----- return -----
        {
          "__type__": "Point",
          "x": 1,
          "y": 2
        }
        ----- stdout -----
        point を作ります
        """
    )
    assert golden(project, "divide_by_zero").endswith(
        "----- raises -----\nZeroDivisionError: division by zero\n"
    )
    assert golden(project, "tags").endswith('----- return -----\n[\n  "a",\n  "b"\n]\n')


def test_prepare_call_hook(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import pytest

        @pytest.fixture(scope="session")
        def casebook_env():
            return {"base": 100}

        def pytest_casebook_prepare_call(env, args):
            args.insert(0, env["base"])
        """
    )
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [5]\n")
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden(project, "add").endswith("----- return -----\n105\n")


def test_call_import_error_fails(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: x\n    call: calc:nothing\n")
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*calc:nothing が見つかりません*"])


# =============================================================================
# 状態・正規化
# =============================================================================


STATE_CONFTEST = """
import contextlib
import calc

@contextlib.contextmanager
def _patched(offset):
    original = calc.add
    calc.add = lambda a, b: original(a, b) + offset
    try:
        yield
    finally:
        calc.add = original

def pytest_casebook_setup(data):
    return _patched(data.get("offset", 0))
"""


def test_states_are_named_setup(project: pytest.Pytester) -> None:
    """状態は「名前を付けた setup:」。pytest_casebook_setup に渡り、ケースのたびに当て直す。"""
    project.makeconftest(STATE_CONFTEST)
    write_casebook(
        project,
        """
        states:
          default: {offset: 0}
          broken: {offset: 1000}
        cases:
          - name: normal
            call: calc:add
            args: [1, 2]
          - group: 障害時
            state: broken
            cases:
              - name: broken
                call: calc:add
                args: [1, 2]
              - name: broken_override
                description: "ケースの setup: は状態の内容に上書きで重なる"
                call: calc:add
                args: [1, 2]
                setup: {offset: 10}
          - name: after
            call: calc:add
            args: [1, 2]
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=5)
    assert "# state: default\n" in golden(project, "normal")
    assert golden(project, "broken").endswith("# state: broken\n----- return -----\n1003\n")
    assert golden(project, "broken_override").endswith("----- return -----\n13\n")
    assert golden(project, "after").endswith("----- return -----\n3\n")


def test_state_files_are_merged_with_case_files(project: pytest.Pytester) -> None:
    project.makepyfile(
        lister="""
        from pathlib import Path

        def read_all():
            return {p.name: p.read_text(encoding="utf-8") for p in sorted(Path().iterdir())}
        """
    )
    write_casebook(
        project,
        """
        states:
          default: {}
          with_config:
            files: {config.ini: "mode=base", shared.txt: base}
        cases:
          - name: merged
            state: with_config
            setup:
              files: {shared.txt: case, own.txt: own}
            call: lister:read_all
            expect:
              return: {config.ini: mode=base, shared.txt: case, own.txt: own}
        """,
    )
    project.runpytest().assert_outcomes(passed=2)


def test_state_content_is_checked_like_setup(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "states:\n  bad: {files: {'../x': y}}\ncases:\n  - name: a\n    call: calc:add\n",
    )
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*states.bad*作業ディレクトリからの相対パスで書いてください*"])


def test_normalize_placeholders_patterns_and_builtins(project: pytest.Pytester) -> None:
    project.makepyfile(
        ids="""
        def make():
            return "id=abc123 at 2026-10-19T12:34:56Z req=7f1c0d3e-9a2b-4c5d-8e6f-0123456789ab n=42"
        """
    )
    project.makeconftest(
        """
        def pytest_casebook_placeholders():
            return [("abc123", "<thing>")]

        def pytest_casebook_patterns():
            return [(r"n=\\d+", "n=<n>")]
        """
    )
    write_casebook(project, "cases:\n  - name: ids\n    call: ids:make\n")
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden(project, "ids").endswith(
        '----- return -----\n"id=<thing> at <datetime> req=<uuid> n=<n>"\n'
    )


# =============================================================================
# グループ・マーク・書き方の誤り
# =============================================================================


def test_groups_can_be_selected_with_k(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - group: 足し算
            cases:
              - name: add
                call: calc:add
                args: [1, 2]
          - group: 割り算
            marks: [slow]
            cases:
              - name: divide
                call: calc:divide
                args: [4, 2]
        """,
    )
    project.makeini("[pytest]\npythonpath = .\nmarkers =\n    slow: 遅い\n")
    project.runpytest("--casebook-update", "-k", "足し算").assert_outcomes(passed=1, deselected=2)
    project.runpytest("--casebook-update", "-m", "slow").assert_outcomes(passed=1, deselected=2)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("cases:\n  - name: a\n    call: m:f\n  - name: a\n    call: m:f\n", "ケース名が重複"),
        (
            "cases:\n  - name: Add\n    call: m:f\n  - name: add\n    call: m:f\n",
            "大文字小文字だけが違うケース名",
        ),
        ("cases:\n  - group: g\n    cases: []\n", "cases にケースがありません"),
        ("cases:\n  - name: a\n    call: m:f\n    arg: [1]\n", "知らないキーがあります: arg"),
        ("cases:\n  - name: a\n", "command・call・request・manual のどれか1つ"),
        ("cases:\n  - name: a\n    call: m:f\n    state: x\n", "states がないのに state"),
        (
            "states: {default: {}}\ncases:\n  - name: a\n    call: m:f\n    state: x\n",
            "states に x",
        ),
        ("cases:\n  - name: a b\n    call: m:f\n", "name に使えるのは"),
        ("cases:\n  - name: .hidden\n    call: m:f\n", "先頭に . と - は使えません"),
        ("cases:\n  - name: '-x'\n    call: m:f\n", "先頭に . と - は使えません"),
        ("cases: []\n", "cases にケースがありません"),
        ("env: [A]\ncases:\n  - name: a\n    call: m:f\n", "env は 変数名 -> 値"),
        ("cases:\n  - name: a\n    call: f\n", "'モジュール:関数' の形"),
        ("cases:\n  - name: a\n    call: m:f\n    timeout: 0\n", "0 より大きい秒数"),
        ("cases:\n  - name: a\n    call: m:f\n    timeout: -1\n", "0 より大きい秒数"),
        ("cases:\n  - name: a\n    call: m:f\n    timeout: .inf\n", "0 より大きい秒数"),
        ("cases:\n  - name: unused_golden_files\n    call: m:f\n", "消し忘れの確認に使う"),
        ("cases:\n  - name: a\n    call: m:f\n    skip: true\n", "例: skip: 不具合 #12"),
        ("cases:\n  - name: a\n    call: m:f\n    expect: {}\n", "1つ以上書いてください"),
        ("cases:\n  - name: a\n    call: m:f\n    params: {}\n", "params は、ケースに重ねる"),
        ("cases:\n  - name: a\n    call: m:f\n    params: []\n", "params は、ケースに重ねる"),
        (
            "cases:\n  - name: a\n    call: m:f\n    params: [{args: [1]}]\n",
            "name（ケース名に足す名前）",
        ),
        (
            "cases:\n  - name: a\n    call: m:f\n    params: [{name: x, params: [{name: y}]}]\n",
            "params の中に params は書けません",
        ),
        (
            "cases:\n  - name: a\n    call: m:f\n    params: [{name: x, arg: [1]}]\n",
            "知らないキーがあります: arg",
        ),
        (
            (
                "cases:\n  - name: a\n    call: m:f\n    params: [{name: x}]\n"
                "  - name: a-x\n    call: m:f\n"
            ),
            "ケース名が重複しています: a-x",
        ),
        ("cases: [\n", "YAML として読めません"),
    ],
)
def test_invalid_casebook_is_a_collection_error(
    project: pytest.Pytester, text: str, message: str
) -> None:
    write_casebook(project, text)
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*{message}*"])


def test_distinct_names_are_not_a_case_collision(project: pytest.Pytester) -> None:
    """大文字小文字の確かめは、本当に違う名前（日本語の名前など）には影響しない。"""
    write_casebook(
        project,
        "cases:\n"
        "  - {name: 足し算, call: calc:add, args: [1, 2], expect: {return: 3}}\n"
        "  - {name: 引き算, call: calc:add, args: [1, -2], expect: {return: -1}}\n",
    )
    project.runpytest().assert_outcomes(passed=3)


def test_unused_golden_files_is_a_case_name_without_the_check(project: pytest.Pytester) -> None:
    """check_orphans: false なら、unused_golden_files もケース名に使える（確かめがないため）。"""
    write_casebook(
        project,
        "check_orphans: false\ncases:\n  - name: unused_golden_files\n    call: calc:add\n"
        "    args: [1, 2]\n    expect: {return: 3}\n",
    )
    project.runpytest().assert_outcomes(passed=1)


def test_shared_golden_with_different_results_fails_on_update(project: pytest.Pytester) -> None:
    """
    golden: で同じファイルを指した2つのケースの結果が違えば、--casebook-update で失敗にする
    （あとのケースが黙って上書きし、次の実行で先のケースが失敗するのを防ぐ）。
    """
    write_casebook(
        project,
        """
        cases:
          - {name: three, call: calc:add, args: [1, 2], golden: sum.txt}
          - {name: also_three, call: calc:add, args: [2, 1], golden: sum.txt}
          - {name: seven, call: calc:add, args: [3, 4], golden: sum.txt}
        """,
    )
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=3, failed=1)  # passed のうち1つは unused_golden_files
    shared = "golden/casebook_calc/sum.txt はケース casebook_calc.yaml::three も使っていて"
    result.stdout.fnmatch_lines([f"*[[]seven[]] 期待出力 {shared}*"])
    assert "3" in golden(project, "sum")


def test_run_error_is_shown_once(project: pytest.Pytester) -> None:
    """
    実行の誤り（import できないなど）は、メッセージを1回だけ出す
    （元の例外がつながって「During handling of …」と2回出ない）。
    """
    write_casebook(project, "cases:\n  - name: a\n    call: nope:f\n    expect: {return: 1}\n")
    # 最後の要約（short test summary）は端末の幅で省略が変わるので、出さずに数える
    result = project.runpytest("-rN")
    result.assert_outcomes(failed=1, passed=1)
    out = result.stdout.str()
    assert out.count("No module named 'nope'") == 1
    assert "During handling" not in out
    assert "direct cause" not in out


def test_expect_key_typo_suggests_the_key(project: pytest.Pytester) -> None:
    """expect: の結果のキーの打ち間違いは、observe として失敗するので、正しいキーを示す。"""
    write_casebook(project, "cases:\n  - {name: a, call: calc:add, expect: {retrun: 3}}\n")
    result = project.runpytest()
    result.stdout.fnmatch_lines(["*expect の return の書き間違いではありませんか？*"])


def test_help_is_in_english(project: pytest.Pytester) -> None:
    """pytest --help の説明は英語（pytest のほかの説明と同じく、既定の言語も英語）。"""
    result = project.runpytest("--help")
    result.stdout.fnmatch_lines(["*--casebook-update*rewrite golden files*"])
    assert "期待出力" not in result.stdout.str()


def test_ini_options(project: pytest.Pytester) -> None:
    project.makeini(
        """
        [pytest]
        pythonpath = .
        casebook_files = *.cases.yaml
        casebook_golden_dir = expected
        """
    )
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    project.makefile(
        ".cases.yaml", my="cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n"
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert (project.path / "expected" / "my.cases" / "add.txt").exists()


# =============================================================================
# params（引数だけ違うケースの展開）
# =============================================================================


def test_params_rows_run_as_their_own_cases(project: pytest.Pytester) -> None:
    """params で展開したケースは1件ずつ実行され、失敗した要素は自分の行番号で報告される。"""
    project.makepyfile(shipping="def fee(subtotal):\n    return 0 if subtotal >= 3000 else 500\n")
    write_casebook(
        project,
        """
        cases:
          - name: shipping
            description: 送料の計算
            call: shipping:fee
            params:
              - {name: "0", description: 0 円は送料 500 円, args: [0], expect: {return: 500}}
              - {name: "2999", description: 送料無料のつもり, args: [2999], expect: {return: 0}}
              - {name: "3000", description: 3000 円から送料無料, args: [3000], expect: {return: 0}}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(passed=3, failed=1)  # passed のうち1つは unused_golden_files
    result.stdout.fnmatch_lines(["*[[]shipping-2999[]]（7 行目）*"])


def test_html_report_has_one_row_per_params_element(project: pytest.Pytester) -> None:
    """params で展開したケースは、試験項目表にも1件ずつ行として出る。"""
    write_casebook(
        project,
        """
        cases:
          - name: adding
            call: calc:add
            params:
              - {name: one, args: [1, 0], expect: {return: 1}}
              - {name: two, args: [1, 1], expect: {return: 2}}
        """,
    )
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}").assert_outcomes(passed=3)
    page = report.read_text(encoding="utf-8")
    assert "<div class='name'>adding-one</div>" in page
    assert "<div class='name'>adding-two</div>" in page


# =============================================================================
# HTML レポート
# =============================================================================


def test_html_report_has_levels_and_merged_cells(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        title: 計算ツール
        levels: [大項目, 中項目, 小項目]
        cases:
          - group: 計算
            description: 四則演算
            cases:
              - group: 足し算
                cases:
                  - group: 整数
                    cases:
                      - {name: add1, call: "calc:add", args: [1, 2], description: 1+2}
                      - {name: add2, call: "calc:add", args: [3, 4]}
              - group: 割り算
                cases:
                  - {name: div, call: "calc:divide", args: [1, 0]}
          - {name: plain, call: "calc:add", args: [0, 0]}
        """,
    )
    project.runpytest("--casebook-update")
    # div の期待出力を壊して失敗させる
    path = project.path / "golden" / "casebook_calc" / "div.txt"
    path.write_text("broken\n", encoding="utf-8")

    report = project.path / "out" / "report.html"
    result = project.runpytest(f"--casebook-html={report}")
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*試験項目表（HTML）:*report.html*"])

    page = report.read_text(encoding="utf-8")
    assert "<h1>試験項目表</h1>" in page
    assert "計算ツール" in page
    for label in ("大項目", "中項目", "小項目"):
        assert f"<th class='level'>{label}</th>" in page
    # 縦に結合する行数には、各ケースの下の詳細の行（失敗の詳細・期待出力の内容）も数える。
    # どのケースも期待出力の内容の行を持つので、「計算」は add1・add2・div の6行、
    # 「割り算」は div の2行
    assert "rowspan='6'><div class='group'>計算</div><div class='muted'>四則演算</div>" in page
    assert "rowspan='4'><div class='group'>足し算</div>" in page
    assert "rowspan='4'><div class='group'>整数</div>" in page
    assert "rowspan='2'><div class='group'>割り算</div><td class='level empty' rowspan='2'>" in (
        page.replace("</td>", "")
    )
    # グループのないケースは階層の列が空になる
    empty = "<td class='level empty' rowspan='2'></td>"
    # 行の属性のあと（data-outcome・data-text は絞り込み用）に、空の階層のセルが3つ続く
    assert re.search(rf"<tr id='case-\d+' class='passed'[^>]*>({empty}){{3}}", page)
    # 失敗の一覧と、表の幅いっぱいの詳細の行
    assert "確認が必要なケース" in page
    assert "計算 &gt; 割り算 &gt; div" in page
    assert (
        "<tr class='detail failed'><td colspan='6'><details><summary>失敗の詳細</summary>" in page
    )
    assert page.count("<tr class='detail") == 4  # 期待出力の内容の行が add1・add2・plain にも付く
    assert '<span class="badge failed">失敗 1</span>' in page


def test_html_report_ignores_outcomes_of_other_plugins(project: pytest.Pytester) -> None:
    """
    pytest-rerunfailures の "rerun" のような、知らない結果でも止まらない（数えずに飛ばす）。
    """
    project.makeconftest(
        """
        import pytest

        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_makereport(item, call):
            report = yield
            if call.when == "call" and item.name == "flaky":
                report.outcome = "rerun"
            return report
        """
    )
    write_casebook(
        project,
        """
        check_orphans: false
        cases:
          - {name: flaky, call: calc:add, args: [1, 2], expect: {return: 3}}
          - {name: steady, call: calc:add, args: [1, 2], expect: {return: 3}}
        """,
    )
    report = project.path / "report.html"
    result = project.runpytest(f"--casebook-html={report}")
    assert result.ret == pytest.ExitCode.OK
    assert "INTERNALERROR" not in result.stdout.str()
    assert "steady" in report.read_text(encoding="utf-8")


def test_html_report_in_english(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        states:
          default: {}
          empty: {}
        cases:
          - group: Arithmetic
            cases:
              - {name: add, call: "calc:add", args: [1, 2], state: empty}
              - {name: div, call: "calc:divide", args: [1, 0], expect: {raises: {$contains: zero}}}
        """,
    )
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    result = project.runpytest("-o", "casebook_lang=en", f"--casebook-html={report}")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*Test specification (HTML):*report.html*"])

    page = report.read_text(encoding="utf-8")
    assert '<html lang="en">' in page
    assert "<h1>Test Specification</h1>" in page
    # levels を書かなければ、階層の呼び名も英語の既定になる
    assert "<th class='level'>Category</th>" in page
    assert "<th>Preconditions</th>" in page
    assert "State: empty" in page
    assert "Golden file (add.txt)" in page
    assert "raises contains &quot;zero&quot;" in page
    assert '<span class="badge passed">Passed 2</span>' in page
    assert "3 cases in total" not in page  # unused_golden_files はレポートに出ない
    assert "2 cases in total" in page


@pytest.mark.parametrize("lang", LANGS)
def test_html_report_has_filter(project: pytest.Pytester, lang: str) -> None:
    """ページ上部に、結果と文字での絞り込みが出る（文言は casebook_lang に合わせる）。"""
    write_casebook(
        project,
        """
        cases:
          - group: Arithmetic
            description: four operations
            cases:
              - {name: add, call: "calc:add", args: [1, 2], description: one plus two}
              - {name: wrong, call: "calc:add", args: [1, 2], expect: {return: 4}}
          - {name: plain, call: "calc:add", args: [0, 0], skip: not yet}
        """,
    )
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest("-o", f"casebook_lang={lang}", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    texts = TEXTS[lang]

    # JavaScript が動かなければ、絞り込みは隠れたまま（今までどおりの件数と表が出る）
    assert '<div class="filter" hidden>' in page
    assert f'<span class="badge failed">{texts["outcomes"]["failed"]} 1</span>' in page
    # 「すべて」と、実際にある結果だけの切り替え
    assert f'data-outcome="" aria-pressed="true">{texts["filter_all"]}</button>' in page
    for outcome in ("passed", "skipped", "failed"):
        label = texts["outcomes"][outcome]
        assert f'data-outcome="{outcome}" aria-pressed="false">{label} 1</button>' in page
    assert 'data-outcome="error"' not in page
    assert f'aria-label="{texts["filter"]}"' in page
    assert f'placeholder="{texts["filter_placeholder"]}"' in page
    assert f'data-template="{texts["filter_shown"]}"' in page
    assert f'data-none="{texts["filter_none"]}"' in page
    assert "<script>" in page
    if lang == "en":
        assert not JAPANESE.search(page)

    # 行には、結果と、絞り込みの対象の文字（縦に結合したグループの名前と説明も）を持たせる
    rows = dict(re.findall(r"data-outcome='(\w+)' data-text='([^']*)'", page))
    assert set(rows) == {"passed", "failed", "skipped"}
    assert rows["passed"].split("\n")[:4] == ["Arithmetic", "four operations", "add", "calc:add"]
    assert "one plus two" in rows["passed"]
    assert "return = 4" in rows["failed"]
    assert "not yet" in rows["skipped"]  # スキップの理由も探せる
    # 失敗の詳細の行は今までどおり（JavaScript がケースの行と一緒に出し入れする）
    assert page.count("<tr class='detail failed'><td colspan='6'>") == 1


def test_html_report_is_self_contained(project: pytest.Pytester) -> None:
    """HTML は1つのファイルで完結する（外部のスクリプト・スタイルを読まない）。"""
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert not re.search(r"<(script|link|img|iframe)\b[^>]*\b(src|href)\s*=", page, re.I)
    assert not re.search(r"https?://", page)
    assert "@import" not in page


JAPANESE = re.compile("[぀-ヿ一-鿿]")


def test_expect_failures_in_english(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - {name: wrong_return, call: "calc:add", args: [1, 2], expect: {return: 4}}
          - {name: unexpected_error, call: "calc:divide", args: [1, 0], expect: {return: 0}}
          - {name: no_error, call: "calc:add", args: [1, 2], expect: {raises: ValueError}}
          - name: wrong_items
            call: "calc:add"
            args: [[1], [2]]
            expect: {return: [1, 2, 3]}
        """,
    )
    result = project.runpytest("-o", "casebook_lang=en")
    result.assert_outcomes(failed=4, passed=1)  # passed は unused_golden_files
    result.stdout.fnmatch_lines(
        [
            "*[[]wrong_return[]] (line 2)*",
            "*Differs from the expected result:",
            "*  - return: expected 4 / actual 3",
            "*----- actual return -----",
            "*  - an exception was raised: ZeroDivisionError: *",
            "*  - raises: no exception was raised (returned 3)",
            "*  - return: number of items differs (expected 3 / actual 2)",
        ]
    )
    assert not JAPANESE.search(result.stdout.str())


def test_golden_failures_in_english(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "cases:\n"
        "  - {name: add, call: calc:add, args: [1, 2]}\n"
        "  - {name: sub, call: calc:add, args: [1, -1]}\n",
    )
    project.runpytest("--casebook-update")
    golden = project.path / "golden" / "casebook_calc"
    (golden / "add.txt").write_text("4\n", encoding="utf-8")
    (golden / "sub.txt").unlink()

    result = project.runpytest("-o", "casebook_lang=en")
    result.assert_outcomes(failed=2, passed=1)  # passed は unused_golden_files
    result.stdout.fnmatch_lines(
        [
            "*The output differs from the golden file. If the change is intended,*",
            "*--- golden/casebook_calc/add.txt (expected)",
            "*+++ actual output",
            "*[[]sub[]] The golden file golden/casebook_calc/sub.txt does not exist.*",
        ]
    )
    assert not JAPANESE.search(result.stdout.str())


def test_lang_must_be_known(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    result = project.runpytest("-o", "casebook_lang=fr")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*casebook_lang*ja / en*fr*"])


def test_html_report_marks_updated(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    report = project.path / "report.html"
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    assert '<span class="badge updated">更新 1</span>' in report.read_text(encoding="utf-8")
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    assert '<span class="badge passed">成功 1</span>' in report.read_text(encoding="utf-8")


# add.txt の期待出力の折りたたみ
GOLDEN_ADD_SUMMARY = r"<details class='golden'><summary>期待出力（add.txt）</summary>"


def test_html_report_shows_golden_contents(project: pytest.Pytester) -> None:
    """期待出力ファイルを使うケースは、比べる部分がケースの行の下に折りたたんで出る。"""
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    report = project.path / "report.html"
    # 期待出力はケースを集めるときに読むので、--casebook-update で作ったあとの実行で出る
    project.runpytest("--casebook-update")
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert re.search(GOLDEN_ADD_SUMMARY, page)
    assert "<pre>----- return -----\n3</pre>" in page
    assert "# case:" not in page  # 説明のヘッダーは出さない（比べる部分だけを出す）
    # <…>（実行ごとに変わる値の置き換え）の注記が、ファイルの見出しの下に1回だけ出る
    assert page.count("期待出力の中の &lt;…&gt; は、実行ごとに変わる値の置き換えです") == 1


# 期待出力の比べる部分が 52 行（# exit_code・見出し・0〜49）になるケース
LONG_GOLDEN_CASE = f"""
command_prefix: [{PY}, -c]
cases:
  - name: long
    command: "'[print(i) for i in range(50)]'"
"""


def test_golden_contents_summary_is_cut(project: pytest.Pytester) -> None:
    """summary（既定）は casebook_html_golden_lines 行で打ち切り、残りの行数を添える。"""
    write_casebook(project, LONG_GOLDEN_CASE)
    report = project.path / "report.html"
    project.runpytest("--casebook-update")
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "…（あと 12 行）</pre>" in page  # 52 行を既定の 40 行で打ち切る
    assert "49</pre>" not in page

    project.runpytest("-o", "casebook_html_golden_lines=5", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "…（あと 47 行）</pre>" in page


def test_golden_contents_off_and_full(project: pytest.Pytester) -> None:
    """off なら内容も注記も出さず、full なら打ち切らずに全部出す。"""
    write_casebook(project, LONG_GOLDEN_CASE)
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest("-o", "casebook_html_golden=off", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<details class='golden'" not in page
    assert "<tr class='detail" not in page
    assert "実行ごとに変わる値の置き換えです" not in page

    project.runpytest("-o", "casebook_html_golden=full", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "…（あと" not in page
    assert "49</pre>" in page


def test_collect_only_shows_golden_contents(project: pytest.Pytester) -> None:
    """`--collect-only` の計画の表にも期待出力の内容が出る（実装の前のレビューに使える）。"""
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    report = project.path / "plan.html"
    # 期待出力がまだない（--casebook-update の前）なら、何も出さない（エラーにもしない）
    result = project.runpytest("--collect-only", f"--casebook-html={report}")
    assert result.ret == pytest.ExitCode.OK
    assert "<details class='golden'" not in report.read_text(encoding="utf-8")

    project.runpytest("--casebook-update")
    result = project.runpytest("--collect-only", f"--casebook-html={report}")
    assert result.ret == pytest.ExitCode.OK
    page = report.read_text(encoding="utf-8")
    assert re.search(GOLDEN_ADD_SUMMARY, page)
    assert "<pre>----- return -----\n3</pre>" in page


def test_golden_file_line_is_the_same_with_or_without_contents(project: pytest.Pytester) -> None:
    """
    期待結果の列は、期待出力の内容を下の行に出すときも出さないときも「期待出力ファイル（…）」の
    文字にする（下の折りたたみへのリンクにはしない。印刷しても読めるように）。
    """
    write_casebook(
        project,
        """
        cases:
          - {name: add, call: calc:add, args: [1, 2]}
          - {name: sub, call: calc:add, args: [1, -1], expect: {return: 0}}
        """,
    )
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert page.count("<div class='line'>期待出力ファイル（add.txt）</div>") == 1
    assert page.count("<details class='golden'>") == 1  # expect: のケースには出さない
    assert "<a " not in page.split("<table class='cases'>", 1)[1]

    project.runpytest("-o", "casebook_lang=en", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<div class='line'>Golden file (add.txt)</div>" in page
    assert not JAPANESE.search(page)

    # 内容を出さないとき（off）も同じ文字（折りたたみはない）
    project.runpytest("-o", "casebook_html_golden=off", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<div class='line'>期待出力ファイル（add.txt）</div>" in page
    assert "<details class='golden'>" not in page


def test_expect_and_manual_cases_show_no_golden_contents(project: pytest.Pytester) -> None:
    """expect: のケースと手動のケースには、期待出力の内容の行を出さない。"""
    write_casebook(
        project,
        """
        check_orphans: false
        cases:
          - {name: add, call: calc:add, args: [1, 2], expect: {return: 3}}
          - {name: by_hand, manual: 画面で確かめる, expect: 表示どおり}
        """,
    )
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<details class='golden'" not in page
    assert "<tr class='detail" not in page


def test_golden_contents_have_an_open_all_button(project: pytest.Pytester) -> None:
    """
    期待出力の内容を出すときは、絞り込みの欄に「すべて開く」ボタンが出る。

    押すたびに開く・閉じるが入れ替わる（動きは埋め込みの JavaScript。ここでは、ボタンと
    その2つの表記が HTML にあることと、出さないときに出ないことを確かめる）。
    """
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert (
        '<button type="button" class="golden-toggle" aria-pressed="false"'
        ' data-open="期待出力をすべて開く" data-close="期待出力をすべて閉じる">'
        "期待出力をすべて開く</button>"
    ) in page

    project.runpytest("-o", "casebook_lang=en", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert 'data-close="Collapse all golden files">Expand all golden files</button>' in page

    # 期待出力の内容を出さないとき（off）はボタンも出さない
    project.runpytest("-o", "casebook_html_golden=off", f"--casebook-html={report}")
    assert 'class="golden-toggle"' not in report.read_text(encoding="utf-8")


def test_html_golden_value_must_be_known(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - {name: add, call: calc:add, args: [1, 2]}\n")
    result = project.runpytest("-o", "casebook_html_golden=both", "--casebook-html=report.html")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*casebook_html_golden*off / summary / full*both*"])


PLAN_CASES = """
cases:
  - group: 足し算
    cases:
      - {name: add, call: "calc:add", args: [1, 2], expect: {return: 3}, description: 1+2}
      - {name: wrong, call: "calc:add", args: [1, 2], expect: {return: 4}}
      - {name: later, call: "calc:add", args: [2, 2], expect: {return: 4}}
"""


def test_collect_only_writes_a_plan(project: pytest.Pytester) -> None:
    """--collect-only でも、実行せずに試験項目表を出せる（結果は「未実施」）。"""
    write_casebook(project, PLAN_CASES)
    report = project.path / "plan.html"
    result = project.runpytest("--collect-only", f"--casebook-html={report}")
    assert result.ret == pytest.ExitCode.OK
    page = report.read_text(encoding="utf-8")
    assert "全 3 件" in page
    assert '<span class="badge notrun">未実施 3</span>' in page
    assert "<div class='name'>add</div>" in page
    assert "return = 3" in page  # 期待結果の列は、実行しなくても出る
    assert "<td class='num'>—</td>" in page
    assert not (project.path / "golden").exists()  # 何も実行していない


def test_cases_not_run_stay_in_the_report(project: pytest.Pytester) -> None:
    """-x で止まったときも、実行しなかったケースは「未実施」として表に残る。"""
    write_casebook(project, PLAN_CASES)
    report = project.path / "report.html"
    project.runpytest("-x", f"--casebook-html={report}").assert_outcomes(passed=1, failed=1)
    page = report.read_text(encoding="utf-8")
    assert "全 3 件" in page
    assert '<span class="badge notrun">未実施 1</span>' in page
    assert re.search(r"<tr id='case-\d+' class='notrun'[^>]*>.*?later", page)


def test_deselected_cases_are_not_in_the_report(project: pytest.Pytester) -> None:
    write_casebook(project, PLAN_CASES)
    report = project.path / "report.html"
    project.runpytest("-k", "add", f"--casebook-html={report}").assert_outcomes(passed=1)
    page = report.read_text(encoding="utf-8")
    assert "全 1 件" in page
    assert "notrun" not in page.split("<style>")[0] + page.split("</style>")[1]


def test_japanese_case_names_are_allowed(project: pytest.Pytester) -> None:
    """ケース名は日本語でもよい（先頭の . と - を禁じた分、締めすぎていないことの確認）。"""
    write_casebook(
        project,
        "cases:\n  - name: 足し算_1-2\n    call: calc:add\n    args: [1, 2]\n"
        "    expect: {return: 3}\n",
    )
    project.runpytest().assert_outcomes(passed=2)


def test_command_env_replaces_casebook_dir(project: pytest.Pytester) -> None:
    """env: の値の中の {casebook_dir} も、argv と同じく YAML のディレクトリになる。"""
    posix = project.path.as_posix()
    write_casebook(
        project,
        f"""
        cases:
          - name: envdir
            command:
              - {PY}
              - -c
              - "import os; print(os.path.samefile(os.environ['CASEBOOK_D'], '{posix}'))"
            env: {{CASEBOOK_D: "{{casebook_dir}}"}}
            expect: {{stdout: "True\\n"}}
        """,
    )
    project.runpytest().assert_outcomes(passed=2)


# =============================================================================
# オプションの掛け合わせ（単体では動いても、同時に付けたときに受け渡しがずれないこと）
# =============================================================================

TWO_CASES = """
cases:
  - name: add
    call: calc:add
    args: [1, 2]
  - name: add2
    call: calc:add
    args: [2, 2]
"""


def _golden_details(report: Path) -> list[str]:
    page = report.read_text(encoding="utf-8")
    return re.findall(r"<details class='golden'.*?<pre>(.*?)</pre>", page, re.S)


def test_update_headers_with_html_shows_the_rewritten_golden(project: pytest.Pytester) -> None:
    """--casebook-update-headers と --casebook-html: 書き直したケースは「更新」で、内容も出る。"""
    write_casebook(project, TWO_CASES)
    (project.path / "golden" / "casebook_calc").mkdir(parents=True)
    (project.path / "golden" / "casebook_calc" / "add.txt").write_text("3\n", encoding="utf-8")
    (project.path / "golden" / "casebook_calc" / "add2.txt").write_text("4\n", encoding="utf-8")
    report = project.path / "report.html"
    project.runpytest("--casebook-update-headers", f"--casebook-html={report}").assert_outcomes(
        passed=3
    )
    page = report.read_text(encoding="utf-8")
    assert '<span class="badge updated">更新 2</span>' in page
    assert _golden_details(report) == ["----- return -----\n3", "----- return -----\n4"]
    assert golden(project, "add").startswith("# case: add\n")


def test_update_with_k_rewrites_only_the_selected_cases(project: pytest.Pytester) -> None:
    """--casebook-update と -k: 選んだケースだけ書き直し、ほかの期待出力を迷子と間違えない。"""
    write_casebook(project, TWO_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    add2 = golden(project, "add2")
    write_casebook(
        project,
        TWO_CASES.replace("args: [1, 2]", "args: [1, 3]").replace("args: [2, 2]", "args: [2, 3]"),
    )
    result = project.runpytest("--casebook-update", "-k", "add2")
    result.assert_outcomes(passed=1, deselected=2)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 1 件*", "golden/casebook_calc/add2.txt"])
    assert golden(project, "add2") != add2
    # 選ばなかった add は書き直さないので、次のふつうの実行で古いまま失敗する
    assert golden(project, "add").endswith("----- return -----\n3\n")
    project.runpytest().assert_outcomes(passed=2, failed=1)


def test_update_and_update_headers_together_act_as_update(project: pytest.Pytester) -> None:
    """両方付けたら --casebook-update（結果が違っても書き直す）として動く。"""
    write_casebook(project, TWO_CASES)
    (project.path / "golden" / "casebook_calc").mkdir(parents=True)
    (project.path / "golden" / "casebook_calc" / "add.txt").write_text("9\n", encoding="utf-8")
    result = project.runpytest("--casebook-update", "--casebook-update-headers")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 2 件*"])
    assert golden(project, "add").endswith("----- return -----\n3\n")


def test_update_with_html_under_xdist(project: pytest.Pytester) -> None:
    """pytest-xdist で分けて実行しても、レポートの結果・更新の印・期待出力の内容がそろう。"""
    pytest.importorskip("xdist")
    write_casebook(project, TWO_CASES)
    report = project.path / "report.html"
    result = project.runpytest("-n", "2", "--casebook-update", f"--casebook-html={report}")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 2 件*"])
    page = report.read_text(encoding="utf-8")
    assert "全 2 件" in page
    assert '<span class="badge updated">更新 2</span>' in page
    assert _golden_details(report) == ["----- return -----\n3", "----- return -----\n4"]


def test_env_is_visible_to_an_in_process_hook(project: pytest.Pytester) -> None:
    """env: は実行の間 os.environ に重なるので、run_in_process で動かす CLI からも見える。"""
    project.makeconftest(
        """
        import os

        from pytest_casebook import run_in_process

        def main(argv):
            print(os.environ.get("CASEBOOK_HOOK_T", "unset"))
            return 0

        def pytest_casebook_run_command(argv):
            return run_in_process(main, argv[1:])
        """
    )
    write_casebook(
        project,
        """
        cases:
          - {name: set, command: x, env: {CASEBOOK_HOOK_T: hello}, expect: {stdout: hello}}
          - {name: unset, command: x, expect: {stdout: unset}}
        """,
    )
    project.runpytest().assert_outcomes(passed=3)  # 3 つ目は unused_golden_files


def test_relative_program_in_workdir_gets_a_hint(project: pytest.Pytester) -> None:
    """files のケースで YAML からの相対パスのプログラムがなければ {casebook_dir} を案内する。"""
    project.mkdir("bin")
    (project.path / "bin" / "tool.py").write_text("print('x')\n", encoding="utf-8")
    write_casebook(
        project,
        """
        cases:
          - {name: plain, command: [bin/tool.py]}
          - {name: with_files, command: [bin/tool.py], setup: {files: {a.txt: x}}}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(failed=2, passed=1)
    # 作業ディレクトリのないケースにはヒントを付けない（見つからない・起動できない理由が違う）
    plain = [line for line in result.stdout.lines if "[plain]" in line]
    assert plain
    assert all("{casebook_dir}" not in line for line in plain)
    result.stdout.fnmatch_lines(
        ["*[[]with_files[]] コマンド*bin/tool.py*files を使うケースは一時の作業ディレクトリ*"]
    )


def test_workdir_hint_also_when_program_cannot_start(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    見つからないときだけでなく、起動できないときも {casebook_dir} を案内する。

    Windows（少なくとも windows-2025 の runner）は相対パスのプログラムを親プロセスの
    カレントディレクトリでも探し、YAML の隣の .py を見つけて WinError 193（起動できない）に
    なる。どの OS でも確かめられるよう、起動できない誤りを出す run_subprocess に差し替える。
    """
    from pytest_casebook import plugin
    from pytest_casebook.runner import CasebookRunError

    def cannot_start(argv: list[str], **kwargs: object) -> None:
        raise CasebookRunError(f"コマンドを起動できません: {argv[0]}（WinError 193）")

    monkeypatch.setattr(plugin, "run_subprocess", cannot_start)
    project.mkdir("bin")
    (project.path / "bin" / "tool.py").write_text("print('x')\n", encoding="utf-8")
    write_casebook(
        project,
        """
        cases:
          - {name: plain, command: [bin/tool.py]}
          - {name: with_files, command: [bin/tool.py], setup: {files: {a.txt: x}}}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(failed=2, passed=1)
    # 作業ディレクトリのない「起動できない」には、どちらの案内も付けない
    result.stdout.fnmatch_lines(
        ["*[[]plain[]] コマンドを起動できません: bin/tool.py（WinError 193）"]
    )
    assert "で実行しました" not in result.stdout.str()
    result.stdout.fnmatch_lines(
        ["*[[]with_files[]] コマンドを起動できません*files を使うケースは一時の作業ディレクトリ*"]
    )


def test_marks_and_observe_accept_a_single_string(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - group: g
            marks: slow
            cases:
              - {name: a, call: "calc:add", args: [1, 2], marks: fast, observe: files,
                 setup: {files: {in.txt: hi}}}
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert "=== in.txt ===" in golden(project, "a")
    result = project.runpytest("-m", "slow and fast", "--collect-only", "-q")
    result.stdout.fnmatch_lines(["casebook_calc.yaml::a"])


def test_states_without_default(project: pytest.Pytester) -> None:
    """states: に default がなくても、state: のないケースは「状態なし」で動く。"""
    project.makeconftest(
        """
        def pytest_casebook_setup(case, data):
            print("setup:", case.state, data)
        """
    )
    write_casebook(
        project,
        """
        states:
          outage: {db: down}
        cases:
          - {name: normal, call: "calc:add", args: [1, 2]}
          - {name: broken, call: "calc:add", args: [1, 2], state: outage}
          - {name: typo, call: "calc:add", args: [1, 2], state: outage2}
        """,
    )
    result = project.runpytest("--casebook-update", "-s")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*states に outage2 がありません*"])
    write_casebook(
        project,
        """
        states:
          outage: {db: down}
        cases:
          - {name: normal, call: "calc:add", args: [1, 2]}
          - {name: broken, call: "calc:add", args: [1, 2], state: outage}
        """,
    )
    result = project.runpytest("--casebook-update", "-s")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*setup: default {}*", "*setup: outage {'db': 'down'}*"])
    assert "# state: default\n" in golden(project, "normal")
