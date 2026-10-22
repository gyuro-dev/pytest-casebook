"""DB（sqlite）を使う会員の処理。"""

import sqlite3


class AlreadyWithdrawn(Exception):
    """すでに退会している。"""


def withdraw(conn: sqlite3.Connection, member_id: int) -> dict[str, object]:
    """会員を退会させ、退会の記録を残す。"""
    row = conn.execute("select active from members where id = ?", (member_id,)).fetchone()
    if row is None or not row[0]:
        raise AlreadyWithdrawn(f"会員 {member_id} はすでに退会しています")
    conn.execute("update members set active = 0 where id = ?", (member_id,))
    conn.execute("insert into history (member_id, action) values (?, 'withdraw')", (member_id,))
    return {"member_id": member_id, "withdrawn": True}
