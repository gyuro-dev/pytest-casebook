"""
pytest-casebook の本体（pytest11 entry point から読み込まれる）。

- ini の `casebook_files` に合う YAML ファイルを集め、ケースごとにテストを作る
- ケースを実行し、正規化した結果を期待値と比べる。期待値は YAML の `expect:` に書くか、
  期待出力ファイルに置く（`--casebook-update` で書き直す）
- `--casebook-html` を付けると、グループの階層の表で結果を HTML に出力する
"""

from __future__ import annotations

import contextlib
import copy
import fnmatch
import itertools
import json
import os
import shlex
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from . import hookspecs
from .expect import map_strings, match_text, match_value
from .golden import (
    comparable_text,
    golden_differs,
    parse_golden,
    read_golden,
    render,
    unified_diff,
    write_golden,
)
from .http import HttpResponse
from .messages import LANGS, MESSAGES, TEXTS
from .model import (
    DEFAULT_GOLDEN_DIR,
    DEFAULT_STATE,
    FILES_TARGET,
    TEXT_EXPECT_KEYS,
    Case,
    CasebookDoc,
    CasebookError,
    load,
    one_line,
)
from .normalize import BUILTIN_PATTERNS, Normalizer, compile_patterns
from .report import CasebookHtmlReport
from .runner import CasebookRunError, CommandResult, import_callable, invoke, run_subprocess
from .serialize import compact, describe_exception, render_rows, serialize, to_jsonable

CASEBOOK_DIR_TOKEN = "{casebook_dir}"
DEFAULT_FILE_PATTERNS = ["casebook_*.yaml", "casebook_*.yml", "*.casebook.yaml", "*.casebook.yml"]

# レポートでケースを YAML に書いた順に並べるための通し番号
_order = itertools.count()


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(hookspecs)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("casebook", "pytest-casebook")
    # オプション名はすべて --casebook- で始める。--update-golden のような一般的な名前は、
    # 利用する側の conftest.py がすでに定義していることがあり、同じ名前だと pytest が起動できない
    group.addoption(
        "--casebook-update",
        action="store_true",
        default=False,
        help="期待出力ファイルを今の出力で書き直す（結果が変わったものだけ。比較で失敗にはしない）",
    )
    group.addoption(
        "--casebook-html",
        metavar="PATH",
        default=None,
        help="ケースの結果を、グループの階層の表で HTML に出力する",
    )
    parser.addini(
        "casebook_files",
        type="linelist",
        default=DEFAULT_FILE_PATTERNS,
        help="ケースファイルとして集めるファイル名のパターン",
    )
    parser.addini(
        "casebook_golden_dir",
        default=DEFAULT_GOLDEN_DIR,
        help="期待出力の置き場所（ケースファイルからの相対パス。その下にケースファイル名（拡張子なし）ごとの"
        "ディレクトリを作る）",
    )
    parser.addini(
        "casebook_levels",
        type="linelist",
        default=[],
        help="グループの階層の呼び名（YAML の levels がないときに使う。省略時は"
        " casebook_lang の言語の既定。ja なら 大項目 中項目 小項目）",
    )
    parser.addini(
        "casebook_command_prefix",
        default="",
        help="command の前に付ける引数（YAML の command_prefix がないときに使う）",
    )
    parser.addini("casebook_encoding", default="utf-8", help="command の出力の文字コード")
    parser.addini(
        "casebook_builtin_patterns",
        type="bool",
        default=True,
        help="日時と UUID を <datetime> / <uuid> に置き換える",
    )
    parser.addini(
        "casebook_html_title",
        default="",
        help="HTML レポートの題名（省略時は casebook_lang の言語の既定。ja なら 試験項目表）",
    )
    parser.addini(
        "casebook_lang",
        default="ja",
        help=f"HTML レポートと、比較の失敗のメッセージの言語（{' / '.join(LANGS)}）",
    )


def _texts(config: pytest.Config) -> dict[str, Any]:
    """ini の casebook_lang の言語の、レポートの文言。"""
    lang = config.getini("casebook_lang")
    if lang not in TEXTS:
        raise pytest.UsageError(
            f"casebook_lang は {' / '.join(LANGS)} のどれかにしてください: {lang}"
        )
    return TEXTS[lang]


