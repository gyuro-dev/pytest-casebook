"""
pytest-casebook の本体（pytest11 entry point から読み込まれる）。

- ini の `casebook_files` に合う YAML ファイルを集め、ケースごとにテストを作る
- ケースを実行し、正規化した結果を期待値と比べる。期待値は YAML の `expect:` に書くか、
  期待出力ファイルに置く（`--casebook-update` で書き直す。`--casebook-update-headers` は
  結果が同じファイルのヘッダーだけを書き直す）
- `--casebook-html` を付けると、グループの階層の表で結果を HTML に出力する
"""

from __future__ import annotations

import contextlib
import copy
import difflib
import fnmatch
import hashlib
import inspect
import itertools
import json
import os
import shlex
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from . import hookspecs
from .expect import map_strings, match_text, match_value
from .golden import (
    GoldenContent,
    comparable_text,
    golden_differs,
    parse_golden,
    read_golden,
    render,
    unified_diff,
    write_golden,
)
from .http import HttpResponse
from .messages import LANGS, MESSAGES, TEXTS, error, language
from .model import (
    DEFAULT_GOLDEN_DIR,
    DEFAULT_STATE,
    EXPECT_KEYS_BY_KIND,
    FILES_TARGET,
    ORPHANS_TEST_NAME,
    TEXT_EXPECT_KEYS,
    Case,
    CasebookDoc,
    CasebookError,
    load,
    one_line,
)
from .normalize import BUILTIN_PATTERNS, Normalizer, compile_patterns
from .report import CasebookHtmlReport
from .runner import (
    CasebookRunError,
    CommandResult,
    WorkerTimeout,
    import_callable,
    invoke,
    run_subprocess,
    run_with_timeout,
)
from .serialize import (
    compact,
    describe_exception,
    exception_name,
    render_rows,
    serialize,
    to_jsonable,
)

CASEBOOK_DIR_TOKEN = "{casebook_dir}"
DEFAULT_FILE_PATTERNS = ["casebook_*.yaml", "casebook_*.yml", "*.casebook.yaml", "*.casebook.yml"]
# ini の casebook_html_golden（HTML レポートに期待出力の内容をどれだけ出すか）の値
HTML_GOLDEN_VALUES = ("off", "summary", "full")
# 期待出力で、見出しのない本文を何として扱うか（ケースの種類 -> 既定の見出し）
DEFAULT_SECTIONS = {"command": "stdout", "call": "return", "request": "json"}

# レポートでケースを YAML に書いた順に並べるための通し番号
_order = itertools.count()
# --casebook-update / --casebook-update-headers で、
# 期待出力ファイル（normcase したパス）-> (先に使ったテストの nodeid, 結果)
_GOLDEN_OWNERS = pytest.StashKey[dict[str, tuple[str, GoldenContent]]]()


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(hookspecs)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("casebook", "pytest-casebook")
    # オプション名はすべて --casebook- で始める。--update-golden のような一般的な名前は、
    # 利用する側の conftest.py がすでに定義していることがあり、同じ名前だと pytest が起動できない。
    # ヘルプは英語で書く（pytest --help のほかの説明と同じく、既定の言語も英語のため）
    group.addoption(
        "--casebook-update",
        action="store_true",
        default=False,
        help="rewrite golden files with the current output (only those whose results changed; "
        "no comparison failures)",
    )
    group.addoption(
        "--casebook-update-headers",
        action="store_true",
        default=False,
        help="rewrite the headers (# case:, # description:, ...) of golden files whose results "
        "still match; a golden file whose results differ still fails "
        "(ignored with --casebook-update, which already rewrites what changed)",
    )
    group.addoption(
        "--casebook-html",
        metavar="PATH",
        default=None,
        help="write the case results as an HTML test specification sheet grouped by levels",
    )
    parser.addini(
        "casebook_files",
        type="linelist",
        default=DEFAULT_FILE_PATTERNS,
        help="file name patterns collected as case files",
    )
    parser.addini(
        "casebook_golden_dir",
        default=DEFAULT_GOLDEN_DIR,
        help="where golden files are stored, relative to the case file "
        "(a directory per case file name without the extension is made under it)",
    )
    parser.addini(
        "casebook_golden_description",
        type="bool",
        default=False,
        help="write the case description as a `# description:` line in golden files "
        "written by --casebook-update or --casebook-update-headers",
    )
    parser.addini(
        "casebook_levels",
        type="linelist",
        default=[],
        help="names of the group levels when the YAML has no levels "
        "(default: those of casebook_lang, e.g. Category Subcategory Item)",
    )
    parser.addini(
        "casebook_command_prefix",
        default="",
        help="arguments put before every command when the YAML has no command_prefix",
    )
    parser.addini("casebook_encoding", default="utf-8", help="encoding of the command output")
    parser.addini(
        "casebook_builtin_patterns",
        type="bool",
        default=True,
        help="replace datetimes and UUIDs with <datetime> / <uuid>",
    )
    parser.addini(
        "casebook_html_title",
        default="",
        help="title of the HTML report (default: that of casebook_lang, e.g. Test Specification)",
    )
    parser.addini(
        "casebook_html_golden",
        default="summary",
        help="how much of each golden file is shown in the HTML report "
        f"({' / '.join(HTML_GOLDEN_VALUES)})",
    )
    # addini は type="int" に対応していないので、文字列で受けて int() にする
    parser.addini(
        "casebook_html_golden_lines",
        default="40",
        help="number of lines of a golden file shown when casebook_html_golden is summary",
    )
    parser.addini(
        "casebook_lang",
        default="en",
        help=f"language of the HTML report and the messages ({' / '.join(LANGS)})",
    )


def _texts(config: pytest.Config) -> dict[str, Any]:
    """ini の casebook_lang の言語の、レポートの文言。"""
    lang = config.getini("casebook_lang")
    if lang not in TEXTS:
        raise pytest.UsageError(f"casebook_lang must be one of {' / '.join(LANGS)}: {lang}")
    return TEXTS[lang]


def _html_golden_options(config: pytest.Config) -> tuple[str, int]:
    """ini の casebook_html_golden（期待出力をどれだけ出すか）と、summary のときの行数。"""
    mode = config.getini("casebook_html_golden")
    if mode not in HTML_GOLDEN_VALUES:
        raise pytest.UsageError(
            f"casebook_html_golden must be one of {' / '.join(HTML_GOLDEN_VALUES)}: {mode}"
        )
    lines = config.getini("casebook_html_golden_lines")
    try:
        limit = int(lines)
    except ValueError:
        raise pytest.UsageError(f"casebook_html_golden_lines must be an integer: {lines}") from None
    return mode, limit


