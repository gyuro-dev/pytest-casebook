"""値の中の比べ方（$contains など）・リストで書く command・期待結果の列の表記の確認。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from helpers import write_casebook

from pytest_casebook.expect import find_matcher_errors, match_value
from pytest_casebook.messages import language

ROWS = [{"id": 1, "msg": "在庫が足りません（残り 0）"}, {"id": 2, "msg": "OK"}]


@pytest.mark.parametrize(
    "expected",
    [
        [{"msg": {"$contains": "在庫が足りません"}}, {"id": 2}],
        [{"msg": {"$regex": r"残り \d+"}}, {}],
        {"$unordered": [{"id": 2}, {"id": 1}]},
        {"$includes": [{"id": 2}]},
        {"$includes": [{"msg": {"$contains": "OK"}}]},
    ],
)
def test_value_matchers_match(expected: object) -> None:
    assert match_value(expected, ROWS, "rows") == []


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ([{"msg": {"$contains": "成功"}}, {}], 'rows[0].msg: "成功" が含まれていません'),
        ({"$unordered": [{"id": 1}]}, "rows: 件数が違います（期待 1 件 / 実際 2 件）"),
        ({"$includes": [{"id": 3}]}, 'rows: {"id": 3} に合う要素がありません（期待の [0]）'),
        ({"$includes": [{"id": 1}, {"id": 1}]}, "期待の [1]"),  # 同じ要素は2回使わない
        ({"$contains": "x"}, "rows: 文字列ではありません"),
    ],
)
def test_value_matchers_mismatch(expected: object, message: str) -> None:
    problems = match_value(expected, ROWS, "rows", lang="ja")
    assert problems
    assert message in problems[0]


def test_data_without_dollar_is_still_data() -> None:
    """$ のないキーはデータとして比べる（contains というキーを持つデータと紛れない）。"""
    assert match_value({"contains": "a"}, {"contains": "a", "x": 1}, "v") == []
    assert match_value({"contains": "a"}, {"contains": "ab"}, "v") != []


def test_find_matcher_errors() -> None:
    assert find_matcher_errors({"$contains": 1}, "json") == ["json: $contains needs a string"]
    with language("ja"):
        _check_find_matcher_errors_in_japanese()


def _check_find_matcher_errors_in_japanese() -> None:
    assert find_matcher_errors({"a": [{"$nope": 1}]}, "json")[0].startswith(
        "json.a[0]: 知らない比べ方です: $nope"
    )
    assert "文字列を書いて" in find_matcher_errors({"$contains": 1}, "json")[0]
    assert "リストを書いて" in find_matcher_errors({"$includes": "a"}, "json")[0]
    assert "正規表現の誤り" in find_matcher_errors({"$regex": "("}, "json")[0]
    assert find_matcher_errors({"$unordered": [{"a": 1}]}, "json") == []


def test_matchers_in_yaml(project: pytest.Pytester) -> None:
    project.makepyfile(
        rows="def get():\n    return [{'id': 2, 'msg': 'b'}, {'id': 1, 'msg': 'a-1'}]\n"
    )
    write_casebook(
        project,
        """
        cases:
          - name: ok
            call: rows:get
            expect:
              return:
                $unordered:
                  - {id: 1, msg: {$regex: '^a-\\d$'}}
                  - {id: 2}
          - name: typo
            call: rows:get
            expect:
              return: {$unorderd: []}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*expect.return: 知らない比べ方です: $unorderd*"])


def test_command_as_list_keeps_backslashes(pytester: pytest.Pytester) -> None:
    """command をリストで書くと区切らずにそのまま渡す（Windows のパスの \\ が消えない）。"""
    py = Path(sys.executable).as_posix()
    # 引数を1つずつ「<引数>」の形で出す
    script = "import sys; print(''.join(f'<{a}>' for a in sys.argv[1:]))"
    text = (
        f'command_prefix: [{py}, -c, "{script}"]\n'
        "cases:\n"
        "  - name: as_list\n"
        r"    command: ['C:\data\in.csv', 'a b']" + "\n"
        r"    expect: {stdout: '<C:\data\in.csv><a b>'}" + "\n"
        "  - name: as_string\n"
        r"    command: 'C:\data\in.csv'" + "\n"
        "    expect: {stdout: '<C:datain.csv>'}  # 文字列だと shell の書き方として \\ が消える\n"
    )
    (pytester.path / "casebook_x.yaml").write_text(text, encoding="utf-8")
    pytester.runpytest().assert_outcomes(passed=3)


def test_report_shows_body_and_headers_matchers(project: pytest.Pytester) -> None:
    project.makeconftest(
        "from pytest_casebook import HttpResponse\n\n"
        "def pytest_casebook_request(request):\n"
        "    return HttpResponse(200, 'エラーです', {'X-Id': 'a1'})\n"
    )
    write_casebook(
        project,
        """
        cases:
          - name: r
            request: /x
            expect:
              body: {contains: エラー}
              headers: {X-Id: {regex: '^a\\d$'}, X-Other: b}
        """,
    )
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "body が「エラー」を含む" in page
    assert "headers.X-Id が「^a\\d$」（正規表現）に合う" in page
    assert "headers.X-Other = &quot;b&quot;" in page