def pytest_configure(config: pytest.Config) -> None:
    texts = _texts(config)
    html = config.getoption("--casebook-html")
    # pytest-xdist のワーカーでは書かない（結果はまとめ役のプロセスに集まる）
    if html and not hasattr(config, "workerinput"):
        title = config.getini("casebook_html_title") or texts["title"]
        lang = config.getini("casebook_lang")
        report = CasebookHtmlReport(Path(html).resolve(), title, lang)
        config.pluginmanager.register(report, "casebook-html-report")


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
        for case in doc.cases:
            item = CasebookItem.from_parent(self, name=case.name, callobj=_make_test(doc, case))
            item.casebook_line = case.line
            for mark in case.marks:
                item.add_marker(mark)
            if case.skip is not None:
                item.add_marker(pytest.mark.skip(reason=case.skip))
            if case.xfail is not None:
                item.add_marker(pytest.mark.xfail(reason=case.xfail))
            # -k でグループ名でも絞り込めるようにする
            item.extra_keyword_matches.update(case.path)
            meta = _report_meta(doc, case, file_label, texts)
            item.user_properties.append(("casebook", meta))
            yield item
        if doc.check_orphans:
            yield CasebookItem.from_parent(
                self, name="golden_orphans", callobj=_make_orphan_test(doc)
            )


def _run_display(doc: CasebookDoc, case: Case) -> str:
    """レポートや期待出力に書く、実行内容の表記。"""
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
    for key, value in own.items():
        lines.append(_shorten(f"{key}: {compact(to_jsonable(value))}"))
    return lines


def _expected_lines(case: Case, texts: dict[str, Any]) -> list[str]:
    """レポートの「期待結果」の列に出す行。"""
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


def _report_meta(
    doc: CasebookDoc, case: Case, file_label: str, texts: dict[str, Any]
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
        "precondition": _precondition_lines(doc, case, texts),
        "expected": _expected_lines(case, texts),
    }


def _make_test(doc: CasebookDoc, case: Case) -> Callable[..., None]:
    """ケース1件を実行するテスト関数を作る（pytest が引数の名前で fixture を渡す）。"""

    def casebook_test(
        casebook_env: Any,
        tmp_path_factory: pytest.TempPathFactory,
        request: pytest.FixtureRequest,
    ) -> None:
        _run_case(request, doc, case, casebook_env, tmp_path_factory)

    return casebook_test


