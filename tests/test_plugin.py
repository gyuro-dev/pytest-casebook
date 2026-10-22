"""
pytester で一時ディレクトリにケースファイルを作り、プラグインの動きを確認する。
"""

from __future__ import annotations

import re
import textwrap

import pytest
from helpers import PY, golden, write_casebook

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
    result.stdout.fnmatch_lines(["*にない期待出力が*['old.txt']*"])


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
    result.stdout.fnmatch_lines(["*にない期待出力が*[[]'old.json'[]]*"])


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


def test_missing_command_fails_with_message(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: x\n    command: no-such-command-xyz\n")
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*コマンドが見つかりません: no-such-command-xyz*"])


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
        ("cases:\n  - name: a\n    call: m:f\n    arg: [1]\n", "知らないキーがあります: arg"),
        ("cases:\n  - name: a\n", "command・call・request のどれか1つ"),
        ("cases:\n  - name: a\n    call: m:f\n    state: x\n", "states がないのに state"),
        (
            "states: {default: {}}\ncases:\n  - name: a\n    call: m:f\n    state: x\n",
            "states に x",
        ),
        ("cases:\n  - name: a b\n    call: m:f\n", "name に使えるのは"),
        ("cases:\n  - name: a\n    call: f\n", "'モジュール:関数' の形"),
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
    assert "<title>試験項目表</title>" in page
    assert "計算ツール" in page
    for label in ("大項目", "中項目", "小項目"):
        assert f"<th class='level'>{label}</th>" in page
    # 縦に結合する行数には、失敗した div の下の詳細の行も数える
    # 「計算」は add1・add2・div（＋詳細）の4行、「割り算」は div（＋詳細）の2行
    assert "rowspan='4'><div class='group'>計算</div><div class='muted'>四則演算</div>" in page
    assert "rowspan='2'><div class='group'>足し算</div>" in page
    assert "rowspan='2'><div class='group'>整数</div>" in page
    assert "rowspan='2'><div class='group'>割り算</div><td class='level empty' rowspan='2'>" in (
        page.replace("</td>", "")
    )
    # グループのないケースは階層の列が空になる
    empty = "<td class='level empty' rowspan='1'></td>"
    assert re.search(rf"<tr id='case-\d+' class='passed'>({empty}){{3}}", page)
    # 失敗の一覧と、表の幅いっぱいの詳細の行
    assert "確認が必要なケース" in page
    assert "計算 &gt; 割り算 &gt; div" in page
    assert (
        "<tr class='detail failed'><td colspan='6'><details><summary>失敗の詳細</summary>" in page
    )
    assert page.count("<tr class='detail") == 1
    assert '<span class="badge failed">失敗 1</span>' in page


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
    assert "<title>Test Specification</title>" in page
    # levels を書かなければ、階層の呼び名も英語の既定になる
    assert "<th class='level'>Category</th>" in page
    assert "<th>Preconditions</th>" in page
    assert "State: empty" in page
    assert "Golden file (add.txt)" in page
    assert "raises contains &quot;zero&quot;" in page
    assert '<span class="badge passed">Passed 2</span>' in page
    assert "3 cases in total" not in page  # golden_orphans はレポートに出ない
    assert "2 cases in total" in page


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
    result.assert_outcomes(failed=4, passed=1)  # passed は golden_orphans
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
    result.assert_outcomes(failed=2, passed=1)  # passed は golden_orphans
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
    assert re.search(r"<tr id='case-\d+' class='notrun'>.*?later", page)


def test_deselected_cases_are_not_in_the_report(project: pytest.Pytester) -> None:
    write_casebook(project, PLAN_CASES)
    report = project.path / "report.html"
    project.runpytest("-k", "add", f"--casebook-html={report}").assert_outcomes(passed=1)
    page = report.read_text(encoding="utf-8")
    assert "全 1 件" in page
    assert "notrun" not in page.split("<style>")[0] + page.split("</style>")[1]
