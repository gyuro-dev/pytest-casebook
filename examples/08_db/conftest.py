"""
DB を使うときの hook。作るのは次の4つ。

- casebook_env: テストで使う DB を用意する（この値が各 hook の env に渡る）
- pytest_casebook_setup: YAML の setup: の db に書いた行を入れ、ケースが終わったら消す
- pytest_casebook_prepare_call: 関数の先頭の引数に DB の接続を渡す
- pytest_casebook_observe: observe: / expect: の db.<テーブル名> の行を取り出す
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
    finally:  # 次のケースに影響しないよう、すべて消す
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
    # 並び順が実行ごとに変わらないよう、必ず order by を付ける
    cur = env.execute(f"select * from {target.removeprefix('db.')} order by 1")
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur]
