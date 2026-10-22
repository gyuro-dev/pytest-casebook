"""
The hook implementations for the sample.

- command cases call shop_en.main in-process instead of starting a subprocess
- the stock of a state (states:) is expressed by temporarily changing the counts in shop_en.STOCK
- the DB is an in-memory sqlite DB. The rows under setup: db are inserted and deleted after the case
- db.<table name> in observe: / expect: reads the table rows after the run
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
import shop_en

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
    # pass main everything after the "shop" of command_prefix
    return run_in_process(shop_en.main, argv[1:], stdin=case.stdin)


@contextlib.contextmanager
def _stock(overrides: dict[str, int]) -> Iterator[None]:
    original = dict(shop_en.STOCK)
    shop_en.STOCK.update(overrides)
    try:
        yield
    finally:
        shop_en.STOCK.clear()
        shop_en.STOCK.update(original)


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
    # data holds the state (states:) with the case's setup: merged over it
    with _stock(data.get("stock", {})), _db_rows(env, data.get("db", {})):
        yield


def pytest_casebook_setup(env: sqlite3.Connection, data: dict[str, Any]) -> Any:
    return _prepare(env, data)


def pytest_casebook_prepare_call(case: Any, env: sqlite3.Connection, args: list[Any]) -> None:
    # functions in the orders_en module get the DB connection as their first argument
    if case.call.startswith("orders_en:"):
        args.insert(0, env)


def pytest_casebook_observe(target: str, env: sqlite3.Connection) -> Any:
    if not target.startswith("db."):
        return None
    table = target.removeprefix("db.")
    cur = env.execute(f"select * from {table} order by 1")
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur]
