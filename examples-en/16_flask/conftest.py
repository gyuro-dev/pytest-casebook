"""
Hooks that check a Flask API and its DB. Same shape as 15_fastapi; only these two points differ:

- the app is created by passing the test DB to the application factory (create_app)
- requests are sent with Flask's test_client (adapter send_with_werkzeug_client)

If Flask is not installed, the samples in this directory are not collected.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

if importlib.util.find_spec("flask") is None:
    collect_ignore_glob = ["*.yaml"]
else:
    from flask.testing import FlaskClient
    from notes_app_en import create_app

    from pytest_casebook import HttpRequest, HttpResponse
    from pytest_casebook.http import send_with_werkzeug_client

    @dataclass
    class Env:
        client: FlaskClient
        db: sqlite3.Connection

    @pytest.fixture(scope="session")
    def casebook_env() -> Iterator[Env]:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.execute("create table notes (id integer primary key, text text, tag text)")
        yield Env(create_app(db).test_client(), db)
        db.close()

    def pytest_casebook_request(request: HttpRequest, env: Env) -> HttpResponse:
        return send_with_werkzeug_client(env.client, request)

    @contextlib.contextmanager
    def _rows(db: sqlite3.Connection, tables: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
        for table, rows in tables.items():
            for row in rows:
                marks = ", ".join("?" for _ in row)
                sql = f"insert into {table} ({', '.join(row)}) values ({marks})"
                db.execute(sql, list(row.values()))
        db.commit()
        try:
            yield
        finally:  # delete everything so the next case is not affected
            db.execute("delete from notes")
            db.commit()

    def pytest_casebook_setup(env: Env, data: dict[str, Any]) -> Any:
        return _rows(env.db, data.get("db", {}))

    def pytest_casebook_observe(target: str, env: Env) -> Any:
        if not target.startswith("db."):
            return None
        cur = env.db.execute(f"select * from {target.removeprefix('db.')} order by 1")
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur]