def _load_doc(config: pytest.Config, path: Path) -> CasebookDoc:
    """ini の設定を当てて、ケースファイルを読む。"""
    return load(
        path,
        golden_dir=path.parent / config.getini("casebook_golden_dir") / path.stem,
        levels=tuple(config.getini("casebook_levels") or _texts(config)["levels"]),
        command_prefix=tuple(shlex.split(config.getini("casebook_command_prefix"))),
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
        # 書き方の誤り・読めないファイル（OSError）・UTF-8 でないファイル（ValueError）は、
        # そのファイル自身を集めるときに知らせるので、ここでは無視する
        with contextlib.suppress(CasebookError, OSError, ValueError):
            docs.append(_load_doc(config, path))
    return docs


def _find_orphans(doc: CasebookDoc, others: list[CasebookDoc]) -> list[str]:
    """
    置き場所にある .txt のうち、どのケースも使っていない期待出力を探す
    （golden: で別の拡張子にしたものは見ない）。

    - 同じ置き場所を使うほかの YAML（同じディレクトリのケースファイル）の期待出力も、
      使われているものとして数える（golden_dir: を共有しても、互いの期待出力を消し忘れと
      間違えない）
    - ほかの YAML の置き場所がこの置き場所の中にあるときは、その中のファイルは
      その YAML の確認に任せる（同じファイルを2回知らせない）
    - golden: sub/a.txt のようにサブディレクトリに置いたものも見る
    """
    root = doc.golden_dir.resolve()
    expected = {
        d.golden_path(c).resolve() for d in [doc, *others] for c in d.cases if c.uses_golden
    }
    nested = [
        d.golden_dir.resolve()
        for d in others
        if d.golden_dir.resolve() != root and d.golden_dir.resolve().is_relative_to(root)
    ]
    return sorted(
        p.relative_to(doc.golden_dir).as_posix()
        for p in doc.golden_dir.rglob("*.txt")
        if p.resolve() not in expected and not any(p.resolve().is_relative_to(n) for n in nested)
    )


def _make_orphan_test(doc: CasebookDoc) -> Callable[..., None]:
    def golden_orphans(request: pytest.FixtureRequest) -> None:
        """ケースを消したのに期待出力だけが残っていないことを確認する。"""
        if not doc.golden_dir.is_dir():
            return
        orphans = _find_orphans(doc, _sibling_docs(request.config, doc))
        if orphans:
            message = MESSAGES[request.config.getini("casebook_lang")]["golden_orphans"]
            pytest.fail(
                message.format(yaml=doc.path.name, golden_dir=doc.golden_dir, orphans=orphans),
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


def _run_case(
    request: pytest.FixtureRequest,
    doc: CasebookDoc,
    case: Case,
    env: Any,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """
    ケースを実行して期待値と比べる。

    1. 作業ディレクトリが要るケースでは、それを作り、files（状態とケースの setup: の両方）を置く
    2. 状態とケースの setup: を重ねた内容で準備をする（pytest_casebook_setup hook）
    3. command を実行する、関数を呼ぶ、または request を送る
    4. observe の対象を取り出す
    5. 後片付けをする（2 で返されたコンテキストマネージャを抜ける）
    6. expect: があればそれと、なければ期待出力ファイルと比べる
    """
    config = request.config
    # このケースの YAML のパスに効く conftest.py の hook だけを呼ぶ
    # （config.hook は、ほかのディレクトリの conftest.py の hook も呼ぶ）
    hook = request.node.ihook
    workdir: Path | None = None
    try:
        with contextlib.ExitStack() as stack:
            if case.needs_workdir:
                workdir = tmp_path_factory.mktemp(f"casebook-{case.name}")
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
                outcome = _execute_command(config, hook, doc, case, env, workdir)
            elif case.request is not None:
                outcome = _execute_request(config, hook, case, env, workdir)
            else:
                outcome = _execute_call(config, hook, doc, case, env, workdir)
            for target in case.observe_targets:
                outcome.observed[target] = _observe(config, hook, case, target, env, workdir)
    except CasebookRunError as e:
        pytest.fail(f"[{case.name}] {e}", pytrace=False)

    if doc.states is not None:
        # 実行内容（command / call / request と引数）のあと、結果（exit_code / status）の前に置く
        keys = [key for key, _ in outcome.header]
        results = [i for i, key in enumerate(keys) if key in ("exit_code", "status")]
        index = results[0] if results else len(keys)
        outcome.header.insert(index, ("state", case.state))
    normalizer = _normalizer(config, hook, doc, env, workdir)
    lang = config.getini("casebook_lang")
    if case.uses_golden:
        _compare_golden(request, doc, case, outcome, normalizer, lang)
    else:
        _compare_expect(case, outcome, normalizer, lang)


def _write_files(workdir: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = workdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _in_dir(workdir: Path | None) -> contextlib.AbstractContextManager[Any]:
    """作業ディレクトリがあれば、その中に移動する。"""
    return contextlib.chdir(workdir) if workdir is not None else contextlib.nullcontext()


def _execute_command(
    config: pytest.Config, hook: Any, doc: CasebookDoc, case: Case, env: Any, workdir: Path | None
) -> _Outcome:
    # {casebook_dir} は YAML のあるディレクトリ（作業ディレクトリで実行するときに、
    # YAML の隣のスクリプトなどを指すのに使う）
    yaml_dir = doc.path.parent.as_posix()
    argv = [
        arg.replace(CASEBOOK_DIR_TOKEN, yaml_dir)
        for arg in [*doc.command_prefix, *(case.command_argv or shlex.split(str(case.command)))]
    ]
    cwd = workdir or doc.path.parent
    with _in_dir(workdir):
        result = hook.pytest_casebook_run_command(
            case=case, argv=argv, env=env, cwd=cwd, config=config
        )
    if result is None:
        result = run_subprocess(
            argv,
            cwd=cwd,
            stdin=case.stdin,
            timeout=case.timeout,
            encoding=config.getini("casebook_encoding"),
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
    config: pytest.Config, hook: Any, doc: CasebookDoc, case: Case, env: Any, workdir: Path | None
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
        result = invoke(func, args, kwargs)

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
    config: pytest.Config, hook: Any, case: Case, env: Any, workdir: Path | None
) -> _Outcome:
    assert case.request is not None
    with _in_dir(workdir):
        response = hook.pytest_casebook_request(
            case=case, request=case.request, env=env, workdir=workdir, config=config
        )
    if response is None:
        raise CasebookRunError(
            "request: を送れません（conftest.py に pytest_casebook_request hook を書いてください）"
        )
    if not isinstance(response, HttpResponse):
        raise CasebookRunError(
            "pytest_casebook_request hook は HttpResponse を返してください"
            f"（返したもの: {type(response).__name__}）"
        )
    return _Outcome(
        header=[("request", case.request.display), ("status", str(response.status))],
        response=response,
    )


def _observe(
    config: pytest.Config, hook: Any, case: Case, target: str, env: Any, workdir: Path | None
) -> Any:
    """observe の対象を取り出す（files は作業ディレクトリを読み、ほかは hook に任せる）。"""
    if target == FILES_TARGET:
        assert workdir is not None
        return {
            p.relative_to(workdir).as_posix(): p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(workdir.rglob("*"))
            if p.is_file()
        }
    value = hook.pytest_casebook_observe(
        target=target, case=case, env=env, workdir=workdir, config=config
    )
    if value is None:
        raise CasebookRunError(
            f"observe: {target} を取り出せません"
            "（pytest_casebook_observe hook がないか、None を返しました）"
        )
    return value


def _render_observed(target: str, value: Any, no_files: str = MESSAGES["ja"]["no_files"]) -> str:
    """
    observe で取り出した値の表記（1件を1行にする）。

    期待出力ファイルには、言語の設定によらず日本語の「（ファイルなし）」を書く
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


def _compare_golden(
    request: pytest.FixtureRequest,
    doc: CasebookDoc,
    case: Case,
    outcome: _Outcome,
    normalizer: Normalizer,
    lang: str,
) -> None:
    """期待出力ファイルと比べる（`--casebook-update` のときは期待出力を書き直す）。"""
    config = request.config
    m = MESSAGES[lang]
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

    actual = render(
        case,
        [(key, normalizer(value)) for key, value in outcome.header],
        [(title, normalizer(body)) for title, body in sections],
    )
    path = doc.golden_path(case)
    label = Path(os.path.relpath(path, doc.path.parent)).as_posix()
    # 比べるのは結果だけ（# case: などの説明のヘッダーは比べない）
    default_section = {"command": "stdout", "call": "return", "request": "json"}[case.kind]
    got = parse_golden(actual, default_section)
    expected = parse_golden(read_golden(path), default_section) if path.exists() else None
    if config.getoption("--casebook-update"):
        # 結果が同じなら書き直さない（手で書いた期待出力の書き方を崩さず、
        # ヘッダーだけの違いで差分が出ないようにする）
        if (expected is None or golden_differs(expected, got)) and write_golden(path, actual):
            request.node.user_properties.append(("casebook_updated", True))
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
        prefix = f"{type(error).__name__}: "
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
        problems += match_text(expect["body"], normalizer(response.body), "body", lang)
    # ヘッダー名は大文字小文字を区別しない
    headers = {name.lower(): value for name, value in response.headers.items()}
    for name, expected in (expect.get("headers") or {}).items():
        if name.lower() not in headers:
            problems.append(m["missing_header"].format(name=name))
        else:
            actual_header = normalizer(headers[name.lower()])
            problems += match_text(expected, actual_header, f"headers.{name}", lang)
    return problems


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
            problems += match_text(expect[key], normalizer(getattr(outcome, key)), key, lang)

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
    config: pytest.Config, hook: Any, doc: CasebookDoc, env: Any, workdir: Path | None
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
    patterns = compile_patterns(
        pair for pairs in hook.pytest_casebook_patterns(env=env, config=config) for pair in pairs
    )
    patterns += doc.normalize
    if config.getini("casebook_builtin_patterns"):
        patterns += BUILTIN_PATTERNS
    return Normalizer(placeholders, patterns)
