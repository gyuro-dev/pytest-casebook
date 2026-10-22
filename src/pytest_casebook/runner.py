"""ケースの実行（CLI の実行と Python 関数の呼び出し）。"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import io
import os
import shutil
import subprocess
import sys
import traceback as tb_module
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .messages import error
from .serialize import describe_exception


class CasebookRunError(Exception):
    """ケースを実行できなかった（コマンドが見つからない、関数を import できないなど）。"""


@dataclass(frozen=True)
class CommandResult:
    """
    The result of running a CLI.

    CLI を実行した結果。
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class CallResult:
    """Python 関数を呼んだ結果。例外が出たときは `error` に入る。"""

    value: Any = None
    error: BaseException | None = None
    stdout: str = ""
    stderr: str = ""


def run_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    stdin: str | None = None,
    timeout: float | None = None,
    encoding: str = "utf-8",
) -> CommandResult:
    """
    コマンドを別プロセスで実行する。

    :param argv: 実行する引数のリスト（先頭がプログラム。パスを含まない名前なら PATH から探す）
    :param cwd: 実行するディレクトリ
    :param stdin: 標準入力に渡す文字列（None なら空の入力）
    :param timeout: 打ち切るまでの秒数
    :param encoding: 出力の文字コード
    :return: 終了コード・stdout・stderr
    :raises CasebookRunError: コマンドが見つからない、または時間内に終わらないとき
    """
    # 子プロセスが Python のとき、Windows でもコンソールの文字コード（cp932 など）ではなく
    # 読み取る側と同じ文字コードで出力させる（利用者が設定していればそれを使う）
    env = {"PYTHONIOENCODING": encoding, **os.environ}
    try:
        proc = subprocess.run(
            [_find_program(argv[0], env), *argv[1:]],
            cwd=cwd,
            env=env,
            input=stdin,
            # 入力を渡さないときは空にし、子プロセスが端末の入力を待って止まらないようにする
            stdin=subprocess.DEVNULL if stdin is None else None,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise CasebookRunError(error("command_not_found", program=argv[0])) from None
    except subprocess.TimeoutExpired:
        raise CasebookRunError(error("command_timeout", timeout=timeout, argv=list(argv))) from None
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def _find_program(name: str, env: dict[str, str]) -> str:
    """
    パスを含まないプログラム名を、PATH から探したフルパスにする（見つからなければそのまま）。

    Windows は、PATH より先に、親プロセスの実行ファイルがあるディレクトリを探す（仮想環境
    では、元の Python のディレクトリになる）。そのため `python` が仮想環境ではなく元の
    Python になり、仮想環境のパッケージ（coverage など）が使えない。どの OS でも PATH の
    順に探すよう、先に探しておく。
    """
    if os.sep in name or (os.altsep and os.altsep in name):
        return name
    return shutil.which(name, path=env.get("PATH")) or name


@contextlib.contextmanager
def _capture(stdin: str | None = None) -> Iterator[tuple[io.StringIO, io.StringIO]]:
    """stdout / stderr を取り込む（stdin を渡せば sys.stdin も差し替え、抜けるときに戻す）。"""
    out, err = io.StringIO(), io.StringIO()
    original_stdin = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield out, err
    finally:
        sys.stdin = original_stdin


def run_in_process(
    main: Callable[..., Any],
    argv: Sequence[str],
    *,
    stdin: str | None = None,
    traceback: bool = False,
) -> CommandResult:
    """
    Call a CLI's main function in-process, capture stdout / stderr, and return them.

    Use this inside the `pytest_casebook_run_command` hook to run a CLI without starting a
    subprocess (a mocked environment can be passed to the CLI as is). To get the same
    result as running in a subprocess:

    - `sys.exit()` uses its value as the exit code
    - any other exception is caught; the exit code becomes 1 and the exception is written to
      stderr

    :param main: a function callable as `main(argv)` (its return value or SystemExit is the
        exit code)
    :param argv: arguments passed to main (without the program name)
    :param stdin: a string passed to standard input (None leaves `sys.stdin` unchanged)
    :param traceback: if True, write the full exception traceback to stderr. If False
        (default), write only one line, `TypeName: message` (it has no line numbers or paths,
        so golden files are less likely to change)
    :return: exit code, stdout, and stderr

    CLI の main 関数を同じプロセスの中で呼び、stdout / stderr を取り込んで返す。

    `pytest_casebook_run_command` hook の中で、別プロセスを立てずに CLI を動かすときに使う
    （モックした環境をそのまま CLI に渡せる）。別プロセスで実行したときと同じ結果になるよう、
    次のように扱う。

    - `sys.exit()` は、その値を終了コードにする
    - それ以外の例外は受け止めて、終了コードを 1 にし、例外を stderr に書く

    :param main: `main(argv)` の形で呼べる関数（戻り値または SystemExit が終了コード）
    :param argv: main に渡す引数（プログラム名を含まない）
    :param stdin: 標準入力に渡す文字列（None なら sys.stdin を変えない）
    :param traceback: True なら例外のトレースバック全体を stderr に書く。False（既定）なら
        `型名: メッセージ` の1行だけを書く（行番号やパスが入らないため、期待出力が変わりにくい）
    :return: 終了コード・stdout・stderr
    """
    with _capture(stdin) as (out, err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
        # 別プロセスで動かしたときと同じく、どんな例外も終了コード 1 にする
        except Exception as e:  # noqa: BLE001
            if traceback:
                # この関数の呼び出しの行は除き、main から先だけを書く
                tb = e.__traceback__.tb_next if e.__traceback__ is not None else None
                tb_module.print_exception(type(e), e, tb, file=sys.stderr)
            else:
                print(describe_exception(e), file=sys.stderr)
            code = 1
        if code is not None and not isinstance(code, int):
            # sys.exit("メッセージ") と同じく、メッセージを stderr に出して終了コード 1 にする
            print(code, file=sys.stderr)
            code = 1
    return CommandResult(code or 0, out.getvalue(), err.getvalue())


def import_callable(spec: str) -> Callable[..., Any]:
    """
    `"パッケージ.モジュール:関数"` の形の文字列から関数を取り出す
    （`"モジュール:クラス.メソッド"` も可）。

    :param spec: YAML の call: に書いた文字列
    :return: 呼び出せるオブジェクト
    :raises CasebookRunError: import できない、または呼べないとき
    """
    module_name, _, attr_path = spec.partition(":")
    try:
        obj: Any = importlib.import_module(module_name)
    except ImportError as e:
        raise CasebookRunError(error("import_failed", module=module_name, error=e)) from e
    for attr in attr_path.split("."):
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            raise CasebookRunError(error("attr_missing", spec=spec, attr=attr)) from None
    if not callable(obj):
        raise CasebookRunError(error("not_callable", spec=spec))
    return cast("Callable[..., Any]", obj)


def invoke(func: Callable[..., Any], args: list[Any], kwargs: dict[str, Any]) -> CallResult:
    """
    関数を呼び、戻り値または例外と、その間に出た stdout / stderr を返す。

    `async def` の関数（戻り値が coroutine）は、終わるまで待ってから結果を返す。
    受け止めるのは Exception だけ（SystemExit などはそのまま上げる）。
    """
    with _capture() as (out, err):
        try:
            value = func(*args, **kwargs)
            if inspect.iscoroutine(value):
                value = asyncio.run(value)
        # 例外も結果の1つとして、期待値（raises）と比べる
        except Exception as e:  # noqa: BLE001
            return CallResult(error=e, stdout=out.getvalue(), stderr=err.getvalue())
    return CallResult(value=value, stdout=out.getvalue(), stderr=err.getvalue())
