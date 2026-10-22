"""
Flask の API と DB を確かめる hook。15_fastapi と同じ形で、違うのは次の2点だけ。

- アプリは application factory（create_app）にテスト用の DB を渡して作る
- リクエストは Flask の test_client で送る（アダプター send_with_werkzeug_client）

Flask が入っていなければ、このディレクトリのサンプルは集めない。
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
    from notes_app import create_app

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
        finally:  # 次のケースに影響しないよう、すべて消す
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
