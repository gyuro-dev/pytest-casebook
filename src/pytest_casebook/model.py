"""
ケースファイル（YAML）の形式の定義と読み込み。

```yaml
title: 計算ツール                 # レポートの見出し（省略時はファイル名）
description: 説明                 # 省略可
levels: [大項目, 中項目, 小項目]   # 階層の呼び名（いくつでも。省略時は ini の casebook_levels）
states:                           # 状態のバリエーション（省略可）
  default: {}
  outage: {db: down}
command_prefix: [python, -m, calc] # command の前に付ける引数（省略可）
golden_dir: golden                # 期待出力の置き場所（このファイルからの相対パス。
                                  # 省略時は golden/<拡張子を除いたファイル名>）
normalize:                        # 出力の置き換え（省略可）
  - {pattern: 'id-\\d+', replace: '<id>'}
cases:
  - group: 足し算                 # グループ（入れ子にできる。入れ子の深さ＝階層）
    description: 説明
    state: outage                 # 中のケースの既定の状態（省略可）
    marks: [slow]                 # 中のケースに付けるマーク（省略可）
    cases:
      - name: add_cli             # ケース名（＝期待出力のファイル名）
        description: 説明
        command: add 1 2          # CLI として実行する
        env: {LANG: C}            # 実行するときの環境変数（省略可。ファイル・グループにも書ける）
      - name: add_func
        call: calc:add            # "モジュール:関数" を呼ぶ
        args: [1, 2]
        kwargs: {}
      - name: print_layout
        manual: 印刷プレビューで罫線を目で確かめる  # 手動のケース（実行しない）
        expect: 2ページ目にも見出し行が出る    # 期待結果を文章で書く
        result: passed            # 手で確かめた結果（省略可）
      - name: import_csv
        setup:                    # このケースだけの準備（省略可）
          files:                  # ケースごとの作業ディレクトリに作るファイル
            input.csv: "id,name\\n1,佐藤\\n"
          db: {users: []}         # files 以外は pytest_casebook_setup hook に渡す
        command: import input.csv # 作業ディレクトリで実行する
        observe: [db.users]       # 実行後に取り出して期待出力に加える（省略可）
        expect:                   # 期待結果を YAML に書く（省略時は期待出力ファイルと比べる）
          exit_code: 0
          stdout: {contains: 1件}
          db.users: [{id: 1, name: 佐藤}]
      - name: shipping            # params: を書くとテンプレートになり、要素を上書きで重ねて
        call: shop:shipping       # 1件ずつのケースに展開する（名前は shipping-0 など）
        params:
          - {name: "0", args: [0], expect: {return: 500}}
          - {name: "3000", args: [3000], expect: {return: 0}}
```
"""

from __future__ import annotations

import math
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .expect import find_matcher_errors
from .http import HttpRequest
from .inifile import IniValue, ini_bool, ini_lines, read_ini
from .messages import TEXTS, error, language

# ケース名は期待出力のファイル名になるため、ファイル名に使える文字だけにする。
# 先頭の . と - は認めない（.foo.txt は隠しファイルになり、消し忘れの確認からも漏れる）
NAME_RE = re.compile(r"^\w[\w.\-]*$")

_TOP_KEYS = {
    "request_defaults",
    "title",
    "description",
    "levels",
    "states",
    "command_prefix",
    "golden_dir",
    "check_orphans",
    "normalize",
    "meta",
    "env",
    "timeout",
    "cases",
}
_GROUP_KEYS = {
    "group",
    "description",
    "state",
    "marks",
    "meta",
    "env",
    "timeout",
    "skip",
    "xfail",
    "cases",
}
_CASE_KEYS = {
    "request",
    "meta",
    "skip",
    "xfail",
    "name",
    "params",
    "description",
    "command",
    "call",
    "args",
    "kwargs",
    "stdin",
    "stdin_file",
    "timeout",
    "env",
    "state",
    "marks",
    "golden",
    "setup",
    "observe",
    "expect",
    "manual",
    "result",
}
# manual のケースに書けないキー（実行しないので意味がない）
_MANUAL_FORBIDDEN_KEYS = (
    "args",
    "kwargs",
    "stdin",
    "stdin_file",
    "timeout",
    "env",
    "observe",
    "golden",
)
# manual のケースの result: に書ける値
MANUAL_RESULTS = ("passed", "failed", "skipped")

DEFAULT_STATE = "default"
DEFAULT_GOLDEN_DIR = "golden"
# 期待出力の消し忘れを確かめるテストの名前（check_orphans: true のとき、ケース名には使えない）
ORPHANS_TEST_NAME = "golden_orphans"

# expect に書ける、実行結果そのものの項目（それ以外のキーは observe の対象として扱う）
COMMAND_EXPECT_KEYS = ("exit_code", "stdout", "stderr")
CALL_EXPECT_KEYS = ("return", "raises", "stdout", "stderr")
REQUEST_EXPECT_KEYS = ("status", "json", "body", "headers")
RESULT_EXPECT_KEYS = frozenset((*COMMAND_EXPECT_KEYS, *CALL_EXPECT_KEYS, *REQUEST_EXPECT_KEYS))
EXPECT_KEYS_BY_KIND = {
    "command": COMMAND_EXPECT_KEYS,
    "call": CALL_EXPECT_KEYS,
    "request": REQUEST_EXPECT_KEYS,
}
_REQUEST_KEYS = {"method", "path", "query", "headers", "json", "body"}
_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
# 文字列の期待値に使える比べ方（完全一致は文字列をそのまま書く）
TEXT_MATCHERS = ("contains", "regex")
# 文字列の期待値（そのままの文字列・{contains}・{regex}）を書ける項目
TEXT_EXPECT_KEYS = ("stdout", "stderr", "raises", "body")
# 組み込みの observe の対象（作業ディレクトリのファイル）
FILES_TARGET = "files"


class CasebookError(Exception):
    """
    An error in how a case file is written.

    ケースファイルの書き方の誤り。
    """