# =============================================================================
# リストの比べ方・書き方の誤りの行番号・golden のパス・期待出力の後始末・差分の色
# =============================================================================


@pytest.mark.parametrize("name", ["$unordered", "$includes"])
def test_list_matchers_do_not_depend_on_order(name: str) -> None:
    """広い条件の要素を先に書いても、細かい条件の要素と取り合わずに一致する。"""
    actual = [{"type": "A", "flag": True}, {"type": "A", "flag": False}]
    expected = {name: [{"type": "A"}, {"type": "A", "flag": True}]}
    assert match_value(expected, actual, "rows") == []


def test_list_matchers_report_only_unmatchable_items() -> None:
    actual = [{"type": "A"}, {"type": "B"}]
    problems = match_value({"$includes": [{"type": "A"}, {"type": "C"}]}, actual, "rows", lang="ja")
    assert problems == ['rows: {"type": "C"} に合う要素がありません（期待の [1]）']


def test_collection_errors_show_line_numbers(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - group: g
            cases:
              - name: ok
                call: calc:add
              - name: typo
                call: calc:add
                expct: {return: 1}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        ["*cases[[]0[]]（2 行目）*cases[[]1[]]（6 行目）*知らないキーがあります: expct*"]
    )


@pytest.mark.parametrize("golden", ["../out.txt", "/tmp/out.txt", "C:/out.txt", "a/../../b.txt"])
def test_golden_must_stay_in_golden_dir(project: pytest.Pytester, golden: str) -> None:
    write_casebook(project, f"cases:\n  - name: a\n    call: calc:add\n    golden: '{golden}'\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*golden は期待出力の置き場所からの相対パスで書いてください*"])


