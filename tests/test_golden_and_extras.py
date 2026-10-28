"""
期待出力の比べ方（結果だけを比べ、ヘッダーを省ける）と、
async の関数・skip / xfail・HTML の時間の確認。
"""

from __future__ import annotations

import decimal
import math
import re
import textwrap
from pathlib import Path

import pytest
from helpers import PY, golden, write_casebook

from pytest_casebook.golden import parse_golden
from pytest_casebook.serialize import to_jsonable


def write_golden_file(pytester: pytest.Pytester, case: str, text: str) -> Path:
    path = pytester.path / "golden" / "casebook_calc" / f"{case}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# =============================================================================
# 期待出力の読み取り
# =============================================================================


def test_parse_golden_ignores_info_header() -> None:
    content = parse_golden(
        "# case: a\n# description: 古い説明\n# command: x\n# state: s\n# exit_code: 2\n"
        "----- stdout -----\nout\n----- stderr -----\nerr\n",
        "stdout",
    )
    assert content.results == {"exit_code": "2"}
    assert content.sections == {"stdout": "out", "stderr": "err"}


def test_parse_golden_without_markers_is_the_default_section() -> None:
    assert parse_golden("こんにちは\n", "stdout").sections == {"stdout": "こんにちは"}
    assert parse_golden("# exit_code: 0\n3\n", "return").sections == {"return": "3"}
    # 行頭が # でも、決まったキーでなければ本文として扱う
    assert parse_golden("# 見出し\n本文\n", "stdout").sections == {"stdout": "# 見出し\n本文"}
    assert parse_golden("", "stdout").sections == {}


def test_parse_golden_unknown_section_title_is_body() -> None:
    """
    見出しになるのは決まった見出しだけ。ほかの `----- X -----` の行は本文の一部になる。

    知っている見出しとまったく同じ行は、見出しのまま（書かれた期待出力と区別できない）。
    """
    text = "----- stdout -----\na\n----- RESULTS -----\nb\n----- observe: db.users -----\n[]\n"
    assert parse_golden(text, "stdout").sections == {
        "stdout": "a\n----- RESULTS -----\nb",
        "observe: db.users": "[]",
    }
    assert parse_golden("----- stdout -----\na\n----- stderr -----\nb\n", "stdout").sections == {
        "stdout": "a",
        "stderr": "b",
    }


def test_output_with_an_unknown_section_line_is_compared_whole(
    project: pytest.Pytester,
) -> None:
    """
    出力に `----- X -----` の行が2回あっても、見出しとして分けないので、1回目の下の本文も
    比べる（見出しとして分けると、同じ見出しの後のほうだけが残り、前の本文は比べられない）。
    """
    project.makepyfile(
        sections_out="def show(first):\n    print(f'----- X -----\\n{first}')\n"
        "    print('----- X -----\\nsecond')\n"
    )
    case = "cases:\n  - name: show\n    call: sections_out:show\n    args: [{first}]\n"
    write_casebook(project, case.format(first="one"))
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert "----- X -----\none\n----- X -----\nsecond\n" in golden(project, "show")
    write_casebook(project, case.format(first="uno"))
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*-one", "*+uno"])


def test_multiline_command_argument_keeps_exit_code_compared(project: pytest.Pytester) -> None:
    """
    command: の引数に改行があっても、ヘッダーは1行ずつに書く。改行のまま書くと、2行目から
    本文になり、# exit_code: が比べられなくなる（終了コードが変わっても通ってしまう）。
    """
    case = (
        "cases:\n  - name: multi\n"
        '    command: ["{py}", "-c", "print(1)\\nraise SystemExit({code})"]\n'
    )
    write_casebook(project, case.format(py=PY, code=0))
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    text = golden(project, "multi")
    header = text.split("----- stdout -----")[0].splitlines()
    assert all(line.startswith("# ") for line in header), text
    assert "# exit_code: 0" in header
    assert "print(1) raise SystemExit(0)" in text
    write_casebook(project, case.format(py=PY, code=1))
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*-# exit_code: 0", "*+# exit_code: 1"])


# =============================================================================
# 手で書いた期待出力
# =============================================================================


CLI = f"""
command_prefix:
  - {PY}
  - -c
  - "import sys; print('こんにちは'); sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)"
cases:
  - name: hello
    description: あいさつ
    command: "0"
  - name: hello_exit3
    command: "3"
"""