@dataclass(frozen=True)
class Group:
    """
    A group that classifies cases (e.g. category / subcategory / item).

    ケースを分類するグループ（大項目・中項目・小項目など）。
    """

    name: str
    description: str = ""


@dataclass(frozen=True)
class Case:
    """
    A single case. It has exactly one of `command`, `call`, `request`, and `manual`.

    1件のケース。`command`・`call`・`request`・`manual` のどれか1つを持つ。
    """

    name: str
    description: str = ""
    groups: tuple[Group, ...] = ()
    # command: に書いた文字列（リストで書いたときは、表示用に1行にしたもの）
    command: str | None = None
    # command: をリストで書いたときの引数（shell の書き方として区切らずに、そのまま使う）
    command_argv: tuple[str, ...] | None = None
    call: str | None = None
    # HTTP のリクエスト（request_defaults の headers を重ねたもの）
    request: HttpRequest | None = None
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    stdin: str | None = None
    # 標準入力に渡すファイル（YAML のディレクトリからの相対パス。stdin とは同時に書けない）
    stdin_file: str | None = None
    timeout: float | None = None
    # command を実行するときに os.environ に重ねる環境変数。ファイル・グループ・ケースの env: を
    # 外側から上書きで重ねたもの（null で外側の変数を消す）。command 以外のケースでは空
    env: dict[str, str] = field(default_factory=dict)
    state: str = DEFAULT_STATE
    # states: のうち、このケースの状態の内容（files を含む、書いたままのもの）
    state_data: Any = None
    marks: tuple[str, ...] = ()
    golden: str | None = None
    # pytest_casebook_setup hook に渡す内容。状態の内容に、ケースの setup: を上書きで重ね、
    # files を除いたもの。setup: も states: もなければ None
    setup: dict[str, Any] | None = None
    # 状態とケースの setup: の files を重ねたもの（作業ディレクトリからの相対パス -> 内容）
    setup_files: dict[str, str] = field(default_factory=dict)
    # 状態かケースの setup: に files を書いたか。空（files: {}）でも作業ディレクトリを作る
    has_setup_files: bool = False
    # ケースに書いた setup:（状態を重ねる前。レポートの「前提条件」に出す）
    own_setup: dict[str, Any] | None = None
    observe: tuple[str, ...] = ()
    expect: dict[str, Any] | None = None
    # 利用する側が自由に使う情報（pytest-casebook は中身を見ない）。
    # 外側のグループの meta に、ケースの meta を上書きで重ねたもの
    meta: dict[str, Any] = field(default_factory=dict)
    # スキップする理由 / 失敗することが分かっている理由（グループに書くと中のケースすべてに付く）
    skip: str | None = None
    xfail: str | None = None
    # YAML の中で、このケースが始まる行（0 から数える。分からなければ None）
    line: int | None = None
    # 手動のケースの手順（manual: に書いたもの）。手動のケースは実行しない
    manual: str | None = None
    # 手動のケースの期待結果（expect: に文章で書いたもの）
    manual_expect: tuple[str, ...] = ()
    # 手動のケースを手で確かめた結果（passed・failed・skipped。まだなら None）
    result: str | None = None

    @property
    def path(self) -> tuple[str, ...]:
        """
        Group names from the outermost (e.g. `("Addition", "Integers")`).

        グループ名を外側から並べたもの（例: `("足し算", "整数")`）。
        """
        return tuple(g.name for g in self.groups)

    @property
    def kind(self) -> str:
        """
        One of `"command"`, `"call"`, `"request"`, and `"manual"`.

        `"command"`・`"call"`・`"request"`・`"manual"` のどれか。
        """
        if self.manual is not None:
            return "manual"
        return _kind_of(self.command, self.call)

    @property
    def uses_golden(self) -> bool:
        """
        Whether the case is compared with a golden file (True when it has no `expect:` and is
        not a manual case).

        期待出力ファイルと比べるケースか（expect: がなく、手動のケースでなければ True）。
        """
        return self.expect is None and self.manual is None

    @property
    def observe_targets(self) -> tuple[str, ...]:
        """
        Targets fetched after the run: those in `observe:` plus the targets written in
        `expect:` (e.g. `db.users`).

        実行後に取り出す対象。observe: に書いたものと、expect: に書いた対象（`db.users` など）。
        """
        extra = [k for k in self.expect or {} if k not in RESULT_EXPECT_KEYS]
        return tuple(dict.fromkeys([*self.observe, *extra]))

    @property
    def needs_workdir(self) -> bool:
        """
        Whether a per-case working directory is created: when `files:` is written in the
        state or the case's setup (even `files: {}`), or when the case fetches `files`.
        Always False for a manual case (it is never run).

        ケースごとの作業ディレクトリを作るか。状態かケースの setup に `files:` を書いたとき
        （`files: {}` でも）と、files を取り出すとき。手動のケースは実行しないので、いつも False。
        """
        if self.manual is not None:
            return False
        return (
            self.has_setup_files or bool(self.setup_files) or FILES_TARGET in self.observe_targets
        )

    @property
    def golden_file(self) -> str:
        """
        The golden file name (`<name>.txt` when `golden` is omitted).

        期待出力ファイルの名前（`golden` を省略したときは `<name>.txt`）。
        """
        return self.golden or f"{self.name}.txt"


def _kind_of(command: str | None, call: str | None) -> str:
    """ケースの種類（Case を作る前の、YAML を確かめる途中でも使う）。"""
    if command is not None:
        return "command"
    return "call" if call is not None else "request"