def test_golden_subdirectory_is_allowed(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "cases:\n  - name: a\n    call: calc:add\n    args: [1, 2]\n    golden: sub/a.txt\n",
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert (project.path / "golden" / "casebook_calc" / "sub" / "a.txt").exists()


def test_html_colors_multiline_expect_diff(project: pytest.Pytester) -> None:
    """expect: の複数行の差分にも色を付ける（箇条書きの行には付けない）。"""
    project.makepyfile(lines="def get():\n    print('a')\n    print('b')\n")
    write_casebook(
        project,
        """
        cases:
          - name: lines
            call: lines:get
            expect:
              stdout: |
                a
                X
        """,
    )
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<span class='diff-del'>    -X</span>" in page
    assert "<span class='diff-add'>    +b</span>" in page
    assert "<span class='diff-del'>  - stdout" not in page


def test_html_does_not_color_actual_values_outside_the_diff(project: pytest.Pytester) -> None:
    """
    差分の外（「----- 実際の return -----」の下の実際の値）の `- item` や `+10` の行には
    色を付けない。差分の行には、これまでどおり付ける。
    """
    project.makepyfile(
        lines="def get():\n    print('a')\n    print('b')\n    return '- item\\n+10'\n"
    )
    write_casebook(
        project,
        """
        cases:
          - name: lines
            call: lines:get
            expect:
              stdout: |
                a
                X
              return: other
        """,
    )
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<span class='diff-del'>    -X</span>" in page
    assert "<span class='diff-add'>    +b</span>" in page
    assert "----- 実際の return -----\n- item\n+10" in page
    assert "<span class='diff-del'>- item" not in page
    assert "<span class='diff-add'>+10" not in page
    assert "<span class='diff-del'>-----" not in page


def test_colorize_only_inside_unified_diff_blocks() -> None:
    from pytest_casebook.report import _colorize

    # 期待出力ファイルとの差分（字下げなし）。差分の前の行には色を付けない
    golden_diff = ["- before", "--- expected (a.txt)", "+++ actual output", "@@ -1 +1 @@"]
    golden_diff += [" same", "-old", "+new"]
    assert _colorize("\n".join(golden_diff)).split("\n") == [
        "- before",
        "<span class='diff-file'>--- expected (a.txt)</span>",
        "<span class='diff-file'>+++ actual output</span>",
        "<span class='diff-hunk'>@@ -1 +1 @@</span>",
        " same",
        "<span class='diff-del'>-old</span>",
        "<span class='diff-add'>+new</span>",
    ]
    # expect: の失敗（差分は4つの空白で字下げ）。字下げの違う行で差分が終わる
    expect_failure = ["  - stdout: differs", "    --- expected stdout", "    +++ actual stdout"]
    expect_failure += ["    @@ -1 +1 @@", "    -X", "    +b", "", "  - return: differs"]
    expect_failure += ["----- actual return -----", "- item", "+10"]
    assert _colorize("\n".join(expect_failure)).split("\n") == [
        "  - stdout: differs",
        "<span class='diff-file'>    --- expected stdout</span>",
        "<span class='diff-file'>    +++ actual stdout</span>",
        "<span class='diff-hunk'>    @@ -1 +1 @@</span>",
        "<span class='diff-del'>    -X</span>",
        "<span class='diff-add'>    +b</span>",
        "",
        "  - return: differs",
        "----- actual return -----",
        "- item",
        "+10",
    ]


def test_orphan_check_looks_into_subdirectories(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "cases:\n  - name: a\n    call: calc:add\n    args: [1, 2]\n    golden: sub/a.txt\n",
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    (project.path / "golden" / "casebook_calc" / "sub" / "old.txt").write_text("x", "utf-8")
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*にない期待出力が*['sub/old.txt']*"])


def _two_yamls(project: pytest.Pytester, a_golden_dir: str, b_golden_dir: str | None) -> None:
    b_line = f"golden_dir: {b_golden_dir}\n" if b_golden_dir else ""
    write_casebook(
        project,
        f"golden_dir: {a_golden_dir}\ncases:\n  - name: a\n    call: calc:add\n    args: [1, 2]\n",
        name="casebook_a",
    )
    write_casebook(
        project,
        f"{b_line}cases:\n  - name: b\n    call: calc:add\n    args: [3, 4]\n",
        name="casebook_b",
    )


def test_shared_golden_dir_does_not_report_each_other(project: pytest.Pytester) -> None:
    """2つの YAML が同じ golden_dir: を使っても、互いの期待出力を消し忘れと間違えない。"""
    _two_yamls(project, "shared", "shared")
    project.runpytest("--casebook-update").assert_outcomes(passed=4)
    project.runpytest().assert_outcomes(passed=4)
    # 1ファイルだけ流しても、同じディレクトリのもう1つの YAML を読んで判断する
    project.runpytest("casebook_a.yaml").assert_outcomes(passed=2)
    # 本当の消し忘れは、どちらの YAML からも1回ずつ知らせる（同じ置き場所の確認なので）
    (project.path / "shared" / "old.txt").write_text("x", "utf-8")
    result = project.runpytest()
    result.assert_outcomes(passed=2, failed=2)
    result.stdout.fnmatch_lines(["*にない期待出力が*['old.txt']*"])


def test_nested_golden_dir_is_left_to_its_owner(project: pytest.Pytester) -> None:
    """a の置き場所（golden/）の中に b の置き場所があっても、二重に知らせない。"""
    _two_yamls(project, "golden", None)
    project.runpytest("--casebook-update").assert_outcomes(passed=4)
    project.runpytest().assert_outcomes(passed=4)
    (project.path / "golden" / "casebook_b" / "old.txt").write_text("x", "utf-8")
    result = project.runpytest()
    # b の確認だけが失敗する（a は b の置き場所の中を見ない）
    result.assert_outcomes(passed=3, failed=1)
    result.stdout.fnmatch_lines(["*FAILED casebook_b.yaml::golden_orphans*"])


def test_orphan_check_ignores_unreadable_siblings(project: pytest.Pytester) -> None:
    """名前がパターンに合うディレクトリや、UTF-8 でないファイルが隣にあっても止まらない。"""
    write_casebook(project, "cases:\n  - name: a\n    call: calc:add\n    args: [1, 2]\n")
    (project.path / "casebook_data.yaml").mkdir()
    (project.path / "casebook_binary.yaml").write_bytes(b"\xff\xfe\x00broken")
    project.runpytest("--casebook-update", "casebook_calc.yaml").assert_outcomes(passed=2)
    project.runpytest("casebook_calc.yaml").assert_outcomes(passed=2)


def test_expect_text_gets_the_same_replacements_as_the_output(project: pytest.Pytester) -> None:
    """
    expect の文字列と {contains} には、実際の出力と同じ置き換えを当ててから比べる
    （固定の日時を書いたのに、実際が <datetime> になって合わない、とならないように）。
    """
    write_casebook(
        project,
        rf"""
        normalize:
          - {{pattern: 'ord-\d+', replace: '<order-id>'}}
        cases:
          - name: exact
            command: [{sys.executable}, -c, "print('at 1970-01-01T00:00:00 ord-12')"]
            expect: {{stdout: "at 1970-01-01T00:00:00 ord-12"}}
          - name: contains
            command: [{sys.executable}, -c, "print('at 1970-01-01T00:00:00 ord-12')"]
            expect: {{stdout: {{contains: "1970-01-01T00:00:00 ord-99"}}}}
          - name: regex_is_left_alone
            command: [{sys.executable}, -c, "print('at 1970-01-01T00:00:00')"]
            expect: {{stdout: {{regex: '<datetime>$'}}}}
        """,
    )
    project.runpytest().assert_outcomes(passed=4)


def test_nan_matches_nan() -> None:
    assert match_value(float("nan"), float("nan"), "x") == []
    assert match_value({"v": float("nan")}, {"v": float("nan")}, "x") == []
    assert match_value(float("nan"), 1.0, "x")
