"""実起動の試験で使う CLI（PostgreSQL に直接読み書きする）。

python todo_cli.py list
python todo_cli.py add <title>
python todo_cli.py done <id>
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_done = sub.add_parser("done")
    p_done.add_argument("id", type=int)
    args = parser.parse_args(argv)

    with psycopg.connect(os.environ["CASEBOOK_DB_URL"]) as conn:
        if args.cmd == "list":
            rows = conn.execute("select id, title, done from todos order by id").fetchall()
            if not rows:
                print("TODO はありません")
            for todo_id, title, done in rows:
                print(f"{todo_id}. [{'x' if done else ' '}] {title}")
            return 0
        if args.cmd == "add":
            (todo_id,) = conn.execute(
                "insert into todos (title) values (%s) returning id", (args.title,)
            ).fetchone()
            print(f"{todo_id} を追加しました: {args.title}")
            return 0
        cur = conn.execute("update todos set done = true where id = %s", (args.id,))
        if cur.rowcount == 0:
            print(f"エラー: {args.id} は見つかりません", file=sys.stderr)
            return 1
        print(f"{args.id} を完了にしました")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
