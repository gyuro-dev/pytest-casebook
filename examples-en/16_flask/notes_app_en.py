"""A notes API using Flask and sqlite (in the application factory form)."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Flask, abort, current_app, jsonify, request


def create_app(db: sqlite3.Connection | None = None) -> Flask:
    """Create the app. Tests pass in a connection to the test DB."""
    app = Flask(__name__)
    app.config["DB"] = db or sqlite3.connect("notes.db", check_same_thread=False)

    def get_db() -> sqlite3.Connection:
        return current_app.config["DB"]

    @app.get("/notes")
    def list_notes() -> Any:
        tag = request.args.get("tag")
        sql, params = "select id, text, tag from notes", ()
        if tag:
            sql, params = sql + " where tag = ?", (tag,)
        rows = get_db().execute(sql + " order by id", params).fetchall()
        return jsonify([{"id": i, "text": t, "tag": g} for i, t, g in rows])

    @app.post("/notes")
    def create_note() -> Any:
        body = request.get_json(silent=True) or {}
        if not body.get("text"):
            return jsonify({"error": "text is required"}), 400
        cur = get_db().execute(
            "insert into notes (text, tag) values (?, ?)", (body["text"], body.get("tag"))
        )
        get_db().commit()
        return (
            jsonify({"id": cur.lastrowid, "text": body["text"]}),
            201,
            {"Location": f"/notes/{cur.lastrowid}"},
        )

    @app.delete("/notes/<int:note_id>")
    def delete_note(note_id: int) -> Any:
        cur = get_db().execute("delete from notes where id = ?", (note_id,))
        get_db().commit()
        if cur.rowcount == 0:
            abort(404)
        return "", 204

    return app
