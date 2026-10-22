"""
call: と request: のケースの timeout の確認。

時間切れのケースの関数・hook は止められず、裏のスレッド（daemon）で動き続ける。テストが遅く
ならないよう、時間切れにするものは 0.2 秒で打ち切り、裏では 1 秒だけ眠らせる。
"""

from __future__ import annotations

import sys
import threading

import pytest
from helpers import write_casebook

from pytest_casebook.runner import WorkerTimeout, invoke, run_with_timeout

SLOW_MODULE = """
import asyncio
import contextvars
import threading
import time

VAR = contextvars.ContextVar("var", default="unset")
RELEASE = threading.Event()


def wait():
    time.sleep(1)
    return "late"


def quick(text):
    print(text)
    print("err", file=__import__("sys").stderr)
    return len(text)


def in_main_thread():
    return threading.current_thread() is threading.main_thread()


def read_var():
    return VAR.get()


def held():
    # 時間切れのあと、次のケースの途中で終わる（取り込みを書き戻さないことの確認に使う）
    RELEASE.wait(5)
    return "held"


def release_and_print():
    RELEASE.set()
    time.sleep(0.2)
    print("after")


async def aio_add(a, b):
    await asyncio.sleep(0)
    return a + b


async def aio_wait():
    await asyncio.sleep(1)
"""


@pytest.fixture
def slow(project: pytest.Pytester) -> pytest.Pytester:
    project.makepyfile(slow=SLOW_MODULE)
    return project


# =============================================================================
# call
# =============================================================================


def test_call_timeout_fails_the_case(slow: pytest.Pytester) -> None:
    write_casebook(slow, "cases:\n  - {name: hang, call: 'slow:wait', timeout: 0.2}\n")
    result = slow.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    message = (
        "call: slow:wait が 0.2 秒以内に終わりませんでした"
        "（関数は止められないため、裏で動き続けます）"
    )
    result.stdout.fnmatch_lines([f"*[[]hang[]] {message}*"])


def test_call_timeout_message_in_english(slow: pytest.Pytester) -> None:
    write_casebook(slow, "cases:\n  - {name: hang, call: 'slow:wait', timeout: 0.2}\n")
    result = slow.runpytest("-o", "casebook_lang=en")
    result.assert_outcomes(failed=1, passed=1)
    message = (
        "call: slow:wait did not finish within 0.2 seconds "
        "(the function cannot be stopped and keeps running in the background)"
    )
    result.stdout.fnmatch_lines([f"*[[]hang[]] {message}*"])


def test_call_within_timeout_keeps_output(slow: pytest.Pytester) -> None:
    write_casebook(
        slow,
        """
        cases:
          - name: quick
            call: slow:quick
            args: [abc]
            timeout: 5
            expect: {return: 3, stdout: "abc\\n", stderr: "err\\n"}
          - name: async_add
            call: slow:aio_add
            args: [1, 2]
            timeout: 5
            expect: {return: 3}
          - name: async_hang
            call: slow:aio_wait
            timeout: 0.2
        """,
    )
    result = slow.runpytest()
    result.assert_outcomes(passed=3, failed=1)
    result.stdout.fnmatch_lines(["*[[]async_hang[]] call: slow:aio_wait が 0.2 秒以内に*"])


def test_call_with_timeout_runs_in_a_worker_thread(slow: pytest.Pytester) -> None:
    # timeout がなければ、今までどおりスレッドを使わない
    slow.makeconftest(
        """
        import slow

        def pytest_casebook_prepare_call(case):
            slow.VAR.set(case.name)
        """
    )
    write_casebook(
        slow,
        """
        cases:
          - {name: plain, call: 'slow:in_main_thread', expect: {return: true}}
          - {name: threaded, call: 'slow:in_main_thread', timeout: 5, expect: {return: false}}
          - {name: context, call: 'slow:read_var', timeout: 5, expect: {return: context}}
        """,
    )
    slow.runpytest().assert_outcomes(passed=4)


def test_late_finish_does_not_break_later_capture(slow: pytest.Pytester) -> None:
    # held は時間切れのあと、release_and_print の途中で終わる。そのとき sys.stdout を
    # 書き戻すと、release_and_print の出力が取り込めなくなる
    write_casebook(
        slow,
        """
        cases:
          - {name: a_held, call: 'slow:held', timeout: 0.2}
          - {name: b_after, call: 'slow:release_and_print', expect: {stdout: "after\\n"}}
        """,
    )
    result = slow.runpytest()
    result.assert_outcomes(failed=1, passed=2)
    result.stdout.fnmatch_lines(["*[[]a_held[]] call: slow:held が 0.2 秒以内に*"])


# =============================================================================
# request
# =============================================================================

REQUEST_CONFTEST = """
import time

from pytest_casebook import HttpResponse


def pytest_casebook_request(request):
    if request.path == "/slow":
        time.sleep(1)
    return HttpResponse(200, "ok")
"""


def test_request_timeout(project: pytest.Pytester) -> None:
    project.makeconftest(REQUEST_CONFTEST)
    write_casebook(
        project,
        """
        cases:
          - {name: fast, request: /fast, timeout: 5, expect: {status: 200, body: ok}}
          - {name: hang, request: GET /slow, timeout: 0.2, expect: {status: 200}}
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(failed=1, passed=2)
    message = (
        "request: GET /slow が 0.2 秒以内に終わりませんでした"
        "（pytest_casebook_request hook は止められないため、裏で動き続けます）"
    )
    result.stdout.fnmatch_lines([f"*[[]hang[]] {message}*"])


# =============================================================================
# runner
# =============================================================================


def test_invoke_restores_stdout_after_timeout() -> None:

    release = threading.Event()
    before = sys.stdout, sys.stderr
    with pytest.raises(WorkerTimeout):
        invoke(release.wait, [5], {}, timeout=0.05)
    assert (sys.stdout, sys.stderr) == before
    release.set()


def test_run_with_timeout_reraises_errors() -> None:
    def boom() -> None:
        raise SystemExit(3)

    with pytest.raises(SystemExit) as exc_info:
        run_with_timeout(boom, 5)
    assert exc_info.value.code == 3
    assert run_with_timeout(lambda: 42, 5) == 42
