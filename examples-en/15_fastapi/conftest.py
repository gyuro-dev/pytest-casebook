"""
Hooks that check a FastAPI API and its DB. You write these four:

- casebook_env: creates a test DB and a TestClient with the app's DB (get_db) replaced
- pytest_casebook_request: sends the request with the TestClient (adapter send_with_httpx_client)
- pytest_casebook_setup: inserts the rows written under setup: db, and deletes them after the case
- pytest_casebook_observe: reads the rows for db.<table name> in observe: / expect:

If FastAPI is not installed, the samples in this directory are not collected.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

if importlib.util.find_spec("fastapi") is None:
    collect_ignore_glob = ["*.yaml"]
else:
    from fastapi.testclient import TestClient
    from todo_api_en import app, get_db

    from pytest_casebook import HttpRequest, HttpResponse
    from pytest_casebook.http import send_with_httpx_client

    @dataclass
    class Env:
        client: TestClient
        db: sqlite3.Connection

    @pytest.fixture(scope="session")
    def casebook_env() -> Iterator[Env]:
        # TestClient runs the app in another thread, so use check_same_thread=False
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.execute("create table todos (id integer primary key, title text, done integer)")
        app.dependency_overrides[get_db] = lambda: db
        yield Env(TestClient(app), db)
        app.dependency_overrides.clear()
        db.close()

    def pytest_casebook_request(request: HttpRequest, env: Env) -> HttpResponse:
        return send_with_httpx_client(env.client, request)

    @contextlib.contextmanager
    def _rows(db: sqlite3.Connection, tables: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
        for table, rows in tables.items():
            for row in rows:
                marks = ", ".join("?" for _ in row)
                db.execute(
                    f"insert into {table} ({', '.join(row)}) values ({marks})", list(row.values())
                )
        db.commit()
        try:
            yield
        finally:  # delete everything so the next case is not affected
            db.execute("delete from todos")
            db.commit()

    def pytest_casebook_setup(env: Env, data: dict[str, Any]) -> Any:
        return _rows(env.db, data.get("db", {}))

    def pytest_casebook_observe(target: str, env: Env) -> Any:
        if not target.startswith("db."):
            return None
        cur = env.db.execute(f"select * from {target.removeprefix('db.')} order by 1")
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur]