@dataclass
class CasebookDoc:
    """
    The contents of one case file.

    1つのケースファイルの内容。
    """

    path: Path
    title: str
    description: str
    levels: tuple[str, ...]
    states: dict[str, Any] | None
    command_prefix: tuple[str, ...]
    golden_dir: Path
    check_orphans: bool
    normalize: list[tuple[re.Pattern[str], str]]
    cases: list[Case]
    # request: に重ねる既定のヘッダー（request_defaults.headers）
    request_headers: dict[str, str] = field(default_factory=dict)
    # ファイル全体の meta（利用する側が自由に使う）
    meta: dict[str, Any] = field(default_factory=dict)
    # ファイル全体の env（どの command のケースにも重ねる環境変数）
    env: dict[str, str] = field(default_factory=dict)
    # load(ini=True) で読んだ ini の casebook_* の値。run_case() の既定に使う
    # （lang・encoding・builtin_patterns・description。ini=False なら空）
    options: dict[str, Any] = field(default_factory=dict)
    # YAML のマッピング（id）-> 始まる行。ケースの行番号を求めるのに、読み込み中だけ使う
    # （id は読み終えると別のオブジェクトに使われうるので、読み終えたら空にする）
    _source_lines: dict[int, int] = field(default_factory=dict, repr=False, compare=False)

    def golden_path(self, case: Case) -> Path:
        """
        The path of the case's golden file (`<name>.txt` when `golden` is omitted).

        :param case: a case in this file
        :return: the golden file path

        ケースの期待出力ファイルのパス（`golden` を省略したときは `<name>.txt`）。

        :param case: このファイルのケース
        :return: 期待出力ファイルのパス
        """
        return self.golden_dir / case.golden_file


def one_line(text: Any) -> str:
    """改行や連続する空白を1つの空白にして1行にする。"""
    return " ".join(str(text or "").split())


