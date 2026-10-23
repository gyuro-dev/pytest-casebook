"""
meta:（利用する側が自由に使う情報）・env:（環境変数）の受け継ぎ・load()・オプション名の衝突の確認。
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from helpers import write_casebook

import pytest_casebook

META_CASEBOOK = """
meta: {owner: qa}
cases:
  - group: 外側
    meta: {demo: false, area: route}
    cases:
      - group: 内側
        meta: {demo: true}
        cases:
          - name: inner
            call: calc:add
            args: [1, 2]
            meta: {moto_only: true}
  - name: plain
    call: calc:add
    args: [1, 2]
"""


def test_meta_is_merged_from_groups_and_passed_to_hooks(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import json
        from pathlib import Path

        def pytest_casebook_prepare_call(case):
            with Path("meta.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"name": case.name, "meta": case.meta}) + "\\n")
        """
    )
    write_casebook(project, META_CASEBOOK)
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    lines = (project.path / "meta.jsonl").read_text(encoding="utf-8").splitlines()
    seen = {d["name"]: d["meta"] for d in map(json.loads, lines)}
    # 外側のグループの meta に、内側のグループ・ケースの meta を上書きで重ねる
    assert seen == {
        "inner": {"demo": True, "area": "route", "moto_only": True},
        "plain": {},
    }


def test_invalid_meta(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: a\n    call: calc:add\n    meta: [1]\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*meta は キー -> 値 のマッピングで書いてください*"])


ENV_CASEBOOK = """
env: {A: file, B: file, C: file}
cases:
  - group: g
    env: {B: group, C: null}
    cases:
      - name: inner
        command: x
        env: {A: case, N: 1, R: 0.5}
      - name: func
        call: calc:add
  - name: top
    command: x
"""


def test_env_is_merged_from_file_groups_and_cases(tmp_path: Path) -> None:
    path = tmp_path / "casebook_env.yaml"
    path.write_text(textwrap.dedent(ENV_CASEBOOK), encoding="utf-8")
    doc = pytest_casebook.load(path)
    env = {c.name: c.env for c in doc.cases}
    assert doc.env == {"A": "file", "B": "file", "C": "file"}
    # 内側が外側を上書きし、null で外側の変数を消す。数値は文字列にする
    assert env["inner"] == {"A": "case", "B": "group", "N": "1", "R": "0.5"}
    assert env["top"] == {"A": "file", "B": "file", "C": "file"}
    # 受け継いだ env は command 以外のケースでは使わない（誤りにもしない）
    assert env["func"] == {}


@pytest.mark.parametrize(
    "env",
    ["[A=1]", "{A: true}", "{A: [1]}", "{A: {b: 1}}", "{'A=B': x}", "{'': x}", "x"],
)
def test_invalid_env(project: pytest.Pytester, env: str) -> None:
    write_casebook(project, f"cases:\n  - name: a\n    command: x\n    env: {env}\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        ["*env は 変数名 -> 値（文字列か数値*のマッピングで書いてください*"]
    )


def test_env_on_call_case_is_an_error(project: pytest.Pytester) -> None:
    write_casebook(project, "cases:\n  - name: a\n    call: calc:add\n    env: {A: x}\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*env は command のケースにだけ書けます*"])


def test_load_reads_the_same_yaml_outside_pytest(tmp_path: Path) -> None:
    path = tmp_path / "casebook_demo.yaml"
    path.write_text(textwrap.dedent(META_CASEBOOK), encoding="utf-8")

    doc = pytest_casebook.load(path)
    assert doc.meta == {"owner": "qa"}
    assert [c.name for c in doc.cases] == ["inner", "plain"]
    assert [c.name for c in doc.cases if c.meta.get("demo")] == ["inner"]
    assert doc.cases[0].path == ("外側", "内側")
    # 期待出力の置き場所は pytest の既定と同じ
    assert doc.golden_path(doc.cases[0]) == tmp_path / "golden" / "casebook_demo" / "inner.txt"


def test_load_reports_errors(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("cases: [\n", encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match="cannot read as YAML"):
        pytest_casebook.load(broken)
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text("cases:\n  - name: a\n", encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match="exactly one of command, call"):
        pytest_casebook.load(wrong)
    # lang で日本語のメッセージにできる
    with pytest.raises(
        pytest_casebook.CasebookError, match="command・call・request・manual のどれか1つ"
    ):
        pytest_casebook.load(wrong, lang="ja")
    # "false" のような文字列を True と取り違えない
    quoted = tmp_path / "quoted.yaml"
    quoted.write_text("check_orphans: 'false'\ncases: []\n", encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match="check_orphans must be true or false"):
        pytest_casebook.load(quoted)
    with pytest.raises(ValueError, match="lang must be one of"):
        pytest_casebook.load(quoted, lang="fr")


def test_load_levels_follow_lang(tmp_path: Path) -> None:
    """levels を書かなければ、階層の呼び名は lang の言語の既定になる。"""
    path = tmp_path / "casebook_x.yaml"
    path.write_text("cases:\n  - {name: a, call: 'm:f'}\n", encoding="utf-8")
    assert pytest_casebook.load(path).levels == ("Category", "Subcategory", "Item")
    assert pytest_casebook.load(path, lang="ja").levels == ("大項目", "中項目", "小項目")
    assert pytest_casebook.load(path, levels=("A",)).levels == ("A",)


def test_project_can_keep_its_own_update_golden_option(project: pytest.Pytester) -> None:
    """利用する側が --update-golden を定義していても起動できる（名前がぶつからない）。"""
    project.makeconftest(
        """
        def pytest_addoption(parser):
            parser.addoption("--update-golden", action="store_true", default=False)
        """
    )
    write_casebook(project, "cases:\n  - name: add\n    call: calc:add\n    args: [1, 2]\n")
    project.runpytest("--update-golden").assert_outcomes(passed=1, failed=1)
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
