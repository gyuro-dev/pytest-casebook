"""Member operations that use a DB (sqlite)."""

import sqlite3


class AlreadyWithdrawn(Exception):
    """The member has already withdrawn."""


def withdraw(conn: sqlite3.Connection, member_id: int) -> dict[str, object]:
    """Withdraw the member and record the withdrawal."""
    row = conn.execute("select active from members where id = ?", (member_id,)).fetchone()
    if row is None or not row[0]:
        raise AlreadyWithdrawn(f"Member {member_id} has already withdrawn")
    conn.execute("update members set active = 0 where id = ?", (member_id,))
    conn.execute("insert into history (member_id, action) values (?, 'withdraw')", (member_id,))
    return {"member_id": member_id, "withdrawn": True}