def pytest_configure(config: pytest.Config) -> None:
    texts = _texts(config)
    html = config.getoption("--casebook-html")
    if html:
        _html_golden_options(config)  # 値の誤りを、ケースを集める前に知らせる
    # pytest-xdist のワーカーでは書かない（結果はまとめ役のプロセスに集まる）
    if html and not hasattr(config, "workerinput"):
        title = config.getini("casebook_html_title") or texts["title"]
        lang = config.getini("casebook_lang")
        report = CasebookHtmlReport(Path(html).resolve(), title, lang)
        config.pluginmanager.register(report, "casebook-html-report")


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    """
    `--casebook-update`（と `--casebook-update-headers`）で書き直した期待出力ファイルの一覧を、
    実行の最後に出す。
    """
    # 書き直したテストの user_properties から、期待出力のパスの表記を集める
    # （pytest-xdist でも、ワーカーの結果はまとめ役の stats に集まる）
    labels = {
        value
        for reports in terminalreporter.stats.values()
        for report in reports
        if getattr(report, "when", None) == "call"
        for key, value in getattr(report, "user_properties", [])
        if key == "casebook_updated" and isinstance(value, str) and value
    }
    if not labels:
        return
    terminalreporter.write_sep("-", _texts(config)["updated_golden"].format(n=len(labels)))
    for label in sorted(labels):
        terminalreporter.write_line(label)


@pytest.fixture(scope="session")
def casebook_env() -> Any:
    """
    The environment for running cases. Defaults to None.

    Define a fixture with the same name in conftest.py to override it; its value is passed to
    every hook as `env`.

    ケースを実行する環境。既定は None。

    conftest.py で同じ名前の fixture を書いて上書きすると、その値が各 hook の `env` に渡る。
    """
    return None


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> pytest.Collector | None:
    patterns = parent.config.getini("casebook_files")
    if any(fnmatch.fnmatch(file_path.name, p) for p in patterns):
        return CasebookFile.from_parent(parent, path=file_path)
    return None


class CasebookItem(pytest.Function):
    """1件のケース（または期待出力の消し忘れの確認）のテスト。"""

    # ケースを書いた YAML の行（0 始まり。golden_orphans には行がない）
    casebook_line: int | None = None

    def reportinfo(self) -> tuple[Path, int, str]:
        # 行番号は None にできない（skip の報告で pytest が行番号を必要とする）。
        # ケースの YAML の行が分かれば、その行を返す（IDE やターミナルから飛べる）
        return self.path, self.casebook_line or 0, f"casebook: {self.name}"


class CasebookFile(pytest.File):
    """1つのケースファイル。"""

    def collect(self) -> Iterator[CasebookItem]:
        config = self.config
        try:
            doc = _load_doc(config, self.path)
        except CasebookError as e:
            raise self.CollectError(str(e)) from None

        file_label = Path(os.path.relpath(self.path, config.rootpath)).as_posix()
        texts = _texts(config)
        # 期待出力の内容は HTML レポートに使うときだけ読む（レポートがなければファイルを読まない）
        html_golden = ("off", 0)
        if config.getoption("--casebook-html"):
            html_golden = _html_golden_options(config)
        for case in doc.cases:
            test = _make_manual_test(case) if case.manual is not None else _make_test(doc, case)
            item = CasebookItem.from_parent(self, name=case.name, callobj=test)
            item.casebook_line = case.line
            for mark in case.marks:
                item.add_marker(mark)
            if case.skip is not None:
                item.add_marker(pytest.mark.skip(reason=case.skip))
            if case.xfail is not None:
                item.add_marker(pytest.mark.xfail(reason=case.xfail))
            if case.manual is not None:
                _mark_manual(item, case, config)
            # -k でグループ名でも絞り込めるようにする
            item.extra_keyword_matches.update(case.path)
            meta = _report_meta(doc, case, file_label, texts, *html_golden)
            item.user_properties.append(("casebook", meta))
            yield item
        if doc.check_orphans:
            yield CasebookItem.from_parent(
                self, name=ORPHANS_TEST_NAME, callobj=_make_orphan_test(doc)
            )


def _run_display(doc: CasebookDoc, case: Case) -> str:
    """レポートや期待出力に書く、実行内容の表記（手動のケースは手順）。"""
    if case.manual is not None:
        return case.manual
    if case.command is not None:
        prefix = shlex.join(doc.command_prefix)
        return f"{prefix} {case.command}" if prefix else case.command
    if case.request is not None:
        return case.request.display
    return str(case.call)


