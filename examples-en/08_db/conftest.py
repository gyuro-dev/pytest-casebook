"""
Hooks for using a DB. You write these four:

- casebook_env: prepares the DB used by the tests (this value is passed to each hook as env)
- pytest_casebook_setup: inserts the rows written under setup: db, and deletes them after the case
- pytest_casebook_prepare_call: passes the DB connection as the function's first argument
- pytest_casebook_observe: reads the rows for db.<table name> in observe: / expect:
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

TABLES = {
    "members": "id integer primary key, name text, active integer",
    "history": "id integer primary key autoincrement, member_id integer, action text",
}


@pytest.fixture(scope="session")
def casebook_env() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    for name, columns in TABLES.items():
        conn.execute(f"create table {name} ({columns})")
    yield conn
    conn.close()


@contextlib.contextmanager
def _insert(conn: sqlite3.Connection, tables: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
    for table, rows in tables.items():
        for row in rows:
            marks = ", ".join("?" for _ in row)
            sql = f"insert into {table} ({', '.join(row)}) values ({marks})"
            conn.execute(sql, list(row.values()))
    try:
        yield
    finally:  # delete everything so the next case is not affected
        for table in TABLES:
            conn.execute(f"delete from {table}")
        conn.execute("delete from sqlite_sequence")


def pytest_casebook_setup(env: sqlite3.Connection, data: dict[str, Any]) -> Any:
    return _insert(env, data.get("db", {}))


def pytest_casebook_prepare_call(env: sqlite3.Connection, args: list[Any]) -> None:
    args.insert(0, env)


def pytest_casebook_observe(target: str, env: sqlite3.Connection) -> Any:
    if not target.startswith("db."):
        return None
    # always add order by so the row order does not change from run to run
    cur = env.execute(f"select * from {target.removeprefix('db.')} order by 1")
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur]
