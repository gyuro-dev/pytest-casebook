"""
手動のケース（manual:）の確認。実行せず、result: に書いた結果をレポートと pytest の結果にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import write_casebook

import pytest_casebook

CASES = """
cases:
  - group: 印刷
    env: {CASEBOOK_M: group}   # 実行する auto だけが受け継ぐ（手動のケースには効かない）
    cases:
      - name: layout
        description: 印刷しても表が崩れない
        manual: |
          印刷プレビューを開く
          罫線がページをまたいで途切れていないか目で確かめる
        expect: [2ページ目の先頭にも見出し行が出る, 罫線が途切れない]
      - name: checked
        manual: 帳票の合計を電卓で確かめる
        expect: 合計が一致する
        result: passed
      - name: broken
        manual: ロゴの色を確かめる
        result: failed
      - name: later
        manual: 実機で確かめる
        result: skipped
      - name: auto
        call: calc:add
        args: [1, 2]
        expect: {return: 3}
"""


def test_manual_cases_are_not_run(project: pytest.Pytester) -> None:
    """result: がなければスキップ、passed / failed / skipped はそのとおりの結果にする。"""
    write_casebook(project, CASES)
    result = project.runpytest("-rs", "--casebook-update")
    # passed: checked・auto・unused_golden_files、skipped: layout・later
    result.assert_outcomes(passed=3, failed=1, skipped=2)
    result.stdout.fnmatch_lines(
        [
            "*[[]broken[]] 手動で確かめた結果が failed です*",
            "*手動のケース（result: がまだありません）*",
            "*手動の確認を行っていません（result: skipped）*",
        ]
    )
    # 手動のケースは期待出力ファイルを作らない
    assert not (project.path / "golden").exists()


def test_manual_cases_in_html_report(project: pytest.Pytester) -> None:
    """レポートには手順と期待結果を出し、結果のないものは「手動」と出す。"""
    write_casebook(project, CASES)
    report = project.path / "report.html"
    project.runpytest(f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert '<span class="badge manual">手動</span>' in page
    assert "<div class='steps'>手動: 印刷プレビューを開く\n罫線がページを" in page
    assert "<div class='line'>2ページ目の先頭にも見出し行が出る</div>" in page
    assert "<div class='line'>合計が一致する</div>" in page
    assert 'data-outcome="manual"' in page  # 絞り込みのボタン
    assert " ms</td>" in page  # 自動のケース（auto）だけに時間が出る
    assert page.count(" ms</td>") == 1
    # 手動のケースのスキップの理由は、バッジで分かるので出さない
    assert "result: がまだありません" not in page
    # グループの env: は、実行する auto の前提条件にだけ出る（手動のケースは受け継がない）
    assert page.count("<div class='line'>環境変数: CASEBOOK_M=group</div>") == 1


def test_manual_cases_do_not_inherit_env(tmp_path: Path) -> None:
    """手動のケースは実行しないので、timeout と同じく外側の env: を受け継がない。"""
    path = tmp_path / "casebook_m.yaml"
    path.write_text(CASES, encoding="utf-8")
    env = {c.name: c.env for c in pytest_casebook.load(path).cases}
    assert env["auto"] == {"CASEBOOK_M": "group"}
    assert env["layout"] == {}
    assert env["checked"] == {}


def test_plan_report_shows_manual(project: pytest.Pytester) -> None:
    """
    `--collect-only` の計画の表でも、result: のない手動のケースは「未実施」ではなく「手動」。

    実行しても手動のままなので、「これから実行する」ように見せない。result: を書いたものと
    自動のケースは「未実施」のまま。
    """
    write_casebook(project, CASES)
    report = project.path / "report.html"
    project.runpytest("--collect-only", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    # 手動 2 件（layout と broken ... broken は result があるので未実施）→ layout だけが手動
    assert page.count('<span class="badge manual">手動</span>') == 1
    assert page.count('class="badge notrun"') >= 1
    assert "data-outcome='manual'" in page


def test_manual_case_in_english(project: pytest.Pytester) -> None:
    write_casebook(project, CASES)
    report = project.path / "report.html"
    project.runpytest("-o", "casebook_lang=en", f"--casebook-html={report}")
    page = report.read_text(encoding="utf-8")
    assert '<span class="badge manual">Manual</span>' in page
    assert "<div class='steps'>Manual: " in page


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "cases:\n  - name: a\n    manual: x\n    call: m:f\n",
            "command・call・request・manual のどれか1つ",
        ),
        ("cases:\n  - name: a\n    manual: ''\n", "manual は文字列"),
        ("cases:\n  - name: a\n    manual: x\n    golden: a.txt\n", "manual のケースには golden"),
        ("cases:\n  - name: a\n    manual: x\n    expect: {stdout: x}\n", "文字列か文字列のリスト"),
        ("cases:\n  - name: a\n    manual: x\n    result: ok\n", "passed / failed / skipped"),
        ("cases:\n  - name: a\n    call: m:f\n    result: passed\n", "result は manual のケース"),
    ],
)
def test_invalid_manual_case(project: pytest.Pytester, text: str, message: str) -> None:
    write_casebook(project, text)
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*{message}*"])


def test_load_manual_case(tmp_path: Path) -> None:
    path = tmp_path / "casebook_manual.yaml"
    path.write_text(
        "cases:\n  - name: a\n    manual: 目で見る\n    expect: 崩れない\n    result: passed\n",
        encoding="utf-8",
    )
    (case,) = pytest_casebook.load(path).cases
    assert case.kind == "manual"
    assert case.manual == "目で見る"
    assert case.manual_expect == ("崩れない",)
    assert case.result == "passed"
    assert case.expect is None
    assert not case.uses_golden
