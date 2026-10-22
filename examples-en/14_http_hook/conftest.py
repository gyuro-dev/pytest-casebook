"""
The smallest form of the hook that sends request: (pytest_casebook_request).

pytest-casebook does not send HTTP itself. For request: cases, this hook receives an
HttpRequest (the content of request: in the YAML) and returns an HttpResponse.
With FastAPI or Flask, send it with their test clients (15_fastapi / 16_flask).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from typing import Any

import todo_service_en

from pytest_casebook import HttpRequest, HttpResponse


def pytest_casebook_request(request: HttpRequest) -> HttpResponse:
    status, value = todo_service_en.handle(request.method, request.path, request.json)
    return HttpResponse(status, json.dumps(value, ensure_ascii=False))


@contextlib.contextmanager
def _todos(rows: list[dict[str, Any]]) -> Iterator[None]:
    todo_service_en.reset()
    for row in rows:
        todo_service_en.TODOS[row["id"]] = row
    try:
        yield
    finally:
        todo_service_en.reset()


def pytest_casebook_setup(data: dict[str, Any]) -> Any:
    return _todos(data.get("todos", []))
