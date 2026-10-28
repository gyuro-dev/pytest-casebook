"""
Hooks called by pytest-casebook. Implement one by writing a function of the same name in
conftest.py.

Every hook receives its arguments by name, so declare only the ones you use
(e.g. `def pytest_casebook_placeholders(env): ...`). Common arguments:

- `case`: the case being run (`pytest_casebook.Case`)
- `env`: the value of the `casebook_env` fixture (override it in conftest.py)
- `workdir`: the per-case working directory, or None when the case has none
- `config`: the pytest config, or None when the case is run outside pytest by
  `pytest_casebook.run_case()`

The same hooks are called by `run_case()` when they are attributes of its `hooks` argument
(e.g. an imported conftest module), so a hook that reads `config` should allow None.

pytest-casebook が呼ぶ hook。利用する側は conftest.py に同じ名前の関数を書いて実装する。

どの hook も引数は名前で受け取るため、使う引数だけを書けばよい
（例: `def pytest_casebook_placeholders(env): ...`）。共通の引数:

- `case`: 実行中のケース（`pytest_casebook.Case`）
- `env`: `casebook_env` fixture の値（conftest.py で上書きして用意する）
- `workdir`: ケースごとの作業ディレクトリ（なければ None）
- `config`: pytest の config。pytest の外で `pytest_casebook.run_case()` が実行するときは None

`run_case()` も、`hooks` 引数（import した conftest モジュールなど）の属性にある同じ hook を
呼ぶ。そのため `config` を使う hook は、None でも動くように書く。
"""

from __future__ import annotations

import re
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pluggy

if TYPE_CHECKING:
    import pytest

    from .http import HttpRequest, HttpResponse
    from .model import Case
    from .runner import CommandResult

hookspec = pluggy.HookspecMarker("pytest")


@hookspec(firstresult=True)
def pytest_casebook_run_command(
    case: Case, argv: list[str], env: Any, cwd: Path, config: pytest.Config | None
) -> CommandResult | tuple[int, str, str] | None:
    """
    Run a command case.

    Return None to use the default (run `argv` in a subprocess, applying `case.stdin`
    and `case.timeout`). To run the CLI in-process, return
    `pytest_casebook.run_in_process(main, argv[1:], stdin=case.stdin)`.

    The environment variables from `env:` (`case.env`) are already put over `os.environ`
    while the case runs, so a CLI run in-process sees them too. The contents of
    `stdin_file:` are already in `case.stdin`.

    For cases with a per-case working directory, this hook is called with the current
    directory changed to it (the same as `cwd`).

    :param argv: the argument list made of `command_prefix` and the command
    :param cwd: the directory to run in (the working directory, or else the directory of the
        case file)
    :return: a `CommandResult` or an `(exit_code, stdout, stderr)` tuple, or None to use the
        default

    command のケースを実行する。

    None を返すと、標準の方法（`argv` を別プロセスで実行し、`case.stdin`・`case.timeout` を
    当てる）になる。同じプロセスで CLI を動かすときは
    `pytest_casebook.run_in_process(main, argv[1:], stdin=case.stdin)` を返す。

    env: の環境変数（`case.env`）は、ケースを実行する間 os.environ に重ねてあるので、
    同じプロセスで動かす CLI からも見える。`stdin_file:` の中身は `case.stdin` に入っている。

    ケースごとの作業ディレクトリがあるケースでは、この hook はそのディレクトリ（`cwd` と同じ）に
    移動した状態で呼ばれる。

    :param argv: `command_prefix` と command を合わせた引数のリスト
    :param cwd: 実行するディレクトリ（作業ディレクトリ、なければケースファイルのあるディレクトリ）
    :return: `CommandResult` か `(終了コード, stdout, stderr)` のタプル。None なら標準の方法
    """


@hookspec(firstresult=True)
def pytest_casebook_request(
    case: Case, request: HttpRequest, env: Any, workdir: Path | None, config: pytest.Config | None
) -> HttpResponse | None:
    """
    Send the HTTP request of a request: case and return the response.

    pytest-casebook does not send HTTP itself, so this hook is required when using request:.
    With your framework's test client and an adapter from `pytest_casebook.http`, it takes
    only a few lines. For cases with a per-case working directory, this hook is called with
    the current directory changed to it. If the case has `timeout:`, this hook is called in a
    separate thread, and the case fails if it does not return in time (the hook is not
    stopped and keeps running in the background).

    ```python
    from pytest_casebook.http import send_with_httpx_client

    def pytest_casebook_request(request, env):
        return send_with_httpx_client(env.client, request)
    ```

    :param request: the request: from the YAML (with the request_defaults headers merged in)
    :return: the response (if every implementation returns None, the case fails)

    request: のケースの HTTP リクエストを送り、レスポンスを返す。

    pytest-casebook は HTTP を送らないので、request: を使うときはこの hook が必要。
    フレームワークのテスト用クライアントと、`pytest_casebook.http` のアダプターを使えば
    数行で書ける。作業ディレクトリがあるケースでは、そのディレクトリに移動した状態で呼ばれる。
    ケースに `timeout:` があると、この hook は別のスレッドで呼ばれ、時間内に返らなければケースは
    失敗する（hook は止まらず、裏で動き続ける）。

    ```python
    from pytest_casebook.http import send_with_httpx_client

    def pytest_casebook_request(request, env):
        return send_with_httpx_client(env.client, request)
    ```

    :param request: YAML の request: の内容（request_defaults のヘッダーを重ねたもの）
    :return: レスポンス（どの実装も None を返すと、ケースは失敗する）
    """


