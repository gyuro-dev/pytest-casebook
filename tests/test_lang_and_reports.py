"""
YAML の先頭の `lang:`（ファイルごとの言語）と、ini の casebook_html_reports
（1 回の実行で表を分ける）の確認。

project fixture の ini は casebook_lang = ja なので、`lang: en` を書いたファイルだけが英語になる。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from helpers import write_casebook

import pytest_casebook

EN_CASES = """
lang: en
states:
  default: {}
  empty: {}
cases:
  - group: Arithmetic
    cases:
      - {name: add, call: "calc:add", args: [1, 2], state: empty}
      - {name: div, call: "calc:divide", args: [1, 0], expect: {raises: {$contains: zero}}}
"""

JA_CASES = """
cases:
  - group: 計算
    cases:
      - {name: add, call: "calc:add", args: [1, 2]}
"""


def _write(project: pytest.Pytester, name: str, text: str) -> Path:
    return write_casebook(project, text, name=name)


# =============================================================================
# YAML の lang:
# =============================================================================


def test_lang_in_yaml_overrides_the_ini_for_that_file(project: pytest.Pytester) -> None:
    """lang: en のファイルは、ini が ja でも、比較の失敗のメッセージが英語になる。"""
    _write(project, "casebook_en", EN_CASES)
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update").assert_outcomes(passed=5)
    # 両方の期待出力を壊して、失敗のメッセージの言語を見る
    for stem in ("casebook_en", "casebook_ja"):
        path = project.path / "golden" / stem / "add.txt"
        path.write_text(path.read_text(encoding="utf-8").replace("3", "4"), encoding="utf-8")
    result = project.runpytest()
    result.assert_outcomes(passed=3, failed=2)
    out = result.stdout.str()
    assert "casebook_en.yaml::add" in out
    assert "The output differs from the golden file" in out
    assert "出力が期待と異なります" in out


def test_lang_in_yaml_applies_to_run_errors_and_manual_cases(project: pytest.Pytester) -> None:
    """実行の誤りと手動のケースのメッセージも、ファイルの言語になる。"""
    _write(
        project,
        "casebook_en",
        """
        lang: en
        cases:
          - {name: missing, command: no-such-command-xyz}
          - {name: check, manual: look at the screen}
          - {name: bad, manual: look again, result: failed}
        """,
    )
    result = project.runpytest("-rs")
    result.assert_outcomes(passed=1, failed=2, skipped=1)  # passed は unused_golden_files
    out = result.stdout.str()
    assert "command not found: no-such-command-xyz (it ran in " in out
    assert "manual case (no result: yet)" in out
    assert "[bad] the manual check result is failed" in out


def test_lang_in_yaml_applies_to_yaml_errors(project: pytest.Pytester) -> None:
    """lang: を書いたファイルは、書き方の誤りもその言語で知らせる。"""
    _write(project, "casebook_en", "lang: en\ncases:\n  - {name: a}\n")
    result = project.runpytest()
    result.stdout.fnmatch_lines(["*write exactly one of command, call, request and manual*"])


def test_lang_must_be_a_known_language(project: pytest.Pytester) -> None:
    _write(project, "casebook_x", "lang: fr\ncases:\n  - {name: a, call: 'calc:add'}\n")
    result = project.runpytest()
    result.stdout.fnmatch_lines(["*casebook_x.yaml: lang は ja / en のどれかで書いてください*"])


def test_default_levels_follow_the_file_language(project: pytest.Pytester) -> None:
    """levels を書かない lang: en のファイルは、階層の呼び名も英語の既定になる。"""
    _write(project, "casebook_en", EN_CASES)
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}").assert_outcomes(passed=3)
    page = report.read_text(encoding="utf-8")
    assert "<th class='level'>Category</th>" in page
    assert "State: empty" in page


def test_load_and_run_case_use_the_file_language(tmp_path: Path) -> None:
    """load() の doc.lang は YAML の lang:。run_case() の既定の言語もそれになる。"""
    path = tmp_path / "casebook_t.yaml"
    path.write_text(
        textwrap.dedent(
            """
            lang: ja
            cases:
              - {name: check, manual: 画面を見る}
            """
        ),
        encoding="utf-8",
    )
    doc = pytest_casebook.load(path)
    assert doc.lang == "ja"
    assert pytest_casebook.load(path, lang="en").lang == "ja"  # YAML が優先
    with pytest.raises(pytest_casebook.CasebookRunError, match="手動のケースは実行できません"):
        pytest_casebook.run_case(doc, doc.cases[0])
    with pytest.raises(pytest_casebook.CasebookRunError, match="a manual case cannot be run"):
        pytest_casebook.run_case(doc, doc.cases[0], lang="en")  # 引数が優先


def test_load_without_lang_in_yaml_keeps_the_given_language(tmp_path: Path) -> None:
    path = tmp_path / "casebook_t.yaml"
    path.write_text("cases:\n  - {name: a, call: 'm:f'}\n", encoding="utf-8")
    assert pytest_casebook.load(path).lang == "en"
    assert pytest_casebook.load(path, lang="ja").lang == "ja"


# =============================================================================
# 表の枠の言語（--casebook-html）
# =============================================================================


def test_report_frame_follows_the_files_when_they_agree(project: pytest.Pytester) -> None:
    """入ったファイルの言語がそろっていれば、ini が ja でも枠は英語になる。"""
    _write(project, "casebook_en", EN_CASES)
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    result = project.runpytest(f"--casebook-html={report}")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*Test specification (HTML):*report.html*"])
    page = report.read_text(encoding="utf-8")
    assert '<html lang="en">' in page
    assert "<h1>Test Specification</h1>" in page
    assert "<th>Preconditions</th>" in page


def test_report_frame_uses_the_ini_language_when_files_mix(project: pytest.Pytester) -> None:
    """言語の違うファイルが混ざった表の枠は、ini の言語（行の文言はファイルごと）。"""
    _write(project, "casebook_en", EN_CASES)
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    result = project.runpytest(f"--casebook-html={report}")
    result.assert_outcomes(passed=5)
    result.stdout.fnmatch_lines(["*試験項目表（HTML）:*report.html*"])
    page = report.read_text(encoding="utf-8")
    assert '<html lang="ja">' in page
    assert "<th>前提条件</th>" in page
    # 行の文言はファイルの言語（英語のファイルの状態の行は英語、階層の呼び名も）
    assert "State: empty" in page
    assert "<th class='level'>Category</th>" in page
    assert "<th class='level'>大項目</th>" in page


# =============================================================================
# ini の casebook_html_reports（1 回の実行で表を分ける）
# =============================================================================


def _ini(project: pytest.Pytester, *reports: str) -> None:
    lines = "\n".join(f"    {r}" for r in reports)
    project.makeini(
        f"[pytest]\npythonpath = .\ncasebook_lang = ja\ncasebook_html_reports =\n{lines}\n"
    )


def test_html_reports_write_one_sheet_per_line(project: pytest.Pytester) -> None:
    """ini の 1 行ごとに、合うファイルのケースだけを入れた HTML を、その言語の枠で書く。"""
    _write(project, "casebook_en", EN_CASES)
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/en.html = casebook_en.yaml", "reports/ja.html = *_ja.yaml")
    result = project.runpytest()
    result.assert_outcomes(passed=5)
    result.stdout.fnmatch_lines(
        ["*Test specification (HTML):*reports*en.html*", "*試験項目表（HTML）:*reports*ja.html*"]
    )
    en = (project.path / "reports" / "en.html").read_text(encoding="utf-8")
    ja = (project.path / "reports" / "ja.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in en
    assert "casebook_en.yaml" in en
    assert "casebook_ja.yaml" not in en
    assert '<html lang="ja">' in ja
    assert "casebook_ja.yaml" in ja
    assert "casebook_en.yaml" not in ja
    assert "2 cases in total" in en
    assert "全 1 件" in ja


def test_html_reports_and_the_whole_sheet_together(project: pytest.Pytester) -> None:
    """--casebook-html の全体の表は、追加の表とは別に、どのファイルも入れて書く。"""
    _write(project, "casebook_en", EN_CASES)
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/en.html = casebook_en.yaml")
    whole = project.path / "all.html"
    result = project.runpytest(f"--casebook-html={whole}")
    result.assert_outcomes(passed=5)
    page = whole.read_text(encoding="utf-8")
    assert "casebook_en.yaml" in page
    assert "casebook_ja.yaml" in page
    assert (project.path / "reports" / "en.html").is_file()
    # 知らせは全体の表が先
    out = result.stdout.str()
    assert out.index("all.html") < out.index("en.html")


def test_html_reports_accept_directory_globs(project: pytest.Pytester) -> None:
    """`customer/**/*.yaml` のように、ディレクトリごとに表を分けられる。"""
    sub = project.path / "customer" / "shop"
    sub.mkdir(parents=True)
    (sub / "casebook_shop.yaml").write_text(textwrap.dedent(JA_CASES), encoding="utf-8")
    _write(project, "casebook_dev", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/customer/index.html = customer/**/*.yaml")
    project.runpytest().assert_outcomes(passed=4)
    page = (project.path / "reports" / "customer" / "index.html").read_text(encoding="utf-8")
    assert "customer/shop/casebook_shop.yaml" in page
    assert "casebook_dev.yaml" not in page


def test_html_reports_skip_a_sheet_with_no_cases(project: pytest.Pytester) -> None:
    """合うファイルがない（綴りの誤りなど）か、絞り込みで空になった表は書かず、知らせる。"""
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/none.html = casebook_typo.yaml", "reports/ja.html = casebook_ja.yaml")
    result = project.runpytest("-k", "nothing_matches")
    result.stdout.fnmatch_lines(
        [
            "*試験項目表（HTML）:*none.html は書きませんでした（入るケースがありません）*",
            "*試験項目表（HTML）:*ja.html は書きませんでした（入るケースがありません）*",
        ]
    )
    assert not (project.path / "reports").exists()


def test_html_reports_with_collect_only(project: pytest.Pytester) -> None:
    """--collect-only の「未実施」の表も、分けて書ける。"""
    _write(project, "casebook_en", EN_CASES)
    _ini(project, "reports/en.html = casebook_en.yaml")
    project.runpytest("--collect-only")
    page = (project.path / "reports" / "en.html").read_text(encoding="utf-8")
    assert '<span class="badge notrun">Not run 2</span>' in page


def test_html_reports_can_be_turned_off_on_the_command_line(project: pytest.Pytester) -> None:
    """-o casebook_html_reports= で、ini の追加の表を出さずに実行できる（実 AWS の実行など）。"""
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/ja.html = casebook_ja.yaml")
    result = project.runpytest("-o", "casebook_html_reports=")
    result.assert_outcomes(passed=2)
    assert "試験項目表" not in result.stdout.str()
    assert not (project.path / "reports").exists()


@pytest.mark.parametrize(
    "line",
    ["reports/x.html", "= casebook_ja.yaml", "reports/x.html =", "reports/x.html = , "],
)
def test_html_reports_line_must_have_a_path_and_patterns(
    project: pytest.Pytester, line: str
) -> None:
    _write(project, "casebook_ja", JA_CASES)
    _ini(project, line)
    result = project.runpytest()
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        ["*casebook_html_reports: each line must be '<html file> = <case file patterns>'*"]
    )


def test_html_reports_patterns_must_be_relative(project: pytest.Pytester) -> None:
    _write(project, "casebook_ja", JA_CASES)
    _ini(project, f"reports/x.html = {project.path.as_posix()}/casebook_ja.yaml")
    result = project.runpytest()
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*casebook_html_reports: patterns must be relative to rootdir*"])


def test_html_reports_check_the_golden_option_early(project: pytest.Pytester) -> None:
    """追加の表だけのときも、casebook_html_golden の誤りはケースを集める前に知らせる。"""
    _write(project, "casebook_ja", JA_CASES)
    project.makeini(
        "[pytest]\npythonpath = .\ncasebook_html_golden = lots\n"
        "casebook_html_reports =\n    reports/ja.html = casebook_ja.yaml\n"
    )
    result = project.runpytest()
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*casebook_html_golden must be one of*"])


def test_html_reports_under_xdist(project: pytest.Pytester) -> None:
    """pytest-xdist で分けて実行しても、追加の表はまとめ役が 1 回だけ書く。"""
    pytest.importorskip("xdist")
    _write(project, "casebook_en", EN_CASES)
    _write(project, "casebook_ja", JA_CASES)
    project.runpytest("--casebook-update")
    _ini(project, "reports/en.html = casebook_en.yaml", "reports/ja.html = casebook_ja.yaml")
    result = project.runpytest("-n", "2")
    result.assert_outcomes(passed=5)
    en = (project.path / "reports" / "en.html").read_text(encoding="utf-8")
    assert "2 cases in total" in en
    assert '<span class="badge passed">Passed 2</span>' in en


# =============================================================================
# ブラウザのタブの題名と、使われていない期待出力
# =============================================================================


def test_page_title_names_the_only_case_file(project: pytest.Pytester) -> None:
    """
    表に入ったケースファイルが 1 つだけなら、タブの題名（<title>）をそのファイルの title: にする。

    見出し（<h1>）は今までどおり。ファイルが 2 つ以上か、ini の casebook_html_title があれば、
    タブの題名も今までどおり。
    """
    _write(
        project,
        "casebook_a",
        "title: 注文の画面\ncases:\n  - {name: a, call: calc:add, args: [1, 2]}\n",
    )
    _write(project, "casebook_b", "cases:\n  - {name: b, call: calc:add, args: [2, 2]}\n")
    _ini(project, "reports/a.html = casebook_a.yaml", "reports/all.html = casebook_*.yaml")
    project.runpytest("--casebook-update")
    page = (project.path / "reports" / "a.html").read_text(encoding="utf-8")
    assert "<title>注文の画面 - 試験項目表</title>" in page
    assert "<h1>試験項目表</h1>" in page
    page = (project.path / "reports" / "all.html").read_text(encoding="utf-8")
    assert "<title>試験項目表</title>" in page

    project.runpytest("-o", "casebook_html_title=受け入れ試験")
    page = (project.path / "reports" / "a.html").read_text(encoding="utf-8")
    assert "<title>受け入れ試験</title>" in page


def test_unused_golden_files_are_shown_in_the_report(project: pytest.Pytester) -> None:
    """
    unused_golden_files のテストは表の行にしないが、失敗したら、そのファイルの節に
    使われていない期待出力ファイルを出す（表だけを見ても、残っていることが分かるように）。
    """
    _write(project, "casebook_a", "cases:\n  - {name: a, call: calc:add, args: [1, 2]}\n")
    project.runpytest("--casebook-update")
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}").assert_outcomes(passed=2)
    page = report.read_text(encoding="utf-8")
    assert "どのケースにも使われていない期待出力ファイル" not in page
    assert "unused_golden_files" not in page

    (project.path / "golden" / "casebook_a" / "old.txt").write_text("3\n", encoding="utf-8")
    result = project.runpytest(f"--casebook-html={report}")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*FAILED casebook_a.yaml::unused_golden_files*"])
    page = report.read_text(encoding="utf-8")
    assert "<h3>どのケースにも使われていない期待出力ファイル</h3>" in page
    assert "<li>old.txt</li>" in page
    assert "1 件" in page  # 件数には入れない

    project.runpytest("-o", "casebook_lang=en", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert "<h3>Golden files not used by any case</h3>" in page
    assert "使われていない" not in page
