"""実起動の試験で使う、DB を読む関数（call: で呼ぶ）。"""

from __future__ import annotations

from typing import Any

import psycopg


def summary(conn: psycopg.Connection[Any]) -> dict[str, int]:
    """TODO の件数と、完了した件数。"""
    total, done = conn.execute(
        "select count(*), count(*) filter (where done) from todos"
    ).fetchone()
    return {"total": total, "done": done, "open": total - done}