@hookspec
def pytest_casebook_prepare_call(
    case: Case,
    env: Any,
    args: list[Any],
    kwargs: dict[str, Any],
    workdir: Path | None,
    config: pytest.Config | None,
) -> None:
    """
    Modify `args` and `kwargs` in place before the function of a call case is called.

    :param args: the args from the YAML (a copy; modify it in place)
    :param kwargs: the kwargs from the YAML (a copy; modify it in place)

    call のケースで関数を呼ぶ前に、`args` と `kwargs` をその場で書き換える。

    :param args: YAML の args（複製。その場で書き換える）
    :param kwargs: YAML の kwargs（複製。その場で書き換える）
    """


@hookspec
def pytest_casebook_setup(
    case: Case, data: dict[str, Any], env: Any, workdir: Path | None, config: pytest.Config | None
) -> AbstractContextManager[Any] | None:
    """
    Prepare a case's preconditions (insert rows into a DB, change the state of a mock, etc.).
    Called before every case (`data` is empty when there is neither setup: nor states:), so
    cleanup in the returned context manager runs every time and no effect of the previous case
    remains.

    `data` is the case's state (the one in `states:` selected by `state:`) overlaid with the
    case's `setup:`. `files` are created in the working directory before the call, so they are
    not included in `data`. Return a context manager when cleanup is needed (it exits after
    observe).

    :param data: the state and the case's setup: merged, without files
    :param workdir: the per-case working directory (None unless the case writes setup
        `files:`, even `files: {}`, or fetches `files` in observe: or expect:)
    :return: a context manager for cleanup, or None. Every implementation is called and every
        returned context manager is entered

    ケースの前提条件の準備をする（DB に行を入れる、モックの状態を変えるなど）。
    すべてのケースの前に呼ぶ（setup: も states: もなければ `data` は空）。そのため、
    返したコンテキストマネージャでの後片付けは毎回行われ、前のケースの影響が残らない。

    `data` は、ケースの状態（`states:` のうち `state:` で選んだもの）に、ケースの `setup:` を
    上書きで重ねたもの。`files` は呼ぶ前に作業ディレクトリに作ってあるため、`data` には含まない。
    後片付けが要るときはコンテキストマネージャを返す（observe のあとに抜ける）。

    :param data: 状態とケースの setup: を重ねた内容から files を除いたもの
    :param workdir: ケースごとの作業ディレクトリ（setup に files: を書いておらず
        （`files: {}` も書いたうちに入る）、observe: / expect: の files もなければ None）
    :return: 後片付け用のコンテキストマネージャか None。すべての実装を呼び、返したものを
        すべて使う
    """


@hookspec(firstresult=True)
def pytest_casebook_observe(
    target: str, case: Case, env: Any, workdir: Path | None, config: pytest.Config | None
) -> Any:
    """
    After the run, fetch and return the value of `target`.

    If a list is returned, each element is written as one line in the golden file. Sort the
    rows in the hook so their order does not change between runs (e.g. add `order by`).
    The built-in target `files` (files in the working directory) is fetched without calling
    this hook.

    :param target: the name written in observe: or expect: (e.g. `db.users`)
    :return: the value (if every implementation returns None, the case fails as an unknown
        target)

    実行後に `target` の値を取り出して返す。

    リストを返すと、期待出力には要素1つを1行で書く。行の並び順は実行ごとに変わらないよう
    hook の側でそろえる（`order by` を付けるなど）。組み込みの対象 `files`
    （作業ディレクトリのファイル）は、この hook を呼ばずに取り出す。

    :param target: observe: や expect: に書いた名前（例: `db.users`）
    :return: 取り出した値（どの実装も None を返すと、取り出せないものとして失敗する）
    """


@hookspec
def pytest_casebook_placeholders(env: Any, config: pytest.Config | None) -> list[tuple[str, str]]:
    """
    Return values to replace in the output, such as IDs that change on every run. The results
    of every implementation are combined.

    :return: a list of `(actual value, replacement)` pairs

    出力中の値を置き換える組を返す（実行ごとに変わる ID など）。すべての実装の結果を
    つなげて使う。

    :return: `(実際の値, 置き換え後)` のリスト
    """


@hookspec
def pytest_casebook_patterns(
    env: Any, config: pytest.Config | None
) -> list[tuple[str | re.Pattern[str], str]]:
    """
    Return regex replacements to apply to the output. The results of every implementation are
    combined and applied after the placeholders.

    :return: a list of `(regex, replacement)` pairs (a regex may be a string or a compiled
        pattern)

    出力に当てる正規表現の置き換えを返す。すべての実装の結果をつなげ、placeholders の
    あとに当てる。

    :return: `(正規表現, 置き換え後)` のリスト（正規表現は文字列でもコンパイル済みでもよい）
    """
