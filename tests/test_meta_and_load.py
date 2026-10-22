"""meta:（利用する側が自由に使う情報）・load()・オプション名の衝突の確認。"""

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
    with pytest.raises(pytest_casebook.CasebookError, match="YAML として読めません"):
        pytest_casebook.load(broken)
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text("cases:\n  - name: a\n", encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match="command・call・request のどれか1つ"):
        pytest_casebook.load(wrong)
    # "false" のような文字列を True と取り違えない
    quoted = tmp_path / "quoted.yaml"
    quoted.write_text("check_orphans: 'false'\ncases: []\n", encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match="check_orphans は true か false"):
        pytest_casebook.load(quoted)


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