def test_handwritten_golden_with_body_only(project: pytest.Pytester) -> None:
    write_casebook(project, CLI)
    write_golden_file(project, "hello", "こんにちは\n")
    # exit_code を書かなければ終了コードは比べない（3 で終わっても一致）
    write_golden_file(project, "hello_exit3", "こんにちは\n")
    project.runpytest().assert_outcomes(passed=3)


def test_handwritten_golden_checks_exit_code_when_written(project: pytest.Pytester) -> None:
    write_casebook(project, CLI)
    write_golden_file(project, "hello", "# exit_code: 0\nこんにちは\n")
    write_golden_file(project, "hello_exit3", "# exit_code: 0\nこんにちは\n")
    result = project.runpytest()
    result.assert_outcomes(passed=2, failed=1)
    result.stdout.fnmatch_lines(["*-# exit_code: 0", "*+# exit_code: 3"])


def test_info_header_changes_do_not_fail(project: pytest.Pytester) -> None:
    write_casebook(project, CLI)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    path = project.path / "golden" / "casebook_calc" / "hello.txt"
    text = path.read_text(encoding="utf-8")
    assert "# description:" not in text
    # 古い形式の description や、変わってしまった command のヘッダーは比べない
    path.write_text(
        text.replace("# command:", "# description: 古い説明\n# command: old"), encoding="utf-8"
    )
    project.runpytest().assert_outcomes(passed=3)


def test_missing_section_means_empty(project: pytest.Pytester) -> None:
    project.makepyfile(
        noisy="import sys\n\ndef run():\n    print('warn', file=sys.stderr)\n    return 1\n"
    )
    write_casebook(project, "cases:\n  - name: noisy\n    call: noisy:run\n")
    write_golden_file(project, "noisy", "1\n")
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    # 書いていない stderr は空を期待する。差分には比べる部分だけが出る
    result.stdout.fnmatch_lines(["*----- stderr -----", "*+warn"])
    assert "# case:" not in result.stdout.str()