def _shorten(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _precondition_lines(doc: CasebookDoc, case: Case, texts: dict[str, Any]) -> list[str]:
    """レポートの「前提条件」の列に出す行。"""
    lines: list[str] = []
    # 既定の状態（default）は、どのケースにも出ると目立つだけなので書かない
    if doc.states is not None and case.state != DEFAULT_STATE:
        lines.append(texts["state"].format(state=case.state))
    # 状態の中身は状態名で分かるため、ケースに書いた setup: だけを出す
    own = dict(case.own_setup or {})
    files = own.pop("files", None) or {}
    if files:
        lines.append(texts["files"].format(files=", ".join(files)))
    # ファイル全体の env はどのケースにも同じなので、それと違う変数だけを出す
    env = [f"{k}={v}" for k, v in case.env.items() if doc.env.get(k) != v]
    if env:
        lines.append(_shorten(texts["env"].format(env=", ".join(env))))
    for key, value in own.items():
        lines.append(_shorten(f"{key}: {compact(to_jsonable(value))}"))
    return lines


def _expected_lines(case: Case, texts: dict[str, Any]) -> list[str]:
    """レポートの「期待結果」の列に出す行。"""
    if case.manual is not None:
        return list(case.manual_expect)
    if case.expect is None:
        # 置き場所はファイルの見出しに1回だけ出す（全行に同じパスが並ぶと読みにくいため）
        lines = [texts["golden"].format(name=case.golden_file)]
        if case.observe_targets:
            lines.append(texts["observe"].format(targets=", ".join(case.observe_targets)))
        return lines
    lines = []
    for key, value in case.expect.items():
        if key == "headers":
            # ヘッダーは1つずつ「headers.名前 …」の行にする
            lines += [_text_expect_line(f"headers.{n}", v, texts) for n, v in value.items()]
        elif key in TEXT_EXPECT_KEYS:
            lines.append(_text_expect_line(key, value, texts))
        else:
            lines.append(_shorten(f"{key} = {compact(to_jsonable(value))}"))
    return lines


def _text_expect_line(label: str, value: Any, texts: dict[str, Any]) -> str:
    """文字列の期待値（そのままの文字列 / {contains} / {regex}）を、読みやすい1行にする。"""
    if isinstance(value, dict) and len(value) == 1:
        ((matcher, pattern),) = value.items()
        how = "contains" if matcher.lstrip("$") == "contains" else "regex"
        return _shorten(texts[how].format(label=label, pattern=pattern))
    return _shorten(f"{label} = {compact(to_jsonable(value))}")


def _golden_text(doc: CasebookDoc, case: Case, mode: str, limit: int, texts: dict[str, Any]) -> str:
    """
    HTML レポートに出す、期待出力ファイルの内容（レポートで、ケースの行の下に折りたたんで出す）。

    比較と同じ、比べる部分だけを出す（`# case:` などの説明のヘッダーは出さない）。
    summary なら limit 行で打ち切り、「…（あと n 行）」を添える。ファイルがない
    （`--casebook-update` の前など）か読めなければ、空にする（エラーにしない）。
    """
    if mode == "off" or not case.uses_golden:
        return ""
    try:
        content = parse_golden(read_golden(doc.golden_path(case)), DEFAULT_SECTIONS[case.kind])
    except (OSError, ValueError):
        return ""
    text = comparable_text(content, content, content).rstrip("\n")
    if not text:
        return ""
    lines = text.split("\n")
    if mode == "summary" and len(lines) > limit:
        lines = [*lines[:limit], texts["more_lines"].format(n=len(lines) - limit)]
    return "\n".join(lines)


def _report_meta(
    doc: CasebookDoc,
    case: Case,
    file_label: str,
    texts: dict[str, Any],
    golden_mode: str,
    golden_lines: int,
) -> dict[str, Any]:
    """HTML レポート用の情報（pytest-xdist でも送れるよう、文字列・数値・リストだけにする）。"""
    return {
        "order": next(_order),
        "file": file_label,
        "title": doc.title,
        "file_description": doc.description,
        "golden_dir": Path(os.path.relpath(doc.golden_dir, doc.path.parent)).as_posix(),
        "levels": list(doc.levels),
        "path": [g.name for g in case.groups],
        "path_descriptions": [g.description for g in case.groups],
        "name": case.name,
        "description": case.description,
        "kind": case.kind,
        "run": _run_display(doc, case),
        # 手動のケースで、手で確かめた結果（result:）がまだないもの（レポートで「手動」と出す）
        "manual_pending": case.manual is not None and case.result is None,
        "precondition": _precondition_lines(doc, case, texts),
        "expected": _expected_lines(case, texts),
        # 期待出力ファイルの名前と、レポートに出すその内容（出すものがなければ空）
        "golden_name": case.golden_file if case.uses_golden else "",
        "golden_text": _golden_text(doc, case, golden_mode, golden_lines, texts),
    }


def _make_test(doc: CasebookDoc, case: Case) -> Callable[..., None]:
    """ケース1件を実行するテスト関数を作る（pytest が引数の名前で fixture を渡す）。"""

    def casebook_test(
        casebook_env: Any,
        tmp_path_factory: pytest.TempPathFactory,
        request: pytest.FixtureRequest,
    ) -> None:
        # 実行の誤り（コマンドが見つからないなど）のメッセージを、ini の言語で出す
        with language(request.config.getini("casebook_lang")):
            _run_case(request, doc, case, casebook_env, tmp_path_factory)

    return casebook_test


def _mark_manual(item: CasebookItem, case: Case, config: pytest.Config) -> None:
    """
    手動のケースを、result: がないか skipped ならスキップにする。

    マーカーで止めるので、スキップの場所には YAML の行が出る。result: がなければ、
    レポートでふつうのスキップと分けて「手動」と出すための印も付ける。
    """
    m = MESSAGES[config.getini("casebook_lang")]
    if case.result is None:
        item.add_marker(pytest.mark.skip(reason=m["manual_not_run"]))
        if case.skip is None:
            item.user_properties.append(("casebook_manual", True))
    elif case.result == "skipped":
        item.add_marker(pytest.mark.skip(reason=m["manual_skipped"]))


def _make_manual_test(case: Case) -> Callable[..., None]:
    """手動のケースのテスト関数を作る（実行はせず、result: に書いた結果にする）。"""

    def casebook_manual(request: pytest.FixtureRequest) -> None:
        if case.result == "failed":
            m = MESSAGES[request.config.getini("casebook_lang")]
            pytest.fail(m["manual_failed"].format(name=case.name), pytrace=False)

    return casebook_manual


def _load_doc(config: pytest.Config, path: Path) -> CasebookDoc:
    """ini の設定を当てて、ケースファイルを読む。"""
    _texts(config)  # casebook_lang を確かめる
    return load(
        path,
        golden_dir=path.parent / config.getini("casebook_golden_dir") / path.stem,
        levels=tuple(config.getini("casebook_levels")) or None,
        command_prefix=tuple(shlex.split(config.getini("casebook_command_prefix"))),
        lang=config.getini("casebook_lang"),
    )


def _sibling_docs(config: pytest.Config, doc: CasebookDoc) -> list[CasebookDoc]:
    """同じディレクトリにある、ほかのケースファイル（読めないものは除く）。"""
    patterns = config.getini("casebook_files")
    docs = []
    for path in sorted(doc.path.parent.iterdir()):
        if path == doc.path or not any(fnmatch.fnmatch(path.name, p) for p in patterns):
            continue
        # 名前がパターンに合うディレクトリ（casebook_data.yaml/ など）は読まない
        if not path.is_file():
            continue
        # 書き方の誤り・UTF-8 でないファイル（CasebookError）・読めないファイル（OSError）は、
        # そのファイル自身を集めるときに知らせるので、ここでは無視する
        with contextlib.suppress(CasebookError, OSError, ValueError):
            docs.append(_load_doc(config, path))
    return docs


def _find_orphans(doc: CasebookDoc, others: list[CasebookDoc]) -> list[str]:
    """
    置き場所にあるのに、どのケースも使っていない期待出力を探す。

    - 調べるのは、期待出力に使われている拡張子のファイルだけ（.txt と、golden: out.json の
      ように書いた拡張子）。置き場所に人が置いたほかのファイル（説明の .md や、.gitkeep の
      ような . で始まるファイル）を消し忘れと間違えないように
    - 同じ置き場所を使うほかの YAML（同じディレクトリのケースファイル）の期待出力も、
      使われているものとして数える（golden_dir: を共有しても、互いの期待出力を消し忘れと
      間違えない）
    - ほかの YAML の置き場所がこの置き場所の中にあるときは、その中のファイルは
      その YAML の確認に任せる（同じファイルを2回知らせない）
    - golden: sub/a.txt のようにサブディレクトリに置いたものも見る
    """
    root = doc.golden_dir.resolve()
    golden_paths = [d.golden_path(c) for d in [doc, *others] for c in d.cases if c.uses_golden]
    expected = {p.resolve() for p in golden_paths}
    suffixes = {".txt"} | {p.suffix for p in golden_paths}
    nested = [
        d.golden_dir.resolve()
        for d in others
        if d.golden_dir.resolve() != root and d.golden_dir.resolve().is_relative_to(root)
    ]
    orphans = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith(".") or p.suffix not in suffixes:
            continue
        real = p.resolve()
        if real not in expected and not any(real.is_relative_to(n) for n in nested):
            orphans.append(p.relative_to(root).as_posix())
    return sorted(orphans)


def _make_orphan_test(doc: CasebookDoc) -> Callable[..., None]:
    def golden_orphans(request: pytest.FixtureRequest) -> None:
        """ケースを消したのに期待出力だけが残っていないことを確認する。"""
        if not doc.golden_dir.is_dir():
            return
        orphans = _find_orphans(doc, _sibling_docs(request.config, doc))
        if orphans:
            message = MESSAGES[request.config.getini("casebook_lang")]["golden_orphans"]
            # ほかのメッセージと同じく、YAML のディレクトリからの相対パスで示す
            golden_dir = Path(os.path.relpath(doc.golden_dir, doc.path.parent)).as_posix()
            pytest.fail(
                message.format(yaml=doc.path.name, golden_dir=golden_dir, orphans=orphans),
                pytrace=False,
            )

    return golden_orphans


# =============================================================================
# ケースの実行
# =============================================================================


@dataclass
class _Outcome:
    """ケースを実行した結果。"""

    header: list[tuple[str, str]]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    value: Any = None
    error: BaseException | None = None
    response: HttpResponse | None = None
    observed: dict[str, Any] = field(default_factory=dict)


# run_case() が呼ぶ hook の名前 -> 最初の結果だけを使う hook（firstresult）かどうか
_HOOK_FIRSTRESULT = {
    "pytest_casebook_run_command": True,
    "pytest_casebook_request": True,
    "pytest_casebook_observe": True,
    "pytest_casebook_setup": False,
    "pytest_casebook_prepare_call": False,
    "pytest_casebook_placeholders": False,
    "pytest_casebook_patterns": False,
}


class _Hooks:
    """
    run_case() に渡された hooks を、pytest の `node.ihook` と同じ呼び方で使えるようにする。

    hooks は、hookspecs と同じ名前の関数を属性に持つオブジェクトやモジュール
    （import した conftest モジュールなど）。実行の共通部分は
    `hook.pytest_casebook_xxx(**kwargs)` と呼ぶので、その形に合わせる。

    - 関数がなければ、firstresult の hook は None、それ以外は [] を返す（pluggy の既定と同じ）
    - 関数があれば、conftest の hook と同じく、宣言した引数だけを渡して呼ぶ。
      firstresult の hook は戻り値をそのまま、それ以外は [戻り値] を返す
      （pluggy はすべてのプラグインの結果のリストを返すため。None なら [] にする）
    """

    def __init__(self, hooks: Any) -> None:
        self._hooks = hooks

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name not in _HOOK_FIRSTRESULT:
            raise AttributeError(name)
        firstresult = _HOOK_FIRSTRESULT[name]
        func = getattr(self._hooks, name, None)

        def call(**kwargs: Any) -> Any:
            if func is None:
                return None if firstresult else []
            # conftest の hook と同じく、関数が宣言した引数だけを渡す
            declared = inspect.signature(func).parameters
            value = func(**{k: v for k, v in kwargs.items() if k in declared})
            if firstresult:
                return value
            return [] if value is None else [value]

        return call


def run_case(
    doc: CasebookDoc,
    case: Case,
    *,
    env: Any = None,
    hooks: Any = None,
    encoding: str | None = None,
    builtin_patterns: bool | None = None,
    lang: str | None = None,
    description: bool | None = None,
) -> str:
    """
    Run one case and return the result as a string in the golden-file format: the same text
    that `--casebook-update` writes, with changing values already normalized. No comparison
    is made. Use it to run cases outside pytest, e.g. in a playground script with a
    `--case <name>` option.

    ```python
    import conftest  # hooks can be the imported conftest module itself
    import pytest_casebook

    doc = pytest_casebook.load("tests/casebook_demo.yaml", ini=True)
    case = next(c for c in doc.cases if c.name == "add_cli")
    print(pytest_casebook.run_case(doc, case, hooks=conftest), end="")
    ```

    An exception from a `call:` case or a non-zero exit code is not an error: as under
    pytest, it comes back inside the returned text (`----- raises -----` / `# exit_code:`).

    `encoding`, `builtin_patterns`, `lang` and `description` default to the ini options
    that `load(path, ini=True)` read (`doc.options`), and otherwise to the built-in
    defaults. Arguments given here win.

    :param doc: the case file loaded with `load()`
    :param case: a case in `doc`
    :param env: passed to every hook as `env` (what the `casebook_env` fixture provides
        under pytest)
    :param hooks: an object or module whose attributes are functions named
        `pytest_casebook_*` (e.g. an imported conftest module); as in conftest.py, each
        function receives only the parameters it declares
    :param encoding: encoding of the command output (the `casebook_encoding` ini; default
        `utf-8`)
    :param builtin_patterns: replace datetimes and UUIDs with `<datetime>` / `<uuid>`
        (the `casebook_builtin_patterns` ini; default True)
    :param lang: language of the error messages: `en` or `ja` (the `casebook_lang` ini;
        default `en`)
    :param description: write a `# description:` line when the case has a description
        (the `casebook_golden_description` ini; default False)
    :return: the result in the golden-file format (with the trailing newline)
    :raises CasebookRunError: when the case cannot be run (a manual case, a command that is
        not found, a timeout, a missing request hook, ...)
    :raises ValueError: when `lang` is not supported

    ケースを1件実行し、期待出力ファイルの形式の文字列にして返す。`--casebook-update` が
    書くものと同じ文字列で、実行ごとに変わる値は正規化済み。比較はしない。pytest の外で
    ケースを動かすとき（`--case <名前>` を持つお試しスクリプトなど）に使う。

    ```python
    import conftest  # hooks には import した conftest モジュールをそのまま渡せる
    import pytest_casebook

    doc = pytest_casebook.load("tests/casebook_demo.yaml", ini=True)
    case = next(c for c in doc.cases if c.name == "add_cli")
    print(pytest_casebook.run_case(doc, case, hooks=conftest), end="")
    ```

    call: のケースの例外や 0 以外の終了コードは誤りではなく、pytest と同じく、返す文字列の
    中に入る（`----- raises -----` / `# exit_code:`）。

    `encoding`・`builtin_patterns`・`lang`・`description` は、省略すると
    `load(path, ini=True)` で読んだ ini の値（`doc.options`）を使い、なければ組み込みの
    既定を使う。ここで渡した引数が優先する。

    :param doc: `load()` で読んだケースファイル
    :param case: `doc` の中のケース
    :param env: 各 hook に `env` として渡す値（pytest では `casebook_env` fixture が渡すもの）
    :param hooks: `pytest_casebook_*` という名前の関数を属性に持つオブジェクトやモジュール
        （import した conftest モジュールなど）。conftest.py と同じく、各関数には宣言した
        引数だけが渡る
    :param encoding: command の出力の文字コード（ini の `casebook_encoding`。既定は `utf-8`）
    :param builtin_patterns: 日時と UUID を `<datetime>` / `<uuid>` に置き換えるか
        （ini の `casebook_builtin_patterns`。既定は True）
    :param lang: 実行の誤りのメッセージの言語。`en` か `ja`
        （ini の `casebook_lang`。既定は `en`）
    :param description: ケースに description があれば `# description:` の行を書く
        （ini の `casebook_golden_description`。既定は False）
    :return: 期待出力ファイルの形式の文字列（末尾の改行を含む）
    :raises CasebookRunError: ケースを実行できないとき（手動のケース、コマンドが見つからない、
        時間切れ、request hook がない、など）
    :raises ValueError: `lang` が対応していない言語のとき
    """
    # 引数 > load(ini=True) で読んだ ini の値 > 組み込みの既定
    options = doc.options
    if encoding is None:
        encoding = str(options.get("encoding", "utf-8"))
    if builtin_patterns is None:
        builtin_patterns = bool(options.get("builtin_patterns", True))
    if lang is None:
        lang = str(options.get("lang", "en"))
    if description is None:
        description = bool(options.get("description", False))
    if lang not in TEXTS:
        raise ValueError(f"lang must be one of {' / '.join(LANGS)}: {lang}")
    with language(lang):
        if case.manual is not None:
            raise CasebookRunError(error("manual_not_runnable", name=case.name))
        hook = _Hooks(hooks)
        # 作業ディレクトリは、正規化（そのパスを <tmp> に置き換える）が終わるまで消さない
        with contextlib.ExitStack() as stack:
            workdir: Path | None = None
            if case.needs_workdir:
                tmp = stack.enter_context(tempfile.TemporaryDirectory())
                # あとから resolve() しても変わらないよう、作った直後に resolve しておく
                # （Windows の 8.3 形式のパスや macOS の /var の symlink で変わりうる）
                workdir = Path(tmp).resolve()
            outcome = _execute_case(doc, case, env, hook, workdir, None, encoding)
            normalizer = _normalizer(None, hook, doc, env, workdir, builtin_patterns)
            return _render_golden(case, outcome, normalizer, description)


def _run_case(
    request: pytest.FixtureRequest,
    doc: CasebookDoc,
    case: Case,
    env: Any,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """
    ケースを実行して期待値と比べる。

    実行（_execute_case）が済んだら、expect: があればそれと、なければ期待出力ファイルと比べる。
    """
    config = request.config
    # このケースの YAML のパスに効く conftest.py の hook だけを呼ぶ
    # （config.hook は、ほかのディレクトリの conftest.py の hook も呼ぶ）
    hook = request.node.ihook
    workdir: Path | None = None
    run_error: str | None = None
    try:
        if case.needs_workdir:
            workdir = tmp_path_factory.mktemp(f"casebook-{case.name}")
        outcome = _execute_case(
            doc, case, env, hook, workdir, config, config.getini("casebook_encoding")
        )
    except CasebookRunError as e:
        run_error = str(e)
    # 失敗にするのは except の外で（中で pytest.fail を呼ぶと、元の例外もつながって表示され、
    # 同じメッセージが2回出る）
    if run_error is not None:
        pytest.fail(f"[{case.name}] {run_error}", pytrace=False)

    normalizer = _normalizer(
        config, hook, doc, env, workdir, config.getini("casebook_builtin_patterns")
    )
    lang = config.getini("casebook_lang")
    if case.uses_golden:
        _compare_golden(request, doc, case, outcome, normalizer, lang)
    else:
        _compare_expect(case, outcome, normalizer, lang)


def _execute_case(
    doc: CasebookDoc,
    case: Case,
    env: Any,
    hook: Any,
    workdir: Path | None,
    config: pytest.Config | None,
    encoding: str,
) -> _Outcome:
    """
    ケースを実行して結果を返す（pytest のテストと run_case() で共通の部分）。

    1. 作業ディレクトリ（要るケースでは作って渡される）に files を置く
       （状態とケースの setup: の両方）
    2. 状態とケースの setup: を重ねた内容で準備をする（pytest_casebook_setup hook）
    3. command を実行する、関数を呼ぶ、または request を送る
    4. observe の対象を取り出す
    5. 後片付けをする（2 で返されたコンテキストマネージャを抜ける）

    :raises CasebookRunError: 実行できないとき（コマンドが見つからないなど）
    """
    with contextlib.ExitStack() as stack:
        if workdir is not None:
            _write_files(workdir, case.setup_files)
        # setup: がないケースでも呼ぶ（data は空）。後片付けが毎回行われ、
        # 前のケースで増えた DB の行などが次のケースに残らないようにするため
        for cm in hook.pytest_casebook_setup(
            case=case,
            data=copy.deepcopy(case.setup or {}),
            env=env,
            workdir=workdir,
            config=config,
        ):
            if cm is not None:
                stack.enter_context(cm)
        if case.command is not None:
            outcome = _execute_command(config, hook, doc, case, env, workdir, encoding)
        elif case.request is not None:
            outcome = _execute_request(config, hook, case, env, workdir)
        else:
            outcome = _execute_call(config, hook, doc, case, env, workdir)
        for target in case.observe_targets:
            outcome.observed[target] = _observe(config, hook, case, target, env, workdir)

    if doc.states is not None:
        # 実行内容（command / call / request と引数）のあと、結果（exit_code / status）の前に置く
        keys = [key for key, _ in outcome.header]
        results = [i for i, key in enumerate(keys) if key in ("exit_code", "status")]
        index = results[0] if results else len(keys)
        outcome.header.insert(index, ("state", case.state))
    return outcome


def _write_files(workdir: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = workdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _in_dir(workdir: Path | None) -> contextlib.AbstractContextManager[Any]:
    """作業ディレクトリがあれば、その中に移動する。"""
    return contextlib.chdir(workdir) if workdir is not None else contextlib.nullcontext()


def _execute_command(
    config: pytest.Config | None,
    hook: Any,
    doc: CasebookDoc,
    case: Case,
    env: Any,
    workdir: Path | None,
    encoding: str,
) -> _Outcome:
    # {casebook_dir} は YAML のあるディレクトリ（作業ディレクトリで実行するときに、
    # YAML の隣のスクリプトなどを指すのに使う）
    yaml_dir = doc.path.parent.as_posix()
    argv = [
        arg.replace(CASEBOOK_DIR_TOKEN, yaml_dir)
        for arg in [*doc.command_prefix, *(case.command_argv or ())]
    ]
    cwd = workdir or doc.path.parent
    with _in_dir(workdir):
        # hook にはケースをそのまま渡す（stdin_file に対応する実装は、hook の中で自分で読む）
        result = hook.pytest_casebook_run_command(
            case=case, argv=argv, env=env, cwd=cwd, config=config
        )
    if result is None:
        stdin = case.stdin
        if case.stdin_file is not None:
            try:
                stdin = (doc.path.parent / case.stdin_file).read_text(encoding="utf-8")
            except OSError:
                raise CasebookRunError(error("stdin_file_missing", name=case.stdin_file)) from None
        result = run_subprocess(
            argv,
            cwd=cwd,
            stdin=stdin,
            timeout=case.timeout,
            encoding=encoding,
            # argv と同じく、env の値の中の {casebook_dir} も YAML のディレクトリにする
            env={k: v.replace(CASEBOOK_DIR_TOKEN, yaml_dir) for k, v in case.env.items()},
        )
    elif not isinstance(result, CommandResult):
        result = CommandResult(*result)
    return _Outcome(
        header=[("command", _run_display(doc, case)), ("exit_code", str(result.exit_code))],
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _execute_call(
    config: pytest.Config | None,
    hook: Any,
    doc: CasebookDoc,
    case: Case,
    env: Any,
    workdir: Path | None,
) -> _Outcome:
    # YAML と同じディレクトリのモジュールを、conftest.py なしで import できるようにする
    # （pytest がテストのファイルのディレクトリを sys.path に加えるのと同じ）
    yaml_dir = str(doc.path.parent)
    if yaml_dir not in sys.path:
        sys.path.insert(0, yaml_dir)
    func = import_callable(str(case.call))
    args = copy.deepcopy(case.args)
    kwargs = copy.deepcopy(case.kwargs)
    hook.pytest_casebook_prepare_call(
        case=case, env=env, args=args, kwargs=kwargs, workdir=workdir, config=config
    )
    with _in_dir(workdir):
        try:
            result = invoke(func, args, kwargs, timeout=case.timeout)
        except WorkerTimeout:
            raise CasebookRunError(
                error("call_timeout", timeout=case.timeout, call=case.call)
            ) from None

    header = [("call", str(case.call))]
    if case.args:
        header.append(("args", json.dumps(case.args, ensure_ascii=False, default=repr)))
    if case.kwargs:
        header.append(("kwargs", json.dumps(case.kwargs, ensure_ascii=False, default=repr)))
    return _Outcome(
        header=header,
        stdout=result.stdout,
        stderr=result.stderr,
        value=result.value,
        error=result.error,
    )


def _execute_request(
    config: pytest.Config | None, hook: Any, case: Case, env: Any, workdir: Path | None
) -> _Outcome:
    request = case.request
    assert request is not None

    def send() -> Any:
        return hook.pytest_casebook_request(
            case=case, request=request, env=env, workdir=workdir, config=config
        )

    with _in_dir(workdir):
        if case.timeout is None:
            response = send()
        else:
            # 時間内に返らなければケースを失敗にする（hook は止められず、裏で動き続ける）
            try:
                response = run_with_timeout(send, case.timeout)
            except WorkerTimeout:
                raise CasebookRunError(
                    error("request_timeout", timeout=case.timeout, request=request.display)
                ) from None
    if response is None:
        raise CasebookRunError(error("no_request_hook"))
    if not isinstance(response, HttpResponse):
        raise CasebookRunError(error("bad_response", type=type(response).__name__))
    return _Outcome(
        header=[("request", request.display), ("status", str(response.status))],
        response=response,
    )


def _observe(
    config: pytest.Config | None, hook: Any, case: Case, target: str, env: Any, workdir: Path | None
) -> Any:
    """observe の対象を取り出す（files は作業ディレクトリを読み、ほかは hook に任せる）。"""
    if target == FILES_TARGET:
        assert workdir is not None
        return {
            p.relative_to(workdir).as_posix(): _read_observed_file(p)
            for p in sorted(workdir.rglob("*"))
            if p.is_file()
        }
    value = hook.pytest_casebook_observe(
        target=target, case=case, env=env, workdir=workdir, config=config
    )
    if value is None:
        message = error("observe_failed", target=target)
        # expect: の結果のキーの打ち間違い（retrun など）は、observe の対象として扱われてここに来る
        close = difflib.get_close_matches(target, EXPECT_KEYS_BY_KIND.get(case.kind, ()), n=1)
        if close:
            message += error("did_you_mean", key=close[0])
        raise CasebookRunError(message)
    return value


def _read_observed_file(path: Path) -> str:
    """
    observe の files で読むファイルの中身。

    UTF-8 で読めないファイル（画像など）は、大きさと SHA-256 の1行にする。置換文字で
    読んでしまうと、違うバイト列が同じ置換文字になり、中身が変わっても気づけないため。
    """
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}>"
    # 改行は LF にそろえる（Windows のプログラムが書く CRLF で期待出力が変わらないように）
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _render_observed(target: str, value: Any, no_files: str = MESSAGES["en"]["no_files"]) -> str:
    """
    observe で取り出した値の表記（1件を1行にする）。

    期待出力ファイルには、言語の設定によらず `(no files)` を書く
    （言語を変えただけで期待出力が変わらないように）。
    """
    if target == FILES_TARGET:
        if not value:
            return no_files
        return "\n".join(f"=== {name} ===\n{text.rstrip()}" for name, text in value.items())
    return render_rows(value)


# =============================================================================
# 期待値との比較
# =============================================================================


def _render_golden(case: Case, outcome: _Outcome, normalizer: Normalizer, description: bool) -> str:
    """
    実行した結果を、正規化して期待出力の形式の文字列にする
    （pytest の比較・更新と run_case() で共通の部分）。

    :param description: ケースに description があれば、`# case:` の直後に
        `# description:` の行を書く（ini の casebook_golden_description）
    """
    sections: list[tuple[str, str]] = []
    if outcome.response is not None:
        # JSON の本文は整形して書き、それ以外はそのまま書く
        is_json, value = outcome.response.parse_json()
        sections.append(("json", serialize(value)) if is_json else ("body", outcome.response.body))
    elif case.command is not None:
        sections.append(("stdout", outcome.stdout))
    elif outcome.error is not None:
        sections.append(("raises", describe_exception(outcome.error)))
    else:
        sections.append(("return", serialize(outcome.value)))
    if case.command is None and outcome.stdout.strip():
        sections.append(("stdout", outcome.stdout))
    if outcome.stderr.strip():
        sections.append(("stderr", outcome.stderr))
    for target, value in outcome.observed.items():
        sections.append((f"observe: {target}", _render_observed(target, value)))

    header = [(key, normalizer(value)) for key, value in outcome.header]
    if description and case.description:
        # description は出力ではなく YAML に書いたものなので、正規化はせず1行にだけする
        header.insert(0, ("description", one_line(case.description)))
    return render(case, header, [(title, normalizer(body)) for title, body in sections])


def _compare_golden(
    request: pytest.FixtureRequest,
    doc: CasebookDoc,
    case: Case,
    outcome: _Outcome,
    normalizer: Normalizer,
    lang: str,
) -> None:
    """
    期待出力ファイルと比べる（`--casebook-update` のときは期待出力を書き直す）。

    `--casebook-update-headers` のときは、ふつうに比べて、結果が同じファイルだけを
    今の形（ヘッダーを含む）で書き直す。
    """
    config = request.config
    m = MESSAGES[lang]
    actual = _render_golden(case, outcome, normalizer, config.getini("casebook_golden_description"))
    path = doc.golden_path(case)
    label = Path(os.path.relpath(path, doc.path.parent)).as_posix()
    # 比べるのは結果だけ（# case: などの説明のヘッダーは比べない）
    default_section = DEFAULT_SECTIONS[case.kind]
    got = parse_golden(actual, default_section)
    expected = parse_golden(read_golden(path), default_section) if path.exists() else None
    if config.getoption("--casebook-update"):
        _claim_golden(request, case, path, label, got, m)
        # 結果が同じなら書き直さない（手で書いた期待出力の書き方を崩さず、
        # ヘッダーだけの違いで差分が出ないようにする）
        if (expected is None or golden_differs(expected, got)) and write_golden(path, actual):
            _record_update(request, path, _result_changes(expected, got))
        # 書かなかったときも読み直す（同じファイルを使う前のケースが書いていることがある）
        _refresh_report_golden(request, doc, case)
        return
    if expected is None:
        pytest.fail(m["golden_missing"].format(name=case.name, label=label), pytrace=False)
    if golden_differs(expected, got):
        diff = unified_diff(
            comparable_text(expected, expected, got),
            comparable_text(got, expected, got),
            label,
            lang,
        )
        pytest.fail(f"{_title(case, lang)}\n{m['golden_differs']}\n{diff}", pytrace=False)
    # --casebook-update-headers: 結果が同じなので、ヘッダーを今の形にそろえる。
    # 比べるのは結果だけなので、ヘッダーを省いて手で書いた期待出力も、ここで
    # --casebook-update が書くのと同じ形（# case: などを含む）に書き直される。
    # 同じファイルを使うほかのケースが先に書いていれば書かない（# case: の違いで、
    # ケースごとに書き直し合わないように）
    if (
        config.getoption("--casebook-update-headers")
        and _claim_golden(request, case, path, label, got, m)
        and write_golden(path, actual)
    ):
        _record_update(request, path, "")


def _refresh_report_golden(request: pytest.FixtureRequest, doc: CasebookDoc, case: Case) -> None:
    """
    HTML レポートに出す期待出力の内容を、書き直したあとのものにする。

    内容は集めるときに読んでいるので、`--casebook-update` で作った・書き直した
    期待出力は、ここで読み直さないとレポートに出ない（または古いまま出る）。
    """
    config = request.config
    if not config.getoption("--casebook-html"):
        return
    meta = dict(request.node.user_properties).get("casebook")
    if isinstance(meta, dict):
        meta["golden_text"] = _golden_text(doc, case, *_html_golden_options(config), _texts(config))


def _claim_golden(
    request: pytest.FixtureRequest,
    case: Case,
    path: Path,
    label: str,
    got: GoldenContent,
    m: dict[str, str],
) -> bool:
    """
    期待出力ファイルを書く前に、同じファイルを使うほかのケースと結果が食い違わないか確かめる。

    同じ期待出力ファイルを使う2つのケースの結果が違うと、あとのケースが黙って上書きし、
    次の実行で先のケースが失敗する。golden: で同じファイルを指したときや、Windows で
    大文字小文字だけが違うケース名（Add と add）のときに起きる。食い違えば失敗にする。

    :return: このケースが、そのファイルを最初に使ったケースなら True
    """
    owners = request.config.stash.setdefault(_GOLDEN_OWNERS, {})
    nodeid: str = request.node.nodeid
    owner = owners.setdefault(os.path.normcase(path.resolve()), (nodeid, got))
    if owner[0] != nodeid and golden_differs(owner[1], got):
        pytest.fail(
            m["golden_shared"].format(name=case.name, label=label, other=owner[0]),
            pytrace=False,
        )
    return owner[0] == nodeid


def _result_changes(expected: GoldenContent | None, got: GoldenContent) -> str:
    """
    書き直す期待出力の、結果のヘッダー（exit_code / status）の変わり方の注記
    （` (exit_code 0 → 2)` の形。変わっていなければ空）。

    0 で終わっていたコマンドが失敗するようになったのに、それが新しい期待出力として
    黙って書かれるのを、一覧で目立たせるため。古いファイルに書いていないキーは、
    比べていなかったので注記しない。新しい結果から消えたキーは `-` と書く。

    新しいファイルは、失敗の結果（0 でない exit_code・400 以上の status・raises）を
    持つときだけ ` (new, exit_code 1)` のように注記する（初回にまとめて作るときに、
    失敗した結果が期待として残るのに気づけるように）。
    """
    if expected is None:
        notable = [
            f"{key} {value}"
            for key, value in got.results.items()
            if (key == "exit_code" and value != "0") or (key == "status" and int(value) >= 400)
        ]
        if "raises" in got.sections:
            notable.append("raises")
        return f" (new, {', '.join(notable)})" if notable else ""
    changes = [
        f"{key} {old} → {got.results.get(key, '-')}"
        for key, old in expected.results.items()
        if got.results.get(key) != old
    ]
    return f" ({', '.join(changes)})" if changes else ""


def _record_update(request: pytest.FixtureRequest, path: Path, note: str) -> None:
    """
    期待出力を書き直したことを、テストの user_properties に残す。

    値は rootdir からのパスの表記に注記を添えたもの（実行の最後の一覧に出す。HTML レポートは
    真偽しか見ないので、空でない文字列でも「更新」と出る）。
    """
    updated = Path(os.path.relpath(path, request.config.rootpath)).as_posix()
    request.node.user_properties.append(("casebook_updated", updated + note))


def _is_instance_of(error: BaseException, name: str) -> bool:
    """
    例外が `name` の型（またはそれを継承した型）かどうか。

    `name` は `ValueError` のような型名、`Outer.Inner` のようなクラスの中の名前、
    `mypkg.errors.MyError` のようなモジュール名付きの名前のどれでもよい。
    """
    name = name.strip()
    return any(
        name in (cls.__name__, cls.__qualname__, f"{cls.__module__}.{cls.__qualname__}")
        for cls in type(error).__mro__
    )


def _match_raises(expected: Any, error: BaseException, described: str, lang: str) -> list[str]:
    """
    raises の期待値と比べる。

    - `"型名"`: その型か、それを継承した型の例外なら一致
    - `"型名: メッセージ"`: 型は上と同じ比べ方で、メッセージは完全一致
    - `{contains: ...}` / `{regex: ...}`: `実際の型名: メッセージ` の文字列と比べる
    """
    if not isinstance(expected, str):
        return match_text(expected, described, "raises", lang)
    type_name, has_message, message = expected.partition(":")
    mismatch = [
        MESSAGES[lang]["mismatch"].format(
            label="raises", expected=compact(expected), actual=compact(described)
        )
    ]
    if not _is_instance_of(error, type_name):
        return mismatch
    if has_message:
        # describe_exception() と同じ型名（Outer.Inner など）で、メッセージの部分を取り出す
        prefix = f"{exception_name(error)}: "
        actual_message = described[len(prefix) :] if described.startswith(prefix) else ""
        if message.strip() != actual_message.strip():
            return mismatch
    return []


def _match_response(
    expect: dict[str, Any],
    response: HttpResponse,
    normalizer: Normalizer,
    value_of: Callable[[Any], Any],
    shown: list[tuple[str, str]],
    lang: str,
) -> list[str]:
    """
    request のケースの expect（status・json・body・headers）と比べる。

    違いが見つかった値は、失敗の説明に添えるため `shown` に (名前, 表記) を足す。
    """
    m = MESSAGES[lang]
    problems: list[str] = []
    if "status" in expect and expect["status"] != response.status:
        problems.append(
            m["mismatch"].format(label="status", expected=expect["status"], actual=response.status)
        )
    if "json" in expect:
        is_json, value = response.parse_json()
        if not is_json:
            body = compact(normalizer.replace(response.body))
            problems.append(m["not_json"].format(body=body))
        else:
            actual = value_of(value)
            found = match_value(expect["json"], actual, "json", lang)
            if found:
                problems += found
                shown.append(("json", serialize(actual)))
    if "body" in expect:
        expected_body = _normalized_expect(expect["body"], normalizer)
        problems += match_text(expected_body, normalizer(response.body), "body", lang)
    # ヘッダー名は大文字小文字を区別しない
    headers = {name.lower(): value for name, value in response.headers.items()}
    for name, expected in (expect.get("headers") or {}).items():
        if name.lower() not in headers:
            problems.append(m["missing_header"].format(name=name))
        else:
            actual_header = normalizer(headers[name.lower()])
            expected = _normalized_expect(expected, normalizer)
            problems += match_text(expected, actual_header, f"headers.{name}", lang)
    return problems


def _normalized_expect(expected: Any, normalizer: Normalizer) -> Any:
    """
    文字列の期待値（そのままの文字列と {contains}）に、実際の出力と同じ置き換えを当てる。

    実際の出力は比べる前に正規化される（日時は `<datetime>` になるなど）ので、YAML に
    `stdout: "1970-01-01T00:00:00"` のように書いた固定の値も同じ形にしないと、
    「期待 "1970-01-01T00:00:00" / 実際 "<datetime>"」で合わなくなる。
    {regex} は正規表現そのものなので触らない。
    """
    if isinstance(expected, str):
        return normalizer.replace(expected)
    if isinstance(expected, dict):
        ((matcher, pattern),) = expected.items()
        if matcher.lstrip("$") == "contains":
            return {matcher: normalizer.replace(pattern)}
    return expected


def _compare_expect(case: Case, outcome: _Outcome, normalizer: Normalizer, lang: str) -> None:
    """YAML の expect: に書いた期待値と比べる。"""
    m = MESSAGES[lang]
    expect = case.expect or {}
    problems: list[str] = []
    shown: list[tuple[str, str]] = []

    def value_of(raw: Any) -> Any:
        return map_strings(to_jsonable(raw), normalizer.replace)

    if "exit_code" in expect and expect["exit_code"] != outcome.exit_code:
        problems.append(
            m["mismatch"].format(
                label="exit_code", expected=expect["exit_code"], actual=outcome.exit_code
            )
        )
    for key in ("stdout", "stderr"):
        if key in expect:
            expected = _normalized_expect(expect[key], normalizer)
            problems += match_text(expected, normalizer(getattr(outcome, key)), key, lang)

    if outcome.response is not None:
        problems += _match_response(expect, outcome.response, normalizer, value_of, shown, lang)
    elif case.command is None:
        if outcome.error is not None:
            described = normalizer(describe_exception(outcome.error))
            if "raises" in expect:
                problems += _match_raises(expect["raises"], outcome.error, described, lang)
            else:
                problems.append(m["raised"].format(described=described))
        elif "raises" in expect:
            returned = compact(value_of(outcome.value))
            problems.append(m["not_raised"].format(returned=returned))
        elif "return" in expect:
            actual = value_of(outcome.value)
            found = match_value(expect["return"], actual, "return", lang)
            if found:
                problems += found
                shown.append(("return", render_rows(actual)))

    for target in case.observe_targets:
        if target not in expect:
            continue
        actual = value_of(outcome.observed[target])
        found = match_value(expect[target], actual, target, lang)
        if found:
            problems += found
            shown.append((target, _render_observed(target, actual, m["no_files"])))

    if problems:
        lines = "\n".join("  - " + p.replace("\n", "\n    ") for p in problems)
        details = "".join(
            f"\n{m['actual_section'].format(name=name)}\n{text}" for name, text in shown
        )
        pytest.fail(f"{_title(case, lang)}\n{m['expect_differs']}\n{lines}{details}", pytrace=False)


def _title(case: Case, lang: str) -> str:
    """失敗の説明の1行目（ケース名・グループ・確認内容）。"""
    where = MESSAGES[lang]["line"].format(line=case.line + 1) if case.line is not None else ""
    parts = [f"[{case.name}]{where}", " > ".join(case.path), one_line(case.description)]
    return " ".join(p for p in parts if p)


def _normalizer(
    config: pytest.Config | None,
    hook: Any,
    doc: CasebookDoc,
    env: Any,
    workdir: Path | None,
    builtin_patterns: bool,
) -> Normalizer:
    """
    このケースの出力の正規化を組み立てる。

    置き換えは、hook の placeholders・作業ディレクトリと YAML のディレクトリのパス、
    正規表現は、hook の patterns・YAML の normalize:・組み込みの日時と UUID の順に当てる。
    """
    placeholders = [
        pair
        for pairs in hook.pytest_casebook_placeholders(env=env, config=config)
        for pair in pairs
    ]
    if workdir is not None:
        # 作業ディレクトリのパスは実行ごとに変わるため <tmp> にする
        for path in {workdir, workdir.resolve()}:
            placeholders += [(str(path), "<tmp>"), (path.as_posix(), "<tmp>")]
    # YAML のディレクトリのパスは、置く場所（人や CI）によって変わるため {casebook_dir} にする
    for path in {doc.path.parent, doc.path.parent.resolve()}:
        placeholders += [(str(path), CASEBOOK_DIR_TOKEN), (path.as_posix(), CASEBOOK_DIR_TOKEN)]
    # 実際の値が "." や空のものは使わない。load() は絶対パスにするが、parse_document に
    # 相対パスを渡されると YAML のディレクトリが "." になり、出力のすべての "." が
    # {casebook_dir} に置き換わってしまう（空文字は、すべての文字の間に入ってしまう）
    placeholders = [(real, token) for real, token in placeholders if real not in ("", ".")]
    patterns = compile_patterns(
        pair for pairs in hook.pytest_casebook_patterns(env=env, config=config) for pair in pairs
    )
    patterns += doc.normalize
    if builtin_patterns:
        patterns += BUILTIN_PATTERNS
    return Normalizer(placeholders, patterns)
