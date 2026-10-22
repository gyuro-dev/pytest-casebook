"""
FastAPI の API と DB を確かめる hook。作るのは次の4つ。

- casebook_env: テスト用の DB を作り、アプリの DB（get_db）を差し替えた TestClient を用意する
- pytest_casebook_request: TestClient でリクエストを送る（アダプター send_with_httpx_client）
- pytest_casebook_setup: setup: の db に書いた行を入れ、ケースが終わったら消す
- pytest_casebook_observe: observe: / expect: の db.<テーブル名> の行を取り出す

FastAPI が入っていなければ、このディレクトリのサンプルは集めない。
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
    from todo_api import app, get_db

    from pytest_casebook import HttpRequest, HttpResponse
    from pytest_casebook.http import send_with_httpx_client

    @dataclass
    class Env:
        client: TestClient
        db: sqlite3.Connection

    @pytest.fixture(scope="session")
    def casebook_env() -> Iterator[Env]:
        # TestClient はアプリを別のスレッドで動かすため、check_same_thread=False にする
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
        finally:  # 次のケースに影響しないよう、すべて消す
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
