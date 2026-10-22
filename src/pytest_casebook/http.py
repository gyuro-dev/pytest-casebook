"""
The YAML `request:` (an HTTP request) and the resulting response.

pytest-casebook does not send HTTP (it does not depend on any HTTP library). Requests are sent
by your `pytest_casebook_request` hook, using each framework's test client.
Small functions (adapters) for sending are provided for commonly used clients.
An adapter only calls the client's methods and does not import the framework.

```python
from pytest_casebook.http import send_with_httpx_client

def pytest_casebook_request(request, env):
    return send_with_httpx_client(env.client, request)   # FastAPI's TestClient, etc.
```

YAML の `request:`（HTTP のリクエスト）と、その結果のレスポンス。

pytest-casebook は HTTP を送らない（HTTP のライブラリに依存しない）。リクエストを送るのは
利用する側の `pytest_casebook_request` hook で、各フレームワークのテスト用クライアントを使う。
よく使うクライアント向けに、送るための小さな関数（アダプター）を用意している。
アダプターはクライアントのメソッドを呼ぶだけで、フレームワークを import しない。

```python
from pytest_casebook.http import send_with_httpx_client

def pytest_casebook_request(request, env):
    return send_with_httpx_client(env.client, request)   # FastAPI の TestClient など
```
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class HttpRequest:
    """
    A request written in the YAML `request:`.

    YAML の `request:` に書いたリクエスト。
    """

    method: str
    path: str
    query: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    # JSON の本文（json: に書いた値）。None なら JSON を送らない
    json: Any = None
    # JSON 以外の本文（body: に書いた文字列）。None なら送らない。json と同時には書けない
    body: str | None = None

    @property
    def url(self) -> str:
        """
        The path with the query string (e.g. `/users?page=2`).

        クエリ文字列を付けたパス（例: `/users?page=2`）。
        """
        if not self.query:
            return self.path
        return f"{self.path}?{urlencode(self.query, doseq=True)}"

    @property
    def display(self) -> str:
        """
        The notation written in reports and golden files (e.g. `POST /users?page=2`).

        レポートや期待出力に書く表記（例: `POST /users?page=2`）。
        """
        return f"{self.method} {self.url}"


@dataclass(frozen=True)
class HttpResponse:
    """
    The response returned by the `pytest_casebook_request` hook. `headers` maps a header
    name to its value (one value per name).

    `pytest_casebook_request` hook が返すレスポンス。`headers` はヘッダー名 -> 値
    （同じ名前のヘッダーが複数あっても1つだけ）。
    """

    status: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def parse_json(self) -> tuple[bool, Any]:
        """
        Parse the body as JSON.

        :return: `(True, value)` if parsed; `(False, None)` if the body is empty or not JSON

        本文を JSON として読む。

        :return: 読めれば `(True, 値)`、本文が空か JSON でなければ `(False, None)`
        """
        if not self.body.strip():
            return False, None
        try:
            return True, json_module.loads(self.body)
        except ValueError:
            return False, None


def send_with_httpx_client(client: Any, request: HttpRequest) -> HttpResponse:
    """
    Send a request with a client that has the httpx API (httpx, httpx2, etc.).

    Works with FastAPI / Starlette's `TestClient`, `httpx.Client`, and so on.

    :param client: a client with `request(method, url, **kwargs)` (e.g. `TestClient(app)`)
    :param request: the request to send
    :return: the response

    httpx の API を持つクライアント（httpx・httpx2 など）でリクエストを送る。

    FastAPI / Starlette の `TestClient`、`httpx.Client` などに使える。

    :param client: `request(method, url, **kwargs)` を持つクライアント（`TestClient(app)` など）
    :param request: 送るリクエスト
    :return: レスポンス
    """
    kwargs: dict[str, Any] = {}
    if request.headers:
        kwargs["headers"] = request.headers
    if request.query:
        kwargs["params"] = request.query
    if request.json is not None:
        kwargs["json"] = request.json
    elif request.body is not None:
        kwargs["content"] = request.body
    res = client.request(request.method, request.path, **kwargs)
    return HttpResponse(res.status_code, res.text, dict(res.headers))


def send_with_werkzeug_client(client: Any, request: HttpRequest) -> HttpResponse:
    """
    Send a request with Werkzeug's test client.

    Works with Flask's `app.test_client()` and so on.

    :param client: a Werkzeug test client (e.g. `app.test_client()`)
    :param request: the request to send
    :return: the response

    Werkzeug のテスト用クライアントでリクエストを送る。

    Flask の `app.test_client()` などに使える。

    :param client: Werkzeug のテスト用クライアント（`app.test_client()` など）
    :param request: 送るリクエスト
    :return: レスポンス
    """
    kwargs: dict[str, Any] = {"method": request.method}
    if request.headers:
        kwargs["headers"] = request.headers
    if request.query:
        kwargs["query_string"] = request.query
    if request.json is not None:
        kwargs["json"] = request.json
    elif request.body is not None:
        kwargs["data"] = request.body
    res = client.open(request.path, **kwargs)
    return HttpResponse(res.status_code, res.get_data(as_text=True), dict(res.headers))
