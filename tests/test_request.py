"""
request:（HTTP のリクエスト）のケースの確認。

HTTP はフレームワークなしの小さな「アプリ」（conftest.py の中の関数）で返す。
FastAPI / Flask で実際に動くことは、入っているときだけ確かめる。
"""

from __future__ import annotations

import textwrap
from typing import Any

import pytest
from helpers import golden, write_casebook

from pytest_casebook import HttpRequest, HttpResponse
from pytest_casebook.http import send_with_httpx_client, send_with_werkzeug_client

# リクエストをそのまま返したり、決まった答えを返したりする小さなアプリ
APP_CONFTEST = """
import json

from pytest_casebook import HttpResponse

USERS = {1: {"id": 1, "name": "佐藤"}}


def pytest_casebook_request(request):
    if request.path == "/echo":
        body = {
            "method": request.method,
            "url": request.url,
            "headers": request.headers,
            "json": request.json,
            "body": request.body,
        }
        return HttpResponse(200, json.dumps(body, ensure_ascii=False))
    if request.path == "/text":
        return HttpResponse(200, "ok\\n", {"Content-Type": "text/plain", "X-Trace": "abc-123"})
    if request.method == "POST" and request.path == "/users":
        user = {"id": 2, "created_at": "2026-10-19T12:00:00Z", **request.json}
        return HttpResponse(201, json.dumps(user, ensure_ascii=False), {"Location": "/users/2"})
    if request.path.startswith("/users/"):
        user = USERS.get(int(request.path.rsplit("/", 1)[1]))
        if user is None:
            return HttpResponse(404, json.dumps({"detail": "見つかりません"}, ensure_ascii=False))
        return HttpResponse(200, json.dumps(user, ensure_ascii=False))
    return HttpResponse(404, "")
"""


@pytest.fixture
def app(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makeconftest(APP_CONFTEST)
    pytester.makeini("[pytest]\ncasebook_lang = ja\n")
    return pytester


# =============================================================================
# 期待出力ファイル
# =============================================================================


def test_golden_for_json_and_text(app: pytest.Pytester) -> None:
    write_casebook(
        app,
        """
        cases:
          - name: create
            request:
              method: POST
              path: /users
              json: {name: 鈴木}
          - name: text
            request: /text
          - name: missing
            request: GET /users/9
        """,
    )
    app.runpytest("--casebook-update").assert_outcomes(passed=4)
    assert golden(app, "create") == textwrap.dedent(
        """\
        # case: create
        # request: POST /users
        # status: 201
        ----- json -----
        {
          "id": 2,
          "created_at": "<datetime>",
          "name": "鈴木"
        }
        """
    )
    assert golden(app, "text").endswith("# status: 200\n----- body -----\nok\n")
    assert "# status: 404" in golden(app, "missing")
    app.runpytest().assert_outcomes(passed=4)


def test_handwritten_golden_body_is_json(app: pytest.Pytester) -> None:
    write_casebook(app, "cases:\n  - name: user\n    request: GET /users/1\n")
    path = app.path / "golden" / "casebook_calc" / "user.txt"
    path.parent.mkdir(parents=True)
    path.write_text('# status: 200\n{"id": 1, "name": "佐藤"}\n', encoding="utf-8")
    # 見出しのない本文は json として扱う（整形の違いは、作り直した JSON と比べるので問わない）
    result = app.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    path.write_text('# status: 200\n{\n  "id": 1,\n  "name": "佐藤"\n}\n', encoding="utf-8")
    app.runpytest().assert_outcomes(passed=2)


# =============================================================================
# expect
# =============================================================================


def test_expect_status_json_body_headers(app: pytest.Pytester) -> None:
    write_casebook(
        app,
        """
        cases:
          - name: create
            request: {method: POST, path: /users, json: {name: 鈴木}}
            expect:
              status: 201
              json: {name: 鈴木}            # 書いたキーだけ（id や created_at は書かなくてよい）
              headers: {location: /users/2} # ヘッダー名は大文字小文字を区別しない
          - name: text
            request: /text
            expect:
              status: 200
              body: ok
              headers:
                Content-Type: {contains: text/plain}
                X-Trace: {regex: '^abc-\\d+$'}
        """,
    )
    app.runpytest().assert_outcomes(passed=3)


def test_expect_failure_is_readable(app: pytest.Pytester) -> None:
    write_casebook(
        app,
        """
        cases:
          - name: wrong
            request: GET /users/1
            expect:
              status: 201
              json: {name: 鈴木}
              headers: {X-Missing: a}
          - name: not_json
            request: /text
            expect:
              json: {a: 1}
        """,
    )
    result = app.runpytest()
    result.assert_outcomes(failed=2, passed=1)
    result.stdout.fnmatch_lines(
        [
            "*- status: 期待 201 / 実際 200",
            '*- json.name: 期待 "鈴木" / 実際 "佐藤"',
            "*- headers.X-Missing: レスポンスにありません",
            "*----- 実際の json -----",
            '*"name": "佐藤"*',
            '*- json: 本文が JSON ではありません（本文 "ok\\n"）',
        ]
    )


# =============================================================================
# リクエストの書き方
# =============================================================================


def test_request_forms_and_defaults(app: pytest.Pytester) -> None:
    write_casebook(
        app,
        """
        request_defaults:
          headers: {Authorization: Bearer test-token, X-Client: casebook}
        cases:
          - name: shorthand
            request: /echo
            expect:
              json:
                method: GET
                url: /echo
                headers: {Authorization: Bearer test-token, X-Client: casebook}
          - name: full
            request:
              method: put
              path: /echo
              query: {page: 2, tag: [a, b]}
              headers: {X-Client: override}
              body: raw text
            expect:
              json:
                method: PUT
                url: /echo?page=2&tag=a&tag=b
                headers: {Authorization: Bearer test-token, X-Client: override}
                body: raw text
                json: null
        """,
    )
    app.runpytest().assert_outcomes(passed=3)


def test_request_without_hook_fails(pytester: pytest.Pytester) -> None:
    write_casebook(pytester, "cases:\n  - name: a\n    request: /x\n    expect: {status: 200}\n")
    result = pytester.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(["*write a pytest_casebook_request hook in conftest.py*"])


def test_request_hook_must_return_http_response(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("def pytest_casebook_request(request):\n    return 200\n")
    write_casebook(pytester, "cases:\n  - name: a\n    request: /x\n    expect: {status: 200}\n")
    result = pytester.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(["*must return an HttpResponse (returned: int)*"])


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("request: FETCH /x", "HTTP のメソッドではありません: FETCH"),
        ("request: users", "request.path は / で始めてください"),
        ("request: GET /x extra", "'メソッド パス'"),
        ("request: {path: /x, json: {}, body: a}", "json と body のどちらか一方"),
        ("request: {path: /x, data: a}", "知らないキーがあります: data"),
        ("request: /x\n    expect: {exit_code: 0}", "expect.exit_code は command のケースにだけ"),
        ("request: /x\n    expect: {status: '200'}", "expect.status は整数で書いてください"),
        ("call: m:f\n    expect: {status: 200}", "expect.status は request のケースにだけ"),
        ("request: /x\n    args: [1]", "args / kwargs は call のケースにだけ"),
    ],
)
def test_invalid_request(pytester: pytest.Pytester, case: str, message: str) -> None:
    pytester.makeini("[pytest]\ncasebook_lang = ja\n")
    write_casebook(pytester, f"cases:\n  - name: a\n    {case}\n")
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*{message}*"])


