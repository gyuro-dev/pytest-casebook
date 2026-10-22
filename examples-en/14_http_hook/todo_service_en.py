"""
A very small TODO "API" without a framework.

A real web app would use FastAPI or Flask, but this sample is just a function so that it
shows only the role of the pytest_casebook_request hook.
"""

from __future__ import annotations

from typing import Any

TODOS: dict[int, dict[str, Any]] = {}


def reset() -> None:
    TODOS.clear()


def handle(method: str, path: str, body: Any) -> tuple[int, Any]:
    """Return (status code, value to turn into JSON)."""
    if path == "/todos" and method == "GET":
        return 200, list(TODOS.values())
    if path == "/todos" and method == "POST":
        if not body or not body.get("title"):
            return 422, {"detail": "title is required"}
        todo = {"id": len(TODOS) + 1, "title": body["title"], "done": False}
        TODOS[todo["id"]] = todo
        return 201, todo
    if path.startswith("/todos/") and method == "GET":
        todo = TODOS.get(int(path.removeprefix("/todos/")))
        return (200, todo) if todo else (404, {"detail": "Not found"})
    return 404, {"detail": "Not found"}
