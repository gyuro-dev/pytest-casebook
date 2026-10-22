"""
フレームワークを使わない、とても小さな TODO の「API」。

本物の Web アプリなら FastAPI や Flask を使うが、このサンプルでは
pytest_casebook_request hook の役割だけを見せるため、ただの関数にしている。
"""

from __future__ import annotations

from typing import Any

TODOS: dict[int, dict[str, Any]] = {}


def reset() -> None:
    TODOS.clear()


def handle(method: str, path: str, body: Any) -> tuple[int, Any]:
    """(ステータスコード, JSON にする値) を返す。"""
    if path == "/todos" and method == "GET":
        return 200, list(TODOS.values())
    if path == "/todos" and method == "POST":
        if not body or not body.get("title"):
            return 422, {"detail": "title は必須です"}
        todo = {"id": len(TODOS) + 1, "title": body["title"], "done": False}
        TODOS[todo["id"]] = todo
        return 201, todo
    if path.startswith("/todos/") and method == "GET":
        todo = TODOS.get(int(path.removeprefix("/todos/")))
        return (200, todo) if todo else (404, {"detail": "見つかりません"})
    return 404, {"detail": "見つかりません"}
