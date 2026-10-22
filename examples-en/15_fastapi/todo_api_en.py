"""A TODO API using FastAPI and sqlite."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()
DB_PATH = "todo.db"


def get_db() -> Iterator[sqlite3.Connection]:
    """The production DB connection (replaced through dependency_overrides in tests)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization != "Bearer secret":
        raise HTTPException(status_code=401, detail="Authentication required")


Db = Annotated[sqlite3.Connection, Depends(get_db)]


class NewTodo(BaseModel):
    title: str


@app.get("/todos")
def list_todos(db: Db, done: bool | None = None) -> list[dict[str, object]]:
    sql, params = "select id, title, done from todos", ()
    if done is not None:
        sql, params = sql + " where done = ?", (int(done),)
    rows = db.execute(sql + " order by id", params).fetchall()
    return [{"id": i, "title": t, "done": bool(d)} for i, t, d in rows]


@app.post("/todos", status_code=201, dependencies=[Depends(require_token)])
def create_todo(todo: NewTodo, db: Db) -> dict[str, object]:
    cur = db.execute("insert into todos (title, done) values (?, 0)", (todo.title,))
    db.commit()
    return {"id": cur.lastrowid, "title": todo.title, "done": False}


@app.patch("/todos/{todo_id}/done", dependencies=[Depends(require_token)])
def complete_todo(todo_id: int, db: Db) -> dict[str, object]:
    cur = db.execute("update todos set done = 1 where id = ?", (todo_id,))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": todo_id, "done": True}
