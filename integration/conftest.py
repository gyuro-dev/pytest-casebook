"""
実起動の試験の hook。PostgreSQL と API サーバーは Docker で本当に起動したものを使う
（scripts/integration.sh が起動して、接続先を環境変数で渡す）。

- casebook_env: PostgreSQL への接続と、API サーバーへの HTTP のクライアント
- pytest_casebook_setup: ケースの前にテーブルを空にして setup: の db の行を入れ、後でまた空にする
- pytest_casebook_observe: db.todos の行を取り出す
- pytest_casebook_request: 本物の HTTP で API サーバーに送る
- pytest_casebook_prepare_call: call: の関数に DB の接続を渡す

接続先（CASEBOOK_DB_URL / CASEBOOK_API_URL）がなければ、このディレクトリのケースは集めない。
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

DB_URL = os.environ.get("CASEBOOK_DB_URL")
API_URL = os.environ.get("CASEBOOK_API_URL")

if not (DB_URL and API_URL):
    collect_ignore_glob = ["*.yaml"]
else:
    import httpx2
    import psycopg

    from pytest_casebook import HttpRequest, HttpResponse
    from pytest_casebook.http import send_with_httpx_client

    @dataclass
    class Env:
        db: psycopg.Connection[Any]
        http: httpx2.Client

    @pytest.fixture(scope="session")
    def casebook_env() -> Iterator[Env]:
        with (
            psycopg.connect(DB_URL, autocommit=True) as db,
            httpx2.Client(base_url=API_URL, timeout=10) as http,
        ):
            yield Env(db, http)

    def _clear(db: psycopg.Connection[Any]) -> None:
        db.execute("truncate todos restart identity")

    @contextlib.contextmanager
    def _rows(
        db: psycopg.Connection[Any], tables: dict[str, list[dict[str, Any]]]
    ) -> Iterator[None]:
        _clear(db)
        for table, rows in tables.items():
            for row in rows:
                columns = ", ".join(row)
                marks = ", ".join(["%s"] * len(row))
                db.execute(f"insert into {table} ({columns}) values ({marks})", list(row.values()))
            # id を明示して入れたあとも、次の serial がぶつからないようにする
            db.execute(
                f"select setval(pg_get_serial_sequence('{table}', 'id'), "
                f"coalesce((select max(id) from {table}), 0) + 1, false)"
            )
        try:
            yield
        finally:
            _clear(db)

    def pytest_casebook_setup(env: Env, data: dict[str, Any]) -> Any:
        return _rows(env.db, data.get("db", {}))

    def pytest_casebook_observe(target: str, env: Env) -> Any:
        if target != "db.todos":
            return None
        cur = env.db.execute("select id, title, done from todos order by id")
        columns = [d.name for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur]

    def pytest_casebook_request(request: HttpRequest, env: Env) -> HttpResponse:
        return send_with_httpx_client(env.http, request)

    def pytest_casebook_prepare_call(env: Env, args: list[Any]) -> None:
        args.insert(0, env.db)
