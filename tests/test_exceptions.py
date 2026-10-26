"""例外の扱い（run_in_process で出た例外と、expect の raises）の確認。"""

from __future__ import annotations

import sys

import pytest
from helpers import golden, write_casebook

from pytest_casebook import run_in_process

# =============================================================================
# run_in_process
# =============================================================================


def _main(argv: list[str]) -> int:
    print("始めます")
    if argv == ["exit-message"]:
        sys.exit("終了します")
    if argv == ["exit-3"]:
        sys.exit(3)
    if argv == ["boom"]:
        raise ValueError("壊れました")
    return 0


def test_run_in_process_turns_exception_into_exit_code_1() -> None:
    result = run_in_process(_main, ["boom"])
    assert result.exit_code == 1
    assert result.stdout == "始めます\n"
    assert result.stderr == "ValueError: 壊れました\n"


def test_run_in_process_traceback_option() -> None:
    result = run_in_process(_main, ["boom"], traceback=True)
    assert result.exit_code == 1
    assert result.stderr.startswith("Traceback (most recent call last):\n")
    assert result.stderr.endswith("ValueError: 壊れました\n")
    # run_in_process 自身の行は含めず、main から先だけを書く
    assert "runner.py" not in result.stderr
    assert "_main" in result.stderr


@pytest.mark.parametrize(
    ("argv", "code", "stderr"),
    [([], 0, ""), (["exit-3"], 3, ""), (["exit-message"], 1, "終了します\n")],
)
def test_run_in_process_exit(argv: list[str], code: int, stderr: str) -> None:
    result = run_in_process(_main, argv)
    assert (result.exit_code, result.stderr) == (code, stderr)


def test_exception_in_cli_is_recorded_in_golden(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import calc
        from pytest_casebook import run_in_process

        def pytest_casebook_run_command(argv):
            return run_in_process(calc.main, argv[1:])
        """
    )
    write_casebook(
        project,
        """
        command_prefix: calc
        cases:
          - name: not_a_number
            command: 1 x
          - name: not_a_number_expect
            command: 1 x
            expect:
              exit_code: 1
              stderr: {contains: "ValueError: invalid literal"}
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=3)
    assert golden(project, "not_a_number").endswith(
        "# exit_code: 1\n----- stdout -----\n\n----- stderr -----\n"
        "ValueError: invalid literal for int() with base 10: 'x'\n"
    )


# =============================================================================
# expect の raises（継承した例外も一致させる）
# =============================================================================

ERRORS_MODULE = """
class AppError(Exception):
    pass


class NotFound(AppError):
    pass


class Outer:
    class Inner(Exception):
        pass


def not_found():
    raise NotFound("ユーザーがいません")


def inner():
    raise Outer.Inner("中の例外")
"""


@pytest.mark.parametrize(
    ("call", "raises"),
    [
        ("not_found", "NotFound"),
        ("not_found", "AppError"),  # 親クラスでも一致する
        ("not_found", "Exception"),
        ("not_found", "errors.NotFound"),  # モジュール名付き
        ("not_found", "errors.AppError"),
        ("not_found", "NotFound: ユーザーがいません"),
        ("not_found", "AppError: ユーザーがいません"),  # 型は継承で、メッセージは完全一致
        ("inner", "Outer.Inner"),  # クラスの中のクラス
        ("inner", "Inner"),
    ],
)
def test_raises_matches_type_or_its_parents(
    project: pytest.Pytester, call: str, raises: str
) -> None:
    project.makepyfile(errors=ERRORS_MODULE)
    write_casebook(
        project,
        f"""
        cases:
          - name: case
            call: errors:{call}
            expect:
              raises: "{raises}"
        """,
    )
    project.runpytest().assert_outcomes(passed=2)


def test_nested_exception_class_is_shown_with_its_outer_class(project: pytest.Pytester) -> None:
    """
    クラスの中の例外は、期待出力・比べ方・失敗の説明のどれでも `Outer.Inner` と書く
    （raises: "Outer.Inner" で一致するのと同じ名前）。
    """
    project.makepyfile(errors=ERRORS_MODULE)
    write_casebook(
        project,
        """
        cases:
          - name: golden
            call: errors:inner
          - name: with_message
            call: errors:inner
            expect: {raises: "Outer.Inner: 中の例外"}
          - name: contains
            call: errors:inner
            expect: {raises: {contains: "Outer.Inner: 中"}}
          - name: other_message
            call: errors:inner
            expect: {raises: "Outer.Inner: 違う"}
        """,
    )
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=4, failed=1)
    assert golden(project, "golden").endswith("----- raises -----\nOuter.Inner: 中の例外\n")
    result.stdout.fnmatch_lines(['*実際 "Outer.Inner: 中の例外"*'])


@pytest.mark.parametrize(
    "raises",
    [
        "KeyError",  # 関係のない型
        "ValueError",
        "other.NotFound",  # モジュールが違う
        "NotFound: 違うメッセージ",
        "AppError:",  # メッセージが空のはず、と書いたことになる
    ],
)
def test_raises_mismatch(project: pytest.Pytester, raises: str) -> None:
    project.makepyfile(errors=ERRORS_MODULE)
    write_casebook(
        project,
        f"""
        cases:
          - name: case
            call: errors:not_found
            expect:
              raises: "{raises}"
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(
        [f'*raises: 期待 "{raises}" / 実際 "NotFound: ユーザーがいません"*']
    )