def test_handwritten_return_and_raises(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: add
            call: calc:add
            args: [1, 2]
          - name: zero
            call: calc:divide
            args: [1, 0]
        """,
    )
    write_golden_file(project, "add", "3\n")
    write_golden_file(project, "zero", "----- raises -----\nZeroDivisionError: division by zero\n")
    project.runpytest().assert_outcomes(passed=3)
    # 例外が出るのに return を書いた場合は失敗する
    write_golden_file(project, "zero", "1.0\n")
    project.runpytest().assert_outcomes(passed=2, failed=1)


# =============================================================================
# --casebook-update の、書き直したファイルの一覧
# =============================================================================


UPDATE_LIST_CASES = """
cases:
  - {name: add, call: "calc:add", args: [1, 2]}
  - {name: tags, call: "calc:tags"}
"""


def test_update_lists_rewritten_golden_files(project: pytest.Pytester) -> None:
    write_casebook(project, UPDATE_LIST_CASES)
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(
        [
            "*書き直した期待出力: 2 件*",
            "golden/casebook_calc/add.txt",
            "golden/casebook_calc/tags.txt",
        ]
    )


def test_update_without_changes_lists_nothing(project: pytest.Pytester) -> None:
    write_casebook(project, UPDATE_LIST_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    # 2回目は結果が変わらず書き直さないので、一覧の代わりに 0 件の 1 行を出す
    # （ふつうの実行と見分けがつき、オプションが効いたことが分かる）
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 0 件（2 件は同じ）*"])
    assert "golden/casebook_calc/" not in result.stdout.str()


def test_update_without_changes_in_english(project: pytest.Pytester) -> None:
    write_casebook(project, UPDATE_LIST_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    result = project.runpytest("--casebook-update", "-o", "casebook_lang=en")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*Updated golden files: 0 (2 unchanged)*"])


def test_update_counts_a_shared_golden_file_once(project: pytest.Pytester) -> None:
    """同じ期待出力ファイルを使う 2 つのケースは、「同じ」の件数でもファイル 1 件に数える。"""
    write_casebook(
        project,
        """
        cases:
          - {name: add, call: "calc:add", args: [1, 2], golden: same.txt}
          - {name: add2, call: "calc:add", args: [1, 2], golden: same.txt}
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 0 件（1 件は同じ）*"])


def test_normal_run_lists_nothing(project: pytest.Pytester) -> None:
    write_casebook(project, UPDATE_LIST_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    result = project.runpytest()
    result.assert_outcomes(passed=3)
    assert "書き直した期待出力" not in result.stdout.str()


def test_update_list_header_in_english(project: pytest.Pytester) -> None:
    write_casebook(project, UPDATE_LIST_CASES)
    result = project.runpytest("--casebook-update", "-o", "casebook_lang=en")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(
        [
            "*Updated golden files: 2*",
            "golden/casebook_calc/add.txt",
            "golden/casebook_calc/tags.txt",
        ]
    )


# 引数1つ目を出力し、2つ目の終了コードで終わるコマンド
ECHO_EXIT = f"""
command_prefix:
  - {PY}
  - -c
  - "import sys; print(sys.argv[1]); sys.exit(int(sys.argv[2]))"
cases:
  - name: fails
    command: "a {{fails}}"
  - name: text
    command: "{{text}} 0"
  - name: hand
    command: "{{hand}}"
"""


def test_update_list_notes_result_header_changes(project: pytest.Pytester) -> None:
    """結果のヘッダー（exit_code）が変わったファイルは、一覧で `(exit_code 0 → 2)` と注記する。"""
    write_casebook(project, ECHO_EXIT.format(fails=0, text="a", hand="a 0"))
    project.runpytest("--casebook-update").assert_outcomes(passed=4)
    # 手で書いた、# exit_code: のない期待出力（終了コードは比べていない）
    write_golden_file(project, "hand", "a\n")
    write_casebook(project, ECHO_EXIT.format(fails=2, text="b", hand="b 3"))
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "*書き直した期待出力: 3 件*",
            "golden/casebook_calc/fails.txt (exit_code 0 → 2)",
            # 出力だけが変わったものと、古いファイルが終了コードを比べていなかったものは注記しない
            "golden/casebook_calc/hand.txt",
            "golden/casebook_calc/text.txt",
        ]
    )
    assert "# exit_code: 2\n" in golden(project, "fails")


# =============================================================================
# async の関数・skip / xfail
# =============================================================================


def test_async_function_is_awaited(project: pytest.Pytester) -> None:
    project.makepyfile(
        aio="""
        import asyncio

        async def add(a, b):
            await asyncio.sleep(0)
            return a + b

        async def boom():
            raise ValueError("async で失敗")
        """
    )
    write_casebook(
        project,
        """
        cases:
          - name: add
            call: aio:add
            args: [1, 2]
            expect: {return: 3}
          - name: boom
            call: aio:boom
            expect: {raises: "ValueError: async で失敗"}
        """,
    )
    project.runpytest().assert_outcomes(passed=3)


def test_skip_and_xfail_with_reason(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - group: 準備中
            skip: 仕様が決まっていない
            cases:
              - {name: later1, call: "calc:add", args: [1, 2]}
              - {name: later2, call: "calc:add", args: [1, 2]}
          - name: known_bug
            xfail: 0 で割ると例外になる不具合（#12）
            call: calc:divide
            args: [1, 0]
            expect: {return: 0}
          - name: own_skip
            skip: このケースだけ止める
            call: calc:add
            args: [1, 2]
        """,
    )
    report = project.path / "report.html"
    result = project.runpytest("-rsx", f"--casebook-html={report}")
    result.assert_outcomes(skipped=3, xfailed=1, passed=1)
    result.stdout.fnmatch_lines(["*仕様が決まっていない*", "*0 で割ると例外になる不具合*"])
    page = report.read_text(encoding="utf-8")
    assert "<div class='muted note'>仕様が決まっていない</div>" in page
    assert "<div class='muted note'>このケースだけ止める</div>" in page
    assert "<div class='muted note'>0 で割ると例外になる不具合（#12）</div>" in page


def test_html_time_excludes_session_fixture_setup(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import time
        import pytest

        @pytest.fixture(scope="session")
        def casebook_env():
            time.sleep(0.5)  # 環境を作るのに時間がかかる
        """
    )
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    report = project.path / "report.html"
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    times = re.findall(r"<td class='num'>(\d+) ms</td>", report.read_text(encoding="utf-8"))
    assert times
    assert int(times[0]) < 400