def _check_keys(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise CasebookError(error("unknown_keys", where=where, keys=", ".join(unknown)))


def _str(value: Any, where: str, key: str, *, required: bool = False) -> str:
    """文字列の値を確かめる。省略（None）は空文字にし、required なら空白だけも誤りにする。"""
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise CasebookError(error("not_string", where=where, key=key))
    return value


def _bool(value: Any, where: str, key: str) -> bool:
    """真偽値を確かめる（"false" のような文字列を True と取り違えないように）。"""
    if not isinstance(value, bool):
        raise CasebookError(error("not_bool", where=where, key=key))
    return value


def _timeout(value: Any, loc: str) -> float | int | None:
    """
    timeout:（秒数）を確かめる。ファイル・グループ・ケースで同じ書き方。

    0 以下は必ず時間切れになり、.inf や .nan はスレッドを待つところで例外になるので、誤りにする。
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value < math.inf:
        raise CasebookError(error("timeout_number", where=loc))
    return value


def _str_list(value: Any, where: str, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CasebookError(error("not_string_list", where=where, key=key))
    return tuple(value)


def _command_prefix(value: Any, where: str) -> tuple[str, ...]:
    """command_prefix: を引数のタプルにする（文字列なら shell の書き方として区切る）。"""
    if isinstance(value, str):
        return tuple(_shell_split(value, where, "command_prefix"))
    return _str_list(value, where, "command_prefix")


def _shell_split(value: str, where: str, key: str) -> list[str]:
    """shell の書き方として区切る（クォートの閉じ忘れは、実行の前に YAML の誤りにする）。"""
    try:
        return shlex.split(value)
    except ValueError as e:
        raise CasebookError(error("bad_shell", where=where, key=key, error=e)) from None


def _normalize_rules(value: Any, where: str) -> list[tuple[re.Pattern[str], str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CasebookError(error("normalize_list", where=where))
    rules: list[tuple[re.Pattern[str], str]] = []
    for i, rule in enumerate(value):
        loc = f"{where}: normalize[{i}]"
        if not isinstance(rule, dict):
            raise CasebookError(error("normalize_item", where=loc))
        _check_keys(rule, {"pattern", "replace"}, loc)
        pattern = _str(rule.get("pattern"), loc, "pattern", required=True)
        try:
            rules.append((re.compile(pattern), _str(rule.get("replace"), loc, "replace")))
        except re.error as e:
            raise CasebookError(error("bad_regex", where=loc, error=e)) from None
    return rules


def load(
    path: str | Path,
    *,
    golden_dir: str | Path | None = None,
    levels: tuple[str, ...] | None = None,
    command_prefix: tuple[str, ...] | None = None,
    lang: str | None = None,
    ini: bool = False,
) -> CasebookDoc:
    """
    Load a case file. Call this to use the same YAML as the tests from outside pytest
    (e.g. a demo script).

    ```python
    import pytest_casebook

    doc = pytest_casebook.load("tests/casebook_demo.yaml", ini=True)
    for case in doc.cases:
        if case.meta.get("demo"):
            print(case.name, case.command)
    ```

    With `ini=True`, the `casebook_*` options are read from the pytest configuration file,
    so the result follows the project settings as under pytest. The file is looked up from
    the case file's directory upwards; in each directory the first of `pytest.ini`,
    `pyproject.toml` (with `[tool.pytest.ini_options]`), `tox.ini` (with `[pytest]`) and
    `setup.cfg` (with `[tool:pytest]`) is used. This is a simplified version of pytest's
    lookup: `-c`, `--rootdir` and `-o` are not taken into account. `casebook_golden_dir`,
    `casebook_levels`, `casebook_command_prefix` and `casebook_lang` apply here;
    `casebook_lang`, `casebook_encoding`, `casebook_builtin_patterns` and
    `casebook_golden_description` are kept in `doc.options` and used by `run_case()`.
    The arguments given here win over the ini values.

    :param path: path to the case file
    :param golden_dir: where golden files are stored when the YAML has no `golden_dir`
        (defaults to `<file's directory>/golden/<file name without extension>`, the same as
        the pytest default; with `ini=True`, `casebook_golden_dir` replaces `golden`)
    :param levels: names of the hierarchy levels when the YAML has no `levels` (defaults to
        `casebook_levels` with `ini=True`, else those of `lang`: `Category / Subcategory /
        Item` for `en`)
    :param command_prefix: arguments put before the command when the YAML has no
        `command_prefix` (defaults to `casebook_command_prefix` with `ini=True`, else none)
    :param lang: language of the error messages and the default `levels`: `en` or `ja`
        (defaults to `casebook_lang` with `ini=True`, else `en`)
    :param ini: read the `casebook_*` options from the pytest configuration file
    :return: the validated contents of the case file
    :raises CasebookError: when the file cannot be read as YAML or is written incorrectly
    :raises OSError: when the file cannot be read
    :raises UnicodeDecodeError: when the file is not UTF-8
    :raises ValueError: when `lang` is not supported, or an ini value is invalid

    ケースファイルを読み込む。pytest の外（デモ用のスクリプトなど）から、
    テストと同じ YAML を使うときに呼ぶ。

    ```python
    import pytest_casebook

    doc = pytest_casebook.load("tests/casebook_demo.yaml", ini=True)
    for case in doc.cases:
        if case.meta.get("demo"):
            print(case.name, case.command)
    ```

    `ini=True` にすると、pytest の設定ファイルから `casebook_*` の設定を読み、pytest で
    動かすときと同じ設定になる。設定ファイルはケースファイルのディレクトリから上へ探し、
    ディレクトリごとに `pytest.ini`・`pyproject.toml`（`[tool.pytest.ini_options]` が
    あるもの）・`tox.ini`（`[pytest]` があるもの）・`setup.cfg`（`[tool:pytest]` が
    あるもの）の順で最初に見つかったものを使う。pytest の探し方を簡単にしたもので、
    `-c`・`--rootdir`・`-o` は考えない。`casebook_golden_dir`・`casebook_levels`・
    `casebook_command_prefix`・`casebook_lang` はここで使い、`casebook_lang`・
    `casebook_encoding`・`casebook_builtin_patterns`・`casebook_golden_description` は
    `doc.options` に入れて `run_case()` が使う。ここで渡した引数は ini の値より優先する。

    :param path: ケースファイルのパス
    :param golden_dir: YAML に `golden_dir` がないときの期待出力の置き場所
        （省略時は pytest の既定と同じ
        `<ファイルのディレクトリ>/golden/<拡張子を除いたファイル名>`。
        `ini=True` なら `golden` の代わりに `casebook_golden_dir`）
    :param levels: YAML に `levels` がないときの階層の呼び名（省略時は、`ini=True` なら
        `casebook_levels`、それもなければ `lang` の言語の既定。
        `en` なら `Category / Subcategory / Item`）
    :param command_prefix: YAML に `command_prefix` がないときに command の前に付ける引数
        （省略時は、`ini=True` なら `casebook_command_prefix`、それ以外はなし）
    :param lang: 書き方の誤りのメッセージと、`levels` の既定の言語。`en` か `ja`
        （省略時は、`ini=True` なら `casebook_lang`、それ以外は `en`）
    :param ini: pytest の設定ファイルから `casebook_*` の設定を読む
    :return: 検証済みのケースファイルの内容
    :raises CasebookError: YAML として読めない、または書き方に誤りがあるとき
    :raises OSError: ファイルを読めないとき
    :raises UnicodeDecodeError: UTF-8 でないとき
    :raises ValueError: `lang` が対応していない言語のとき、または ini の値が正しくないとき
    """
    # 絶対パスにしておく。"casebook_x.yaml" のような相対パスのままだと、YAML のディレクトリが
    # "." になり、正規化で "." を {casebook_dir} に置き換えてしまう。{casebook_dir} の展開や
    # sys.path に加えるパスも、作業ディレクトリに移動したあとでは別の場所を指してしまう。
    # resolve() ではなく pytest と同じ abspath にする（symlink やネットワークドライブを
    # たどると、pytest の rootpath と別の表記になり、relpath が食い違う・失敗するため）。
    # Path.absolute() は .. を残すので、上のディレクトリの設定ファイルを探すときに困る
    path = Path(os.path.abspath(path))  # noqa: PTH100
    # ini=True なら pytest の設定ファイルの値（引数で渡したものが優先、なければ組み込みの既定）
    values: dict[str, IniValue] = read_ini(path.parent)[1] if ini else {}
    if lang is None:
        lang = str(values.get("casebook_lang", "en"))
    if lang not in TEXTS:
        raise ValueError(f"lang must be one of {' / '.join(TEXTS)}: {lang}")
    if golden_dir is None and "casebook_golden_dir" in values:
        golden_dir = path.parent / str(values["casebook_golden_dir"]) / path.stem
    if levels is None and "casebook_levels" in values:
        levels = tuple(ini_lines(values["casebook_levels"])) or None
    if command_prefix is None:
        command_prefix = tuple(
            _shell_split(
                str(values.get("casebook_command_prefix", "")),
                "casebook_command_prefix",
                "casebook_command_prefix",
            )
        )
    options: dict[str, Any] = {}
    if ini:
        options = {
            "lang": lang,
            "encoding": str(values.get("casebook_encoding", "utf-8")),
            "builtin_patterns": ini_bool(
                "casebook_builtin_patterns", values.get("casebook_builtin_patterns", "true")
            ),
            "description": ini_bool(
                "casebook_golden_description", values.get("casebook_golden_description", "false")
            ),
        }
    with language(lang):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise CasebookError(error("not_utf8", where=path.name, error=e)) from None
        loader = _LineLoader(source)
        try:
            data = loader.get_single_data()
        except yaml.YAMLError as e:
            hint = ""
            if "mapping values are not allowed" in str(e):
                # 一番よくある書き間違い（description: setup: の説明 など）
                hint = error("yaml_hint")
            raise CasebookError(error("yaml_error", where=path.name, error=e, hint=hint)) from None
        finally:
            loader.dispose()
        doc = parse_document(
            data,
            path,
            golden_dir=(
                Path(os.path.abspath(golden_dir))  # noqa: PTH100 (path と同じ)
                if golden_dir
                else path.parent / DEFAULT_GOLDEN_DIR / path.stem
            ),
            levels=levels if levels is not None else TEXTS[lang]["levels"],
            command_prefix=command_prefix,
            source_lines=loader.lines,
        )
    doc.options = options
    return doc


class _LineLoader(yaml.SafeLoader):
    """safe_load と同じように読み、マッピングが始まる行を覚えておく。"""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.lines: dict[int, int] = {}

    def construct_line_map(self, node: yaml.MappingNode) -> Any:
        """
        マッピングを作り、始まる行を覚える（PyYAML の作法どおり、先に空の dict を返してから
        中身を入れる。アンカーで自分を参照していても読めるように）。
        """
        data: dict[Any, Any] = {}
        self.lines[id(data)] = node.start_mark.line
        yield data
        data.update(self.construct_mapping(node))


_LineLoader.add_constructor("tag:yaml.org,2002:map", _LineLoader.construct_line_map)


def parse_document(
    data: Any,
    path: Path,
    *,
    golden_dir: Path,
    levels: tuple[str, ...],
    command_prefix: tuple[str, ...] = (),
    source_lines: dict[int, int] | None = None,
) -> CasebookDoc:
    """
    YAML を読み込んだ値を検証して `CasebookDoc` にする。

    :param data: YAML を読み込んだ値（`yaml.safe_load` と同じ形）
    :param path: ケースファイルのパス
    :param golden_dir: YAML に `golden_dir` がないときの期待出力の置き場所
    :param levels: YAML に `levels` がないときの階層の呼び名
    :param command_prefix: YAML に `command_prefix` がないときに command の前に付ける引数
    :param source_lines: マッピングの id -> 始まる行（`_LineLoader.lines`）。ケースの行番号に使う
    :return: 検証済みのケースファイルの内容
    :raises CasebookError: 書き方に誤りがあるとき
    """
    where = path.name
    if not isinstance(data, dict):
        raise CasebookError(error("top_mapping", where=where))
    _check_keys(data, _TOP_KEYS, where)

    states = data.get("states")
    if states is not None and not (
        isinstance(states, dict) and all(isinstance(k, str) for k in states)
    ):
        raise CasebookError(error("states_mapping", where=where))
    # 状態は「名前を付けた setup:」なので、setup: と同じ書き方であることを確かめる
    for name, value in (states or {}).items():
        _parse_setup(value, f"{where}: states.{name}")

    doc = CasebookDoc(
        path=path,
        title=_str(data.get("title"), where, "title") or path.name,
        description=_str(data.get("description"), where, "description"),
        levels=_str_list(data["levels"], where, "levels") if "levels" in data else levels,
        states=states,
        command_prefix=(
            _command_prefix(data["command_prefix"], where)
            if "command_prefix" in data
            else command_prefix
        ),
        golden_dir=(
            path.parent / _str(data["golden_dir"], where, "golden_dir", required=True)
            if "golden_dir" in data
            else golden_dir
        ),
        check_orphans=_bool(data.get("check_orphans", True), where, "check_orphans"),
        normalize=_normalize_rules(data.get("normalize"), where),
        request_headers=_request_defaults(data.get("request_defaults"), where),
        cases=[],
        meta=_meta(data.get("meta"), where),
        env=_merge_env({}, _env(data.get("env"), where)),
        _source_lines=source_lines or {},
    )

    if not data.get("cases"):
        raise CasebookError(error("no_cases", where=where))
    _walk(
        data["cases"],
        doc,
        (),
        DEFAULT_STATE,
        (),
        {},
        doc.env,
        {},
        _timeout(data.get("timeout"), where),
        f"{where}: cases",
    )

    seen: dict[str, int] = {}
    for case in doc.cases:
        seen[case.name] = seen.get(case.name, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    if duplicates:
        raise CasebookError(error("duplicate_names", where=where, names=", ".join(duplicates)))
    # 大文字小文字だけが違う名前は、Windows で期待出力が同じファイルになるため誤りにする
    folded: dict[str, set[str]] = {}
    for name in seen:
        folded.setdefault(name.casefold(), set()).add(name)
    collided = sorted(" / ".join(sorted(names)) for names in folded.values() if len(names) > 1)
    if collided:
        raise CasebookError(error("duplicate_names_case", where=where, names=", ".join(collided)))
    # 同じ名前のテストが2つになり、-k や結果で区別できなくなるため
    if doc.check_orphans and ORPHANS_TEST_NAME in seen:
        raise CasebookError(error("reserved_name", where=where, name=ORPHANS_TEST_NAME))
    doc._source_lines = {}
    return doc


def _walk(
    items: Any,
    doc: CasebookDoc,
    groups: tuple[Group, ...],
    state: str,
    marks: tuple[str, ...],
    meta: dict[str, Any],
    env: dict[str, str],
    flags: dict[str, str],
    timeout: float | int | None,
    where: str,
) -> None:
    """グループを再帰的にたどり、ケースを `doc.cases` に順に追加する。"""
    if not isinstance(items, list):
        raise CasebookError(error("items_list", where=where))
    if not items:
        # グループの cases: が空リスト（ファイルの cases: [] と同じ扱い）
        raise CasebookError(error("no_cases", where=where))
    for i, item in enumerate(items):
        # 書き方の誤りを知らせるときに、YAML の何行目かも出す
        line = doc._source_lines.get(id(item)) if isinstance(item, dict) else None
        loc = f"{where}[{i}]" + (error("line", line=line + 1) if line is not None else "")
        if not isinstance(item, dict):
            raise CasebookError(error("item_mapping", where=loc))
        if "group" in item:
            _check_keys(item, _GROUP_KEYS, loc)
            group = Group(
                name=_str(item["group"], loc, "group", required=True),
                description=_str(item.get("description"), loc, "description"),
            )
            _walk(
                item.get("cases"),
                doc,
                (*groups, group),
                _state(item, loc, state),
                (*marks, *_str_list(item.get("marks"), loc, "marks")),
                {**meta, **_meta(item.get("meta"), loc)},
                _merge_env(env, _env(item.get("env"), loc)),
                {**flags, **_flags(item, loc)},
                _timeout(item["timeout"], loc) if "timeout" in item else timeout,
                f"{loc}{error('in_group', name=group.name)}.cases",
            )
        elif "params" in item:
            # params: を持つケースはテンプレート。テンプレートに params の各要素を上書きで
            # 重ねて（深い併合はしない）、1件ずつのケースにする。要素は name を持ち、
            # ケース名は「テンプレート名-要素名」になる。重ねた結果の検証は、ふつうの
            # ケースと同じ _parse_case に任せる
            params = item["params"]
            if not (
                isinstance(params, list) and params and all(isinstance(p, dict) for p in params)
            ):
                raise CasebookError(error("params_list", where=loc))
            template = {k: v for k, v in item.items() if k != "params"}
            name = _str(template.get("name"), loc, "name", required=True)
            for param in params:
                # 誤りの表示とレポートの行番号は、要素自身の行を優先する（分からなければ
                # テンプレートの行）。_parse_case が merged の id で行を引けるように登録する
                pline = doc._source_lines.get(id(param), line)
                ploc = f"{where}[{i}]" + (
                    error("line", line=pline + 1) if pline is not None else ""
                )
                if "params" in param:
                    raise CasebookError(error("params_nested", where=ploc))
                if "name" not in param:
                    raise CasebookError(error("params_name", where=ploc))
                merged = {**template, **param}
                merged["name"] = f"{name}-{_str(param['name'], ploc, 'name', required=True)}"
                if pline is not None:
                    doc._source_lines[id(merged)] = pline
                doc.cases.append(
                    _parse_case(merged, doc, groups, state, marks, meta, env, flags, timeout, ploc)
                )
        else:
            doc.cases.append(
                _parse_case(item, doc, groups, state, marks, meta, env, flags, timeout, loc)
            )


# call: の形（モジュール:関数）。空の名前・空白・相対 import（先頭の .）は通さない
_CALL_RE = re.compile(r"[^:\s.][^:\s]*:[^:\s]+")


def _parse_case(
    item: dict[str, Any],
    doc: CasebookDoc,
    groups: tuple[Group, ...],
    state: str,
    marks: tuple[str, ...],
    meta: dict[str, Any],
    env: dict[str, str],
    flags: dict[str, str],
    timeout: float | int | None,
    loc: str,
) -> Case:
    _check_keys(item, _CASE_KEYS, loc)
    name = _str(item.get("name"), loc, "name", required=True)
    if not NAME_RE.match(name):
        raise CasebookError(error("bad_name", where=loc, name=repr(name)))
    loc = f"{loc}{error('in_case', name=name)}"

    if sum(key in item for key in ("command", "call", "request", "manual")) != 1:
        raise CasebookError(error("one_action", where=loc))
    manual = _str(item["manual"], loc, "manual", required=True) if "manual" in item else None
    if manual is not None:
        forbidden = [key for key in _MANUAL_FORBIDDEN_KEYS if key in item]
        if forbidden:
            raise CasebookError(error("manual_keys", where=loc, keys=", ".join(forbidden)))
    elif "result" in item:
        raise CasebookError(error("result_only_manual", where=loc))
    command = None
    command_argv = None
    if isinstance(item.get("command"), list):
        # リストで書くと、shell の書き方として区切らない（Windows のパスの \ が消えない）
        command_argv = _str_list(item["command"], loc, "command")
        command = shlex.join(command_argv)
        if not command_argv and not doc.command_prefix:
            raise CasebookError(error("empty_command", where=loc))
    elif "command" in item:
        # 空文字も書ける（command_prefix だけで実行するとき）
        command = _str(item["command"], loc, "command")
        # 空白だけも空として扱う（区切ると引数が1つもない）
        if not _shell_split(command, loc, "command") and not doc.command_prefix:
            raise CasebookError(error("empty_command", where=loc))
    call = _str(item["call"], loc, "call", required=True) if "call" in item else None
    if call is not None and not _CALL_RE.fullmatch(call):
        raise CasebookError(error("bad_call", where=loc, call=repr(call)))
    if call is None and ("args" in item or "kwargs" in item):
        raise CasebookError(error("args_only_call", where=loc))
    if command is None and "stdin" in item:
        raise CasebookError(error("stdin_only_command", where=loc))
    if command is None and "stdin_file" in item:
        raise CasebookError(error("stdin_file_only_command", where=loc))
    if "stdin" in item and "stdin_file" in item:
        raise CasebookError(error("stdin_and_file", where=loc))
    stdin_file = None
    if "stdin_file" in item:
        stdin_file = _str(item["stdin_file"], loc, "stdin_file", required=True)
        # YAML のディレクトリの外（絶対パスや ..）は指せない
        if not _is_inside(stdin_file):
            raise CasebookError(error("stdin_file_path", where=loc, name=repr(stdin_file)))
    # ケースに env: を書けるのは command だけ（ファイルやグループから受け継いだ env は、
    # command 以外のケースでは使わないだけで、誤りにはしない）
    if command is None and "env" in item:
        raise CasebookError(error("env_only_command", where=loc))
    own_env = _env(item.get("env"), loc)
    request = (
        _parse_request(item["request"], doc.request_headers, loc) if "request" in item else None
    )
    kind = _kind_of(command, call)

    args = item.get("args", [])
    if not isinstance(args, list):
        raise CasebookError(error("args_list", where=loc))
    kwargs = item.get("kwargs", {})
    if not (isinstance(kwargs, dict) and all(isinstance(k, str) for k in kwargs)):
        raise CasebookError(error("kwargs_mapping", where=loc))
    # ケースに書いた timeout が最優先。なければファイル・グループから受け継いだ既定を使う
    if "timeout" in item:
        timeout = _timeout(item["timeout"], loc)
    if manual is not None:
        # 手動のケースは実行しないため、受け継いだ既定の timeout は使わない
        # （ケース自身の timeout: は _MANUAL_FORBIDDEN_KEYS で先に誤りにしている）
        timeout = None

    state = _state(item, loc, state)
    if doc.states is None:
        if state != DEFAULT_STATE:
            raise CasebookError(error("state_without_states", where=loc, state=state))
        state_data = None
    elif state in doc.states:
        state_data = doc.states[state]
    else:
        raise CasebookError(error("unknown_state", where=loc, state=state))

    # 状態の内容に、ケースの setup: を上書きで重ねる（files はファイル名ごとに重ねる）
    base, base_files = _parse_setup(state_data, loc)
    own, own_files = _parse_setup(item.get("setup"), loc)
    setup = None if base is None and own is None else {**(base or {}), **(own or {})}
    # files: を書いたか（空でも）は、None かどうかで分かる
    has_setup_files = base_files is not None or own_files is not None
    setup_files = {**(base_files or {}), **(own_files or {})}

    observe = _str_list(item.get("observe"), loc, "observe")
    expect = (
        _parse_expect(item["expect"], kind, loc) if "expect" in item and manual is None else None
    )
    if expect is not None:
        # expect: のケースは期待出力ファイルを使わないので、expect: にない observe: の対象は
        # 取り出しても何とも比べられず、黙って捨てられてしまう。誤りにして知らせる
        # （組み込みの files も同じ）
        missing = [target for target in observe if target not in expect]
        if missing:
            raise CasebookError(
                error("observe_not_in_expect", where=loc, targets=", ".join(missing))
            )

    return Case(
        name=name,
        description=_str(item.get("description"), loc, "description"),
        groups=groups,
        command=command,
        command_argv=command_argv,
        call=call,
        request=request,
        args=args,
        kwargs=kwargs,
        stdin=_str(item.get("stdin"), loc, "stdin") if "stdin" in item else None,
        stdin_file=stdin_file,
        timeout=timeout,
        env=_merge_env(env, own_env) if command is not None else {},
        state=state,
        state_data=state_data,
        marks=(*marks, *_str_list(item.get("marks"), loc, "marks")),
        golden=_golden_name(item, loc),
        setup=setup,
        setup_files=setup_files,
        has_setup_files=has_setup_files,
        own_setup=item.get("setup"),
        observe=observe,
        expect=expect,
        meta={**meta, **_meta(item.get("meta"), loc)},
        line=doc._source_lines.get(id(item)),
        manual=manual,
        manual_expect=_manual_expect(item.get("expect"), loc) if manual is not None else (),
        result=_manual_result(item.get("result"), loc),
        **{**flags, **_flags(item, loc)},
    )


def _manual_expect(value: Any, loc: str) -> tuple[str, ...]:
    """手動のケースの expect:（期待結果を文章で書いたもの。文字列か文字列のリスト）。"""
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
        raise CasebookError(error("manual_expect", where=loc))
    return tuple(value)


def _manual_result(value: Any, loc: str) -> str | None:
    """手動のケースの result:（passed・failed・skipped）。"""
    if value is None:
        return None
    if value not in MANUAL_RESULTS:
        raise CasebookError(error("result_value", where=loc, values=" / ".join(MANUAL_RESULTS)))
    return str(value)


def _flags(item: dict[str, Any], loc: str) -> dict[str, str]:
    """skip: / xfail: を取り出す（理由を文字列で書く）。"""
    flags: dict[str, str] = {}
    for key in ("skip", "xfail"):
        if key in item:
            value = item[key]
            # skip: true のように書きがちなので、理由を書くことを例で示す
            if not isinstance(value, str) or not value.strip():
                raise CasebookError(error("reason_string", where=loc, key=key))
            flags[key] = value
    return flags


def _meta(value: Any, loc: str) -> dict[str, Any]:
    """meta: を確かめる（中身は利用する側が自由に使うため、マッピングであることだけを見る）。"""
    if value is None:
        return {}
    if not (isinstance(value, dict) and all(isinstance(k, str) for k in value)):
        raise CasebookError(error("meta_mapping", where=loc))
    return dict(value)


def _env(value: Any, loc: str) -> dict[str, str | None]:
    """
    env: を確かめ、変数名 -> 値 にする。

    値は文字列か数値（`DEBUG: 1` のように書けるよう、数値は文字列にする）。null は外側の
    値を消す印として None のまま返す。true / false は "True" などに変わって紛らわしいため
    誤りにする（文字列で "true" と書く）。
    """
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(k, str)
        and k
        and "=" not in k
        and (v is None or (isinstance(v, str | int | float) and not isinstance(v, bool)))
        for k, v in value.items()
    ):
        raise CasebookError(error("env_mapping", where=loc))
    return {k: None if v is None else str(v) for k, v in value.items()}


def _merge_env(outer: dict[str, str], inner: dict[str, str | None]) -> dict[str, str]:
    """外側の env に内側の env を上書きで重ねる（内側で null にした変数は消す）。"""
    merged = dict(outer)
    for name, value in inner.items():
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = value
    return merged


def _parse_setup(value: Any, loc: str) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """
    setup: を (hook に渡す部分, files) に分ける。

    files: を書いていなければ files は None。空（`files: {}`）なら {} で、
    作業ディレクトリを作る印になる。
    """
    if value is None:
        return None, None
    if not (isinstance(value, dict) and all(isinstance(k, str) for k in value)):
        raise CasebookError(error("setup_mapping", where=loc))
    data = dict(value)
    if "files" not in data:
        return data, None
    # files: の下が空（null）なら、置くファイルはない。[] や "" は誤りにする
    files = data.pop("files")
    if files is None:
        files = {}
    if not (
        isinstance(files, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items())
    ):
        raise CasebookError(error("setup_files", where=loc))
    for name in files:
        if not _is_inside(name):
            raise CasebookError(error("setup_file_path", where=loc, name=repr(name)))
    return data, files


def _state(item: dict[str, Any], loc: str, inherited: str) -> str:
    """state: を確かめる（書いたなら空にできない。書かなければ外側のグループのもの）。"""
    if "state" not in item:
        return inherited
    return _str(item["state"], loc, "state", required=True)


def _golden_name(item: dict[str, Any], loc: str) -> str | None:
    """golden:（期待出力のファイル名）を確かめる。期待出力の置き場所の外は指せない。"""
    if "golden" not in item:
        return None
    name = _str(item["golden"], loc, "golden", required=True)
    if not _is_inside(name):
        raise CasebookError(error("golden_path", where=loc, name=repr(name)))
    return name


def _is_inside(name: str) -> bool:
    """
    基準のディレクトリの中を指す相対パスか（絶対パス・ドライブ名・.. を含まない）。

    setup.files のファイル名と golden: に使い、ディレクトリの外に書かないようにする。
    """
    p = PurePosixPath(name.replace("\\", "/"))
    return bool(name.strip()) and not p.is_absolute() and ":" not in name and ".." not in p.parts


def _check_text_expect(value: Any, loc: str, key: str) -> None:
    """文字列の期待値（そのままの文字列、または {contains: ...} / {regex: ...}）を確かめる。"""
    if isinstance(value, str):
        return
    if isinstance(value, dict) and len(value) == 1 and all(isinstance(k, str) for k in value):
        ((matcher, pattern),) = value.items()
        # 値の中と同じく $contains / $regex と書いてもよい
        matcher = matcher.lstrip("$")
        if matcher in TEXT_MATCHERS and isinstance(pattern, str):
            if matcher == "regex":
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise CasebookError(
                        error("expect_regex", where=loc, key=key, error=e)
                    ) from None
            return
    raise CasebookError(error("expect_text", where=loc, key=key))


def _parse_expect(value: Any, kind: str, loc: str) -> dict[str, Any]:
    """expect: を確かめる（ケースの種類に合う項目か、比べ方の書き方が正しいか）。"""
    if not (isinstance(value, dict) and value and all(isinstance(k, str) for k in value)):
        raise CasebookError(error("expect_mapping", where=loc))
    allowed = EXPECT_KEYS_BY_KIND[kind]
    for key in value:
        if key in RESULT_EXPECT_KEYS and key not in allowed:
            kinds = " / ".join(k for k, keys in EXPECT_KEYS_BY_KIND.items() if key in keys)
            raise CasebookError(error("expect_kind", where=loc, key=key, kinds=kinds))
    if "return" in value and "raises" in value:
        raise CasebookError(error("return_and_raises", where=loc))
    if "exit_code" in value and (
        isinstance(value["exit_code"], bool) or not isinstance(value["exit_code"], int)
    ):
        raise CasebookError(error("exit_code_int", where=loc))
    if "status" in value and (
        isinstance(value["status"], bool) or not isinstance(value["status"], int)
    ):
        raise CasebookError(error("status_int", where=loc))
    for key in TEXT_EXPECT_KEYS:
        if key in value:
            _check_text_expect(value[key], loc, key)
    if "headers" in value:
        headers = value["headers"]
        if not (isinstance(headers, dict) and all(isinstance(k, str) for k in headers)):
            raise CasebookError(error("headers_mapping", where=loc))
        for name, expected in headers.items():
            _check_text_expect(expected, loc, f"headers.{name}")
    # return・json・observe の対象の値の中にある $contains などの書き間違いを探す
    for key, expected in value.items():
        if key in TEXT_EXPECT_KEYS or key in ("headers", "exit_code", "status"):
            continue
        errors = find_matcher_errors(expected, f"expect.{key}")
        if errors:
            raise CasebookError(f"{loc}: {errors[0]}")
    return value


def _str_mapping(value: Any, loc: str, key: str) -> dict[str, str]:
    """ヘッダーのような 名前 -> 文字列 のマッピング（値は文字列にそろえる）。"""
    if value is None:
        return {}
    if not (isinstance(value, dict) and all(isinstance(k, str) for k in value)):
        raise CasebookError(error("name_value_mapping", where=loc, key=key))
    return {k: str(v) for k, v in value.items()}


def _request_defaults(value: Any, where: str) -> dict[str, str]:
    """request_defaults: を確かめ、既定のヘッダーを返す。"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CasebookError(error("request_defaults_mapping", where=where))
    _check_keys(value, {"headers"}, f"{where}: request_defaults")
    return _str_mapping(value.get("headers"), where, "request_defaults.headers")


def _parse_request(value: Any, default_headers: dict[str, str], loc: str) -> HttpRequest:
    """
    request: を確かめて HttpRequest にする。

    `"POST /users"` のような文字列（メソッドを省けば GET）か、method・path・query・
    headers・json・body のマッピングで書く。ヘッダーは request_defaults の headers に
    上書きで重ねる。
    """
    if isinstance(value, str):
        parts = value.split()
        if len(parts) == 1:
            parts = ["GET", *parts]
        if len(parts) != 2:
            raise CasebookError(error("request_form", where=loc))
        value = {"method": parts[0], "path": parts[1]}
    if not isinstance(value, dict):
        raise CasebookError(error("request_type", where=loc))
    _check_keys(value, _REQUEST_KEYS, f"{loc}: request")
    method = _str(value.get("method", "GET"), loc, "request.method", required=True).upper()
    if method not in _HTTP_METHODS:
        raise CasebookError(error("request_method", where=loc, method=method))
    path = _str(value.get("path"), loc, "request.path", required=True)
    if not path.startswith("/"):
        raise CasebookError(error("request_path", where=loc, path=repr(path)))
    query = value.get("query")
    if query is None:
        query = {}
    if not (isinstance(query, dict) and all(isinstance(k, str) for k in query)):
        raise CasebookError(error("query_mapping", where=loc))
    if "json" in value and "body" in value:
        raise CasebookError(error("json_and_body", where=loc))
    own_headers = _str_mapping(value.get("headers"), loc, "request.headers")
    # ヘッダー名は大文字小文字を区別しないので、既定と違う書き方（Authorization と
    # authorization）でも上書きにする（両方送らない）
    overridden = {name.lower() for name in own_headers}
    kept = {k: v for k, v in default_headers.items() if k.lower() not in overridden}
    return HttpRequest(
        method=method,
        path=path,
        query=query,
        headers={**kept, **own_headers},
        json=value.get("json"),
        body=_str(value["body"], loc, "request.body") if "body" in value else None,
    )