def test_http_request_url() -> None:
    assert HttpRequest("GET", "/a").url == "/a"
    assert HttpRequest("GET", "/a", query={"q": "日本"}).url == "/a?q=%E6%97%A5%E6%9C%AC"
    assert HttpRequest("POST", "/a", query={"x": 1}).display == "POST /a?x=1"


def test_http_response_parse_json() -> None:
    assert HttpResponse(200, '{"a": 1}').parse_json() == (True, {"a": 1})
    assert HttpResponse(200, "ok").parse_json() == (False, None)
    assert HttpResponse(204, "").parse_json() == (False, None)


# =============================================================================
# アダプター（フレームワークを import せず、クライアントのメソッドを呼ぶだけ）
# =============================================================================


class _Res:
    def __init__(self) -> None:
        self.status_code = 201
        self.text = '{"ok": true}'
        self.headers = {"Content-Type": "application/json"}

    def get_data(self, as_text: bool) -> str:
        return self.text


class _FakeHttpxClient:
    def request(self, method: str, url: str, **kwargs: Any) -> _Res:
        self.called = (method, url, kwargs)
        return _Res()


class _FakeWerkzeugClient:
    def open(self, path: str, **kwargs: Any) -> _Res:
        self.called = (path, kwargs)
        return _Res()


REQ = HttpRequest("POST", "/u", query={"a": 1}, headers={"X": "1"}, json={"n": 1})


def test_send_with_httpx_client() -> None:
    client = _FakeHttpxClient()
    res = send_with_httpx_client(client, REQ)
    assert res == HttpResponse(201, '{"ok": true}', {"Content-Type": "application/json"})
    assert client.called == (
        "POST",
        "/u",
        {"headers": {"X": "1"}, "params": {"a": 1}, "json": {"n": 1}},
    )
    send_with_httpx_client(client, HttpRequest("PUT", "/b", body="raw"))
    assert client.called == ("PUT", "/b", {"content": "raw"})


def test_send_with_werkzeug_client() -> None:
    client = _FakeWerkzeugClient()
    res = send_with_werkzeug_client(client, REQ)
    assert res.status == 201
    assert client.called == (
        "/u",
        {"method": "POST", "headers": {"X": "1"}, "query_string": {"a": 1}, "json": {"n": 1}},
    )
    send_with_werkzeug_client(client, HttpRequest("PUT", "/b", body="raw"))
    assert client.called == ("/b", {"method": "PUT", "data": "raw"})


# =============================================================================
# 実際のフレームワーク（入っているときだけ）
# =============================================================================


def test_fastapi_test_client() -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    app = fastapi.FastAPI()

    @app.post("/items")
    def create(item: dict[str, Any], q: str = "") -> dict[str, Any]:
        return {"item": item, "q": q}

    res = send_with_httpx_client(
        TestClient(app), HttpRequest("POST", "/items", query={"q": "x"}, json={"n": 1})
    )
    assert res.status == 200
    assert res.parse_json() == (True, {"item": {"n": 1}, "q": "x"})


def test_flask_test_client() -> None:
    flask = pytest.importorskip("flask")
    app = flask.Flask(__name__)

    @app.post("/items")
    def create() -> Any:
        return {"item": flask.request.get_json(), "q": flask.request.args.get("q")}, 201

    res = send_with_werkzeug_client(
        app.test_client(), HttpRequest("POST", "/items", query={"q": "x"}, json={"n": 1})
    )
    assert res.status == 201
    assert res.parse_json() == (True, {"item": {"n": 1}, "q": "x"})