def test_golden_written_by_update_has_no_description(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "cases:\n  - name: add\n    description: 説明\n    call: calc:add\n    args: [1, 2]\n",
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert (
        golden(project, "add")
        == "# case: add\n# call: calc:add\n# args: [1, 2]\n----- return -----\n3\n"
    )


def test_html_level_columns_follow_actual_depth(project: pytest.Pytester) -> None:
    """階層の列は、実際のグループの深さだけ出す（levels に3つあっても、1階層なら1列）。"""
    write_casebook(
        project,
        """
        levels: [大項目, 中項目, 小項目]
        cases:
          - group: 足し算
            cases:
              - {name: add, call: "calc:add", args: [1, 2], expect: {return: 3}}
        """,
    )
    write_casebook(
        project, "cases:\n  - {name: flat, call: 'calc:add', args: [1, 1]}\n", name="casebook_flat"
    )
    report = project.path / "report.html"
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    sections = report.read_text(encoding="utf-8").split("<section>")[1:]
    by_title = {s.split("</h2>")[0]: s for s in sections}
    grouped = next(s for t, s in by_title.items() if "casebook_calc" in t)
    flat = next(s for t, s in by_title.items() if "casebook_flat" in t)
    assert grouped.count("<th class='level'>") == 1
    assert "<th class='level'>大項目</th>" in grouped
    assert "中項目" not in grouped
    assert "<th class='level'>" not in flat


def test_case_line_numbers(project: pytest.Pytester) -> None:
    """ケースの YAML の行を、pytest の場所（reportinfo）と失敗の説明に出す。"""
    write_casebook(
        project,
        """
        cases:
          - group: 足し算
            cases:
              - name: ok
                call: calc:add
                args: [1, 2]
                expect: {return: 3}
              - name: wrong
                call: calc:add
                args: [1, 2]
                expect: {return: 4}
        """,
    )
    result = project.runpytest("--junitxml=junit.xml", "-o", "junit_family=xunit1")
    result.assert_outcomes(passed=2, failed=1)
    # wrong の「- name:」は 8 行目（reportinfo と junit は 0 から数えるので 7）
    result.stdout.fnmatch_lines(["*[[]wrong[]]（8 行目） 足し算*"])
    junit = (project.path / "junit.xml").read_text(encoding="utf-8")
    assert 'name="wrong" file="casebook_calc.yaml" line="7"' in junit


def test_load_sets_case_line(tmp_path: Path) -> None:
    import pytest_casebook

    path = tmp_path / "casebook_x.yaml"
    path.write_text("cases:\n  - name: a\n    call: m:f\n  - name: b\n    call: m:f\n", "utf-8")
    assert [c.line for c in pytest_casebook.load(path).cases] == [1, 3]


def test_html_diff_lines_are_colored(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    path = project.path / "golden" / "casebook_calc" / "add.txt"
    path.parent.mkdir(parents=True)
    path.write_text("4\n", encoding="utf-8")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<span class='diff-del'>-4</span>" in page
    assert "<span class='diff-add'>+3</span>" in page


# =============================================================================
# ini の casebook_golden_description（# description: の行）
# =============================================================================


DESCRIBED_CASES = """
cases:
  - name: add
    description: 1 と 2 を足す
    call: calc:add
    args: [1, 2]
  - name: plain
    call: calc:add
    args: [3, 4]
"""


def test_update_writes_description_when_enabled(project: pytest.Pytester) -> None:
    write_casebook(project, DESCRIBED_CASES)
    project.runpytest(
        "--casebook-update", "-o", "casebook_golden_description=true"
    ).assert_outcomes(passed=3)
    assert golden(project, "add").startswith(
        "# case: add\n# description: 1 と 2 を足す\n# call: calc:add\n"
    )
    # description のないケースには書かない
    assert "# description:" not in golden(project, "plain")
    # 行は説明で比べないので、設定の on / off どちらでも比較は成功する
    project.runpytest("-o", "casebook_golden_description=true").assert_outcomes(passed=3)
    project.runpytest().assert_outcomes(passed=3)


def test_description_does_not_rewrite_unchanged_golden(project: pytest.Pytester) -> None:
    """設定を入れても、結果が変わらない限り既存のファイルは書き直さない（行も足さない）。"""
    write_casebook(project, DESCRIBED_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    assert "# description:" not in golden(project, "add")
    result = project.runpytest("--casebook-update", "-o", "casebook_golden_description=true")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 0 件（2 件は同じ）*"])
    assert "# description:" not in golden(project, "add")
    # 行のないファイルのままでも、設定を入れた比較は成功する
    project.runpytest("-o", "casebook_golden_description=true").assert_outcomes(passed=3)


def test_multiline_description_becomes_one_line(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: add
            description: |
              1 と 2 を
              足す
            call: calc:add
            args: [1, 2]
        """,
    )
    project.runpytest(
        "--casebook-update", "-o", "casebook_golden_description=true"
    ).assert_outcomes(passed=2)
    assert "# description: 1 と 2 を 足す\n" in golden(project, "add")


# =============================================================================
# --casebook-update-headers（結果が同じファイルのヘッダーを書き直す）
# =============================================================================


def test_update_headers_adds_description(project: pytest.Pytester) -> None:
    write_casebook(project, DESCRIBED_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    plain = golden(project, "plain")
    result = project.runpytest(
        "--casebook-update-headers", "-o", "casebook_golden_description=true"
    )
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 1 件*", "golden/casebook_calc/add.txt"])
    assert golden(project, "add").startswith("# case: add\n# description: 1 と 2 を足す\n")
    # description のないケースは変わらない
    assert golden(project, "plain") == plain
    # もう一度実行しても、書き直すものはない（0 件の 1 行だけ出る）
    result = project.runpytest(
        "--casebook-update-headers", "-o", "casebook_golden_description=true"
    )
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*書き直した期待出力: 0 件（2 件は同じ）*"])


def test_update_headers_fails_when_results_differ(project: pytest.Pytester) -> None:
    write_casebook(project, DESCRIBED_CASES)
    path = write_golden_file(project, "add", "4\n")
    write_golden_file(project, "plain", "7\n")
    result = project.runpytest(
        "--casebook-update-headers", "-o", "casebook_golden_description=true"
    )
    result.assert_outcomes(passed=2, failed=1)
    result.stdout.fnmatch_lines(["*出力が期待と異なります*"])
    # 結果が違うファイルはそのまま。結果が同じ plain は書き直す
    assert path.read_text(encoding="utf-8") == "4\n"
    assert golden(project, "plain").startswith("# case: plain\n")
    result.stdout.fnmatch_lines(["*書き直した期待出力: 1 件*", "golden/casebook_calc/plain.txt"])


def test_update_headers_rewrites_handwritten_golden(project: pytest.Pytester) -> None:
    write_casebook(project, CLI)
    write_golden_file(project, "hello", "こんにちは\n")
    write_golden_file(project, "hello_exit3", "こんにちは\n")
    # ふつうの実行では、手で書いた形のまま
    project.runpytest().assert_outcomes(passed=3)
    assert golden(project, "hello") == "こんにちは\n"
    # 結果だけを比べるので、ヘッダーを省いたファイルは --casebook-update と同じ形になる
    project.runpytest("--casebook-update-headers").assert_outcomes(passed=3)
    hello = golden(project, "hello")
    assert hello.startswith("# case: hello\n# command: ")
    assert hello.endswith("# exit_code: 0\n----- stdout -----\nこんにちは\n")
    assert "# exit_code: 3\n" in golden(project, "hello_exit3")


def test_update_headers_does_not_create_missing_golden(project: pytest.Pytester) -> None:
    write_casebook(project, CLI)
    result = project.runpytest("--casebook-update-headers")
    result.assert_outcomes(passed=1, failed=2)
    result.stdout.fnmatch_lines(["*期待出力 golden/casebook_calc/hello.txt がありません*"])
    assert not (project.path / "golden").exists()


# =============================================================================
# to_jsonable の Decimal
# =============================================================================


def test_decimal_becomes_a_number(project: pytest.Pytester) -> None:
    """
    Decimal は数として比べられる（DynamoDB の数は Decimal で返るため）。

    整数なら int、そうでなければ float にする。observe の hook が Decimal を返しても、
    YAML の `price: 300` がそのまま一致する。
    """
    assert to_jsonable(decimal.Decimal("300")) == 300
    assert isinstance(to_jsonable(decimal.Decimal("300")), int)
    assert to_jsonable(decimal.Decimal("1.5")) == 1.5
    assert isinstance(to_jsonable(decimal.Decimal("1.5")), float)
    assert to_jsonable({"price": decimal.Decimal("300")}) == {"price": 300}
    assert to_jsonable([decimal.Decimal("3E+2")]) == [300]
    # 整数にできない NaN・Infinity でも落ちない
    assert math.isnan(to_jsonable(decimal.Decimal("NaN")))
    assert to_jsonable(decimal.Decimal("-Infinity")) == float("-inf")
    assert to_jsonable(decimal.Decimal("sNaN")) == "Decimal('sNaN')"

    project.makeconftest(
        """
        import decimal

        def pytest_casebook_observe(target):
            return [{"id": "1", "price": decimal.Decimal("300")}]
        """
    )
    write_casebook(
        project,
        """
        cases:
          - name: rows
            call: calc:add
            args: [1, 2]
            observe: [db.rows]
            expect:
              return: 3
              db.rows: [{id: "1", price: 300}]
        """,
    )
    project.runpytest().assert_outcomes(passed=2)


def test_html_shows_the_golden_written_by_update(project: pytest.Pytester) -> None:
    """--casebook-update と --casebook-html を一緒に使うと、書き直したあとの期待出力を出す。"""
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    report = project.path / "report.html"

    def shown() -> list[str]:
        page = report.read_text(encoding="utf-8")
        return re.findall(r"<details class='golden'.*?<pre>(.*?)</pre>", page, re.S)

    # 集めるときにはまだ期待出力がない
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    assert shown() == ["----- return -----\n3"]
    # 集めるときの古い内容（4）ではなく、書き直した内容（3）を出す
    path = project.path / "golden" / "casebook_calc" / "add.txt"
    path.write_text("4\n", encoding="utf-8")
    project.runpytest("--casebook-update", f"--casebook-html={report}")
    assert shown() == ["----- return -----\n3"]


def test_update_list_notes_failing_results_of_new_golden(project: pytest.Pytester) -> None:
    """新しく作る期待出力でも、失敗の結果（0 でない exit_code・raises）は一覧で注記する。"""
    write_casebook(
        project,
        f"""
        cases:
          - name: ok
            command: [{PY}, -c, "print('a')"]
          - name: fails
            command: [{PY}, -c, "import sys; sys.exit(3)"]
          - name: raises
            call: calc:divide
            args: [1, 0]
        """,
    )
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "*書き直した期待出力: 3 件*",
            "golden/casebook_calc/fails.txt (new, exit_code 3)",
            "golden/casebook_calc/ok.txt",
            "golden/casebook_calc/raises.txt (new, raises)",
        ]
    )


def test_html_shows_a_shared_golden_for_every_case(project: pytest.Pytester) -> None:
    """同じ期待出力ファイルを使うケースは、先のケースが書いたあとのケースでも内容が出る。"""
    write_casebook(
        project,
        """
        cases:
          - {name: three, call: calc:add, args: [1, 2], golden: sum.txt}
          - {name: also_three, call: calc:add, args: [2, 1], golden: sum.txt}
        """,
    )
    report = project.path / "report.html"
    project.runpytest("--casebook-update", f"--casebook-html={report}").assert_outcomes(passed=3)
    page = report.read_text(encoding="utf-8")
    shown = re.findall(r"<details class='golden'.*?<pre>(.*?)</pre>", page, re.S)
    assert shown == ["----- return -----\n3", "----- return -----\n3"]


def test_diff_shows_control_characters(project: pytest.Pytester) -> None:
    """ANSI の色などの制御文字は、差分では \x1b の形で見せる（端末が色として食べないように）。"""
    write_casebook(
        project,
        f"cases:\n  - name: color\n    command: [{PY}, -c, \"print('\\x1b[32mok\\x1b[0m')\"]\n",
    )
    write_golden_file(project, "color", "\x1b[31mok\x1b[0m\n")
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines([r"-\x1b[[]31mok\x1b[[]0m", r"+\x1b[[]32mok\x1b[[]0m"])
    assert "\x1b[" not in result.stdout.str()
