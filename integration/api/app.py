"""実起動の試験で使う TODO の API（PostgreSQL に読み書きする）。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

app = FastAPI()
DATABASE_URL = os.environ["DATABASE_URL"]
API_TOKEN = os.environ.get("API_TOKEN", "secret")


def get_db() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="認証が必要です")


Db = Annotated[psycopg.Connection[dict[str, Any]], Depends(get_db)]


class NewTodo(BaseModel):
    title: str


@app.get("/health")
def health(db: Db) -> dict[str, str]:
    db.execute("select 1")
    return {"status": "ok"}


@app.get("/todos")
def list_todos(db: Db, done: bool | None = None) -> list[dict[str, Any]]:
    if done is None:
        rows = db.execute("select id, title, done from todos order by id").fetchall()
    else:
        rows = db.execute(
            "select id, title, done from todos where done = %s order by id", (done,)
        ).fetchall()
    return rows


@app.post("/todos", status_code=201, dependencies=[Depends(require_token)])
def create_todo(todo: NewTodo, db: Db) -> dict[str, Any]:
    if not todo.title.strip():
        raise HTTPException(status_code=422, detail="title が空です")
    row = db.execute(
        "insert into todos (title) values (%s) returning id, title, done, created_at",
        (todo.title,),
    ).fetchone()
    db.commit()
    return row


@app.patch("/todos/{todo_id}/done", dependencies=[Depends(require_token)])
def complete_todo(todo_id: int, db: Db) -> dict[str, Any]:
    row = db.execute(
        "update todos set done = true where id = %s returning id, title, done", (todo_id,)
    ).fetchone()
    db.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="見つかりません")
    return row


@app.delete("/todos/{todo_id}", status_code=204, dependencies=[Depends(require_token)])
def delete_todo(todo_id: int, db: Db) -> None:
    cur = db.execute("delete from todos where id = %s", (todo_id,))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="見つかりません")
