"""
request: を送る hook（pytest_casebook_request）の最小の形。

pytest-casebook は HTTP を送らない。request: のケースでは、この hook が
HttpRequest（YAML の request: の内容）を受け取り、HttpResponse を返す。
FastAPI や Flask のときは、それぞれのテスト用クライアントで送る（15_fastapi / 16_flask）。
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from typing import Any

import todo_service

from pytest_casebook import HttpRequest, HttpResponse


def pytest_casebook_request(request: HttpRequest) -> HttpResponse:
    status, value = todo_service.handle(request.method, request.path, request.json)
    return HttpResponse(status, json.dumps(value, ensure_ascii=False))


@contextlib.contextmanager
def _todos(rows: list[dict[str, Any]]) -> Iterator[None]:
    todo_service.reset()
    for row in rows:
        todo_service.TODOS[row["id"]] = row
    try:
        yield
    finally:
        todo_service.reset()


def pytest_casebook_setup(data: dict[str, Any]) -> Any:
    return _todos(data.get("todos", []))
