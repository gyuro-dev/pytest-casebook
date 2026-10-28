"""
meta:（利用する側が自由に使う情報）・env:（環境変数）の受け継ぎ・load()・オプション名の衝突の確認。
"""

from __future__ import annotations

import json
import os
import re
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
    # 受け継いだ env は、call のケースにも同じように重なる（実行の間 os.environ に当たる）
    assert env["func"] == {"A": "file", "B": "group"}


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


def test_env_applies_to_call_and_request_cases(project: pytest.Pytester) -> None:
    """env: は call / request のケースにも書け、実行の間 os.environ に重なる（あとで元に戻る）。"""
    project.makeconftest(
        """
        import os

        from pytest_casebook import HttpResponse

        def pytest_casebook_request(request):
            return HttpResponse(200, os.environ.get("CASEBOOK_T", "unset"), {})
        """
    )
    write_casebook(
        project,
        """
        env: {CASEBOOK_T: file}
        cases:
          - {name: func, call: "os:getenv", args: [CASEBOOK_T], expect: {return: file}}
          - {name: own, call: "os:getenv", args: [CASEBOOK_T], env: {CASEBOOK_T: case},
             expect: {return: case}}
          - {name: removed, call: "os:getenv", args: [CASEBOOK_T], env: {CASEBOOK_T: null},
             expect: {return: null}}
          - {name: api, request: /x, env: {CASEBOOK_T: api}, expect: {status: 200, body: api}}
        """,
    )
    assert "CASEBOOK_T" not in os.environ
    project.runpytest().assert_outcomes(passed=5)  # 5 つ目は golden_orphans
    assert "CASEBOOK_T" not in os.environ


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


PARAMS_CASEBOOK = """\
cases:
  - name: shipping
    description: 送料の計算
    call: shop:shipping
    params:
      - {name: "0", args: [0], expect: {return: 500}}
      - {name: "2999", description: 2999 円は送料 500 円, args: [2999], expect: {return: 500}}
      - {name: "3000", description: 3000 円から送料無料, args: [3000], expect: {return: 0}}
"""


def test_params_expands_a_template_into_cases(tmp_path: Path) -> None:
    """params の要素ごとに1件のケースになり、要素のキーがテンプレートを丸ごと上書きする。"""
    path = tmp_path / "casebook_params.yaml"
    path.write_text(PARAMS_CASEBOOK, encoding="utf-8")
    doc = pytest_casebook.load(path)
    # 名前は <テンプレート名>-<要素名> で、要素の順に並ぶ
    assert [c.name for c in doc.cases] == ["shipping-0", "shipping-2999", "shipping-3000"]
    # description は、要素に書けば置き換わり、書かなければテンプレートの値を受け継ぐ
    assert [c.description for c in doc.cases] == [
        "送料の計算",
        "2999 円は送料 500 円",
        "3000 円から送料無料",
    ]
    assert all(c.call == "shop:shipping" for c in doc.cases)
    assert [c.args for c in doc.cases] == [[0], [2999], [3000]]
    # 深い併合はせず、要素の expect がテンプレートの expect 全体を置き換える
    assert [c.expect for c in doc.cases] == [{"return": 500}, {"return": 500}, {"return": 0}]
    # 行番号は、テンプレートではなく要素自身の行（0 から数える）
    assert [c.line for c in doc.cases] == [5, 6, 7]


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


