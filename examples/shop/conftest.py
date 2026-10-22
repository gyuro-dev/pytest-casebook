"""
サンプルの hook の実装。

- command のケースは、別プロセスを立てずに shop.main を同じプロセスで呼ぶ
- 状態（states:）の stock は shop.STOCK の在庫数を一時的に書き換えて表す
- DB は sqlite のインメモリ DB。setup: の db に書いた行を入れ、ケースが終わったら消す
- observe: / expect: の db.<テーブル名> で、実行後のテーブルの行を取り出す
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
import shop

from pytest_casebook import run_in_process

TABLES = {
    "stock": "item text primary key, count integer",
    "orders": "id integer primary key autoincrement, item text, quantity integer",
}


@pytest.fixture(scope="session")
def casebook_env() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    for name, columns in TABLES.items():
        conn.execute(f"create table {name} ({columns})")
    yield conn
    conn.close()


def pytest_casebook_run_command(argv: list[str], case: Any) -> Any:
    # command_prefix の "shop" を除いた残りを main に渡す
    return run_in_process(shop.main, argv[1:], stdin=case.stdin)


@contextlib.contextmanager
def _stock(overrides: dict[str, int]) -> Iterator[None]:
    original = dict(shop.STOCK)
    shop.STOCK.update(overrides)
    try:
        yield
    finally:
        shop.STOCK.clear()
        shop.STOCK.update(original)


@contextlib.contextmanager
def _db_rows(conn: sqlite3.Connection, tables: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
    for table, rows in tables.items():
        for row in rows:
            columns = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            conn.execute(f"insert into {table} ({columns}) values ({marks})", list(row.values()))
    try:
        yield
    finally:
        for table in TABLES:
            conn.execute(f"delete from {table}")
        conn.execute("delete from sqlite_sequence")


@contextlib.contextmanager
def _prepare(env: sqlite3.Connection, data: dict[str, Any]) -> Iterator[None]:
    # 状態（states:）とケースの setup: を重ねた内容が data に入っている
    with _stock(data.get("stock", {})), _db_rows(env, data.get("db", {})):
        yield


def pytest_casebook_setup(env: sqlite3.Connection, data: dict[str, Any]) -> Any:
    return _prepare(env, data)


def pytest_casebook_prepare_call(case: Any, env: sqlite3.Connection, args: list[Any]) -> None:
    # orders モジュールの関数には、先頭の引数に DB の接続を渡す
    if case.call.startswith("orders:"):
        args.insert(0, env)


def pytest_casebook_observe(target: str, env: sqlite3.Connection) -> Any:
    if not target.startswith("db."):
        return None
    table = target.removeprefix("db.")
    cur = env.execute(f"select * from {table} order by 1")
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur]