@pytest.mark.parametrize(
    ("text", "message"),
    [
        # 空白だけの command は、区切ると引数が1つもない
        ("cases:\n  - {name: a, command: '   '}\n", "command is empty"),
        # クォートの閉じ忘れは、実行の前に YAML の誤りにする
        ('cases:\n  - {name: a, command: "add \'apple"}\n', "cannot split command into"),
        ('command_prefix: "store \'a"\ncases: []\n', "cannot split command_prefix into"),
        # call: のモジュール名・関数名の空・空白・相対 import
        ("cases:\n  - {name: a, call: ':f'}\n", "call must be 'module:function'"),
        ("cases:\n  - {name: a, call: 'm:'}\n", "call must be 'module:function'"),
        ("cases:\n  - {name: a, call: '.m:f'}\n", "call must be 'module:function'"),
        ("cases:\n  - {name: a, call: 'm : f'}\n", "call must be 'module:function'"),
        # 偽になる不正な値（[]・""・false）を省略と取り違えない
        ("cases:\n  - {name: a, call: 'm:f', setup: {files: []}}\n", "setup.files must be"),
        ("cases:\n  - {name: a, call: 'm:f', setup: {files: false}}\n", "setup.files must be"),
        ("cases:\n  - {name: a, request: {path: /x, query: []}}\n", "request.query must be"),
        ("cases:\n  - {name: a, request: {path: /x, query: ''}}\n", "request.query must be"),
        ("cases:\n  - {name: a, call: 'm:f', state: ''}\n", "state must be a string"),
        ("cases:\n  - {name: a, call: 'm:f', state: null}\n", "state must be a string"),
        ("cases:\n  - {name: a, call: 'm:f', golden: ''}\n", "golden must be a string"),
        (
            "cases:\n  - group: g\n    state: ''\n    cases: [{name: a, call: 'm:f'}]\n",
            "state must be a string",
        ),
    ],
)
def test_load_rejects_edge_cases(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "casebook_x.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(pytest_casebook.CasebookError, match=re.escape(message)):
        pytest_casebook.load(path)


def test_setup_files_can_be_empty(tmp_path: Path) -> None:
    """files: の下を空（null）にしたときは、置くファイルがないだけ。"""
    path = tmp_path / "casebook_x.yaml"
    path.write_text("cases:\n  - name: a\n    call: m:f\n    setup:\n      files:\n", "utf-8")
    assert pytest_casebook.load(path).cases[0].setup_files == {}


def test_params_errors_point_to_the_element(tmp_path: Path) -> None:
    """params の要素の誤りは、テンプレートではなく要素の行を出す。"""
    path = tmp_path / "casebook_x.yaml"
    path.write_text(
        "cases:\n  - name: t\n    call: m:f\n    params:\n      - {name: a}\n      - {nam: b}\n",
        encoding="utf-8",
    )
    with pytest.raises(pytest_casebook.CasebookError, match=r"cases\[0\] \(line 6\).*needs a name"):
        pytest_casebook.load(path)


def test_load_reports_a_file_that_is_not_utf8(project: pytest.Pytester) -> None:
    """UTF-8 でない（Shift_JIS などで保存した）ファイルは、集めるときの誤りとして知らせる。"""
    path = project.path / "casebook_sjis.yaml"
    path.write_bytes("cases:\n  - {name: 足し算, call: 'calc:add'}\n".encode("cp932"))
    with pytest.raises(pytest_casebook.CasebookError, match="cannot read as UTF-8"):
        pytest_casebook.load(path)
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*casebook_sjis.yaml: UTF-8 で読めません*"])
    result.stdout.no_fnmatch_line("*Traceback*")


def test_load_makes_a_relative_golden_dir_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "casebook_x.yaml"
    path.write_text("cases:\n  - {name: a, call: 'm:f'}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    doc = pytest_casebook.load(path, golden_dir="g")
    assert doc.golden_dir == tmp_path / "g"


def test_string_command_is_split_when_loading(tmp_path: Path) -> None:
    """文字列の command: は読み込みのときに引数に区切る（実行のときに区切り直さない）。"""
    path = tmp_path / "casebook_x.yaml"
    path.write_text(
        "cases:\n  - {name: a, command: \"add 'red apple' --n=2\"}\n"
        "  - {name: b, command: [add, 'red apple']}\n",
        encoding="utf-8",
    )
    doc = pytest_casebook.load(path)
    assert doc.cases[0].command_argv == ("add", "red apple", "--n=2")
    assert doc.cases[1].command_argv == ("add", "red apple")
    assert doc.cases[1].command == "add 'red apple'"
