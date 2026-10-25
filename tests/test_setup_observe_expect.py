"""
setup:（前提条件）・observe:（実行後の値の取り出し）・expect:（YAML に書く期待値）の確認。
"""

from __future__ import annotations

import hashlib
import shutil
import textwrap

import pytest
from helpers import PY, golden, write_casebook

# DB の代わりに sqlite のインメモリ DB を使う conftest
DB_CONFTEST = """
import contextlib
import sqlite3

import pytest


@pytest.fixture(scope="session")
def casebook_env():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table users (id integer primary key, name text, active integer)")
    yield conn
    conn.close()


@contextlib.contextmanager
def _rows(conn, data):
    for row in data.get("db", {}).get("users", []):
        conn.execute(
            "insert into users (id, name, active) values (?, ?, ?)",
            (row["id"], row["name"], row.get("active", 1)),
        )
    try:
        yield
    finally:
        conn.execute("delete from users")


def pytest_casebook_setup(env, data):
    return _rows(env, data)


def pytest_casebook_observe(target, env):
    if target == "db.users":
        cur = env.execute("select id, name, active from users order by id")
        return [{"id": i, "name": n, "active": bool(a)} for i, n, a in cur]
    return None


def pytest_casebook_prepare_call(env, kwargs):
    kwargs["conn"] = env
"""

USERS_MODULE = """
def deactivate(conn, user_id):
    cur = conn.execute("update users set active = 0 where id = ?", (user_id,))
    return {"changed": cur.rowcount, "user_id": user_id}


def add(conn, user_id, name):
    conn.execute("insert into users (id, name, active) values (?, ?, 1)", (user_id, name))
    return user_id
"""


@pytest.fixture
def db_project(project: pytest.Pytester) -> pytest.Pytester:
    project.makeconftest(DB_CONFTEST)
    project.makepyfile(users=USERS_MODULE)
    return project


# =============================================================================
# setup.files と作業ディレクトリ
# =============================================================================


def test_setup_files_are_created_in_workdir_and_observed(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix:
          - {PY}
          - -c
          - |
            import os, pathlib, sys
            text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
            pathlib.Path("out.txt").write_text(text.upper(), encoding="utf-8")
            print("cwd=" + os.getcwd())
        cases:
          - name: upper
            setup:
              files:
                in/data.txt: "abc\\n"
            command: in/data.txt
            observe: [files]
        """,
    )
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    assert golden(project, "upper").endswith(
        textwrap.dedent(
            """\
            ----- stdout -----
            cwd=<tmp>
            ----- observe: files -----
            === in/data.txt ===
            abc
            === out.txt ===
            ABC
            """
        )
    )
    project.runpytest().assert_outcomes(passed=2)


def test_call_runs_in_workdir(project: pytest.Pytester) -> None:
    project.makepyfile(reader="def read(name):\n    return open(name, encoding='utf-8').read()\n")
    write_casebook(
        project,
        """
        cases:
          - name: read
            setup: {files: {a.txt: hello}}
            call: reader:read
            args: [a.txt]
            expect:
              return: hello
        """,
    )
    project.runpytest().assert_outcomes(passed=2)


@pytest.mark.parametrize("name", ["/etc/passwd", "../outside.txt", "C:/x.txt", "a/../../b.txt"])
def test_setup_files_must_stay_in_workdir(project: pytest.Pytester, name: str) -> None:
    write_casebook(
        project,
        f"cases:\n  - name: a\n    call: calc:add\n    setup: {{files: {{'{name}': x}}}}\n",
    )
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*作業ディレクトリからの相対パスで書いてください*"])


# =============================================================================
# setup の hook と observe（DB）
# =============================================================================


def test_db_rows_are_written_one_per_line(db_project: pytest.Pytester) -> None:
    write_casebook(
        db_project,
        """
        cases:
          - name: deactivate
            setup:
              db:
                users:
                  - {id: 1, name: 佐藤}
                  - {id: 2, name: 鈴木}
            call: users:deactivate
            kwargs: {user_id: 2}
            observe: [db.users]
          - name: empty_after_cleanup
            call: users:deactivate
            kwargs: {user_id: 1}
            observe: [db.users]
        """,
    )
    db_project.runpytest("--casebook-update").assert_outcomes(passed=3)
    assert golden(db_project, "deactivate").endswith(
        "----- observe: db.users -----\n"
        '{"id": 1, "name": "佐藤", "active": true}\n'
        '{"id": 2, "name": "鈴木", "active": false}\n'
    )
    # 前のケースで入れた行は後片付けで消えている
    assert golden(db_project, "empty_after_cleanup").endswith(
        '"changed": 0,\n  "user_id": 1\n}\n----- observe: db.users -----\n[]\n'
    )


def test_db_change_shows_only_the_changed_row_in_diff(db_project: pytest.Pytester) -> None:
    text = """
        cases:
          - name: deactivate
            setup:
              db:
                users:
                  - {id: 1, name: 佐藤}
                  - {id: 2, name: 鈴木}
                  - {id: 3, name: 高橋}
            call: users:deactivate
            kwargs: {user_id: 2}
            observe: [db.users]
        """
    write_casebook(db_project, text)
    db_project.runpytest("--casebook-update")
    write_casebook(db_project, text.replace("user_id: 2", "user_id: 3"))

    result = db_project.runpytest()
    result.assert_outcomes(passed=1, failed=1)
    out = result.stdout.str()
    # 違う行だけが -/+ になり、変わらない行（佐藤）は差分の行にならない
    assert '-{"id": 2, "name": "鈴木", "active": false}' in out
    assert '+{"id": 2, "name": "鈴木", "active": true}' in out
    assert '-{"id": 1, "name": "佐藤"' not in out


def test_observe_without_hook_fails(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        "cases:\n  - name: a\n    call: calc:add\n    args: [1, 2]\n    observe: [db.x]\n",
    )
    result = project.runpytest("--casebook-update")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*observe: db.x を取り出せません*"])


# =============================================================================
# expect:
# =============================================================================


def test_expect_passes_without_golden(db_project: pytest.Pytester) -> None:
    write_casebook(
        db_project,
        f"""
        command_prefix: [{PY}, -c]
        cases:
          - name: deactivate
            setup:
              db: {{users: [{{id: 1, name: 佐藤}}, {{id: 2, name: 鈴木}}]}}
            call: users:deactivate
            kwargs: {{user_id: 2}}
            expect:
              return: {{changed: 1}}
              db.users:
                - {{id: 1, active: true}}
                - {{id: 2, name: 鈴木, active: false}}
          - name: duplicate
            setup:
              db: {{users: [{{id: 1, name: 佐藤}}]}}
            call: users:add
            kwargs: {{user_id: 1, name: 重複}}
            expect:
              raises: IntegrityError
          - name: duplicate_message
            setup:
              db: {{users: [{{id: 1, name: 佐藤}}]}}
            call: users:add
            kwargs: {{user_id: 1, name: 重複}}
            expect:
              raises: {{contains: UNIQUE constraint failed}}
          - name: cli
            command: "'import sys; print(\\"在庫切れ\\"); sys.exit(3)'"
            expect:
              exit_code: 3
              stdout: {{contains: 在庫切れ}}
              stderr: ""
          - name: cli_regex
            command: "'print(\\"total=42\\")'"
            expect:
              stdout: {{regex: '^total=\\d+$'}}
        """,
    )
    result = db_project.runpytest("--casebook-update")
    result.assert_outcomes(passed=6)
    # expect: のケースは期待出力ファイルを作らない
    assert not (db_project.path / "golden").exists()


def test_expect_failure_message_is_readable(db_project: pytest.Pytester) -> None:
    write_casebook(
        db_project,
        """
        cases:
          - name: deactivate
            setup:
              db: {users: [{id: 1, name: 佐藤}, {id: 2, name: 鈴木}]}
            call: users:deactivate
            kwargs: {user_id: 2}
            expect:
              return: {changed: 2}
              db.users:
                - {id: 1, name: 佐藤, active: true}
                - {id: 2, name: 鈴木, active: true}
                - {id: 3, name: 高橋}
        """,
    )
    result = db_project.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(
        [
            "*期待結果と違います:",
            "*- return.changed: 期待 2 / 実際 1",
            "*- db.users: 件数が違います（期待 3 件 / 実際 2 件）",
            "*- db.users[[]1].active: 期待 true / 実際 false",
            "*----- 実際の return -----",
            "*----- 実際の db.users -----",
            '*{"id": 1, "name": "佐藤", "active": true}',
            '*{"id": 2, "name": "鈴木", "active": false}',
        ]
    )


def test_expect_unexpected_exception_and_missing_exception(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        """
        cases:
          - name: boom
            call: calc:divide
            args: [1, 0]
            expect:
              return: 1
          - name: no_boom
            call: calc:divide
            args: [4, 2]
            expect:
              raises: "ZeroDivisionError: division by zero"
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(failed=2, passed=1)
    result.stdout.fnmatch_lines(
        [
            "*例外が出ました: ZeroDivisionError: division by zero*",
            "*raises: 例外が出ませんでした（戻り値 2.0）*",
        ]
    )


def test_expect_multiline_stdout_shows_diff(project: pytest.Pytester) -> None:
    write_casebook(
        project,
        f"""
        command_prefix: [{PY}, -c]
        cases:
          - name: lines
            command: "'print(\\"a\\"); print(\\"b\\"); print(\\"c\\")'"
            expect:
              stdout: |
                a
                X
                c
        """,
    )
    result = project.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(["*stdout: 期待と違います*", "*-X*", "*+b*"])


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("command: x\n    expect: {return: 1}", "expect.return は call のケースにだけ書けます"),
        ("call: m:f\n    expect: {exit_code: 0}", "expect.exit_code は command のケースにだけ"),
        ("call: m:f\n    expect: {return: 1, raises: E}", "return と raises のどちらか一方"),
        ("command: x\n    expect: {exit_code: '0'}", "exit_code は整数で書いてください"),
        ("command: x\n    expect: {stdout: {regex: '('}}", "expect.stdout の正規表現の誤り"),
        ("command: x\n    expect: {stdout: {starts: a}}", "expect.stdout は文字列か"),
        ("command: x\n    expect: {}", "expect は 項目 -> 期待値 のマッピング"),
        # キーが文字列でなくても、書き方の誤りとして知らせる（AttributeError で落ちない）
        ("command: x\n    expect: {stdout: {1: a}}", "expect.stdout は文字列か"),
    ],
)
def test_invalid_expect(project: pytest.Pytester, case: str, message: str) -> None:
    write_casebook(project, f"cases:\n  - name: a\n    {case}\n")
    result = project.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*{message}*"])


def test_html_shows_precondition_and_expected(db_project: pytest.Pytester) -> None:
    write_casebook(
        db_project,
        """
        states:
          default: {}
          two_users:
            db: {users: [{id: 1, name: 佐藤}, {id: 2, name: 鈴木}]}
        cases:
          - name: deactivate
            setup:
              files: {memo.txt: x}
              db: {users: [{id: 1, name: 佐藤}]}
            call: users:deactivate
            kwargs: {user_id: 1}
            expect:
              db.users: [{id: 1, active: false}]
          - name: golden_case
            state: two_users
            call: users:deactivate
            kwargs: {user_id: 1}
            observe: [db.users]
        """,
    )
    report = db_project.path / "report.html"
    # 期待出力の内容は出さない（観察した db.users に鈴木が出て、状態の中身の確認と紛れるため）
    db_project.runpytest(
        "--casebook-update", "-o", "casebook_html_golden=off", f"--casebook-html={report}"
    )
    page = report.read_text(encoding="utf-8")
    assert "<th>前提条件</th><th>期待結果</th>" in page
    # 既定の状態は出さず、それ以外の状態は名前だけを出す（中身は出さない）
    assert "状態: default" not in page
    assert "<div class='line'>状態: two_users</div>" in page
    assert "鈴木" not in page
    assert "<div class='line'>ファイル: memo.txt</div>" in page
    assert "db: {&quot;users&quot;: [{&quot;id&quot;: 1" in page
    assert "db.users = [{&quot;id&quot;: 1, &quot;active&quot;: false}]" in page
    # 期待出力ファイルの置き場所はファイルごとに1回だけ出し、行にはファイル名だけを出す
    assert "期待出力ファイルの置き場所: golden/casebook_calc/" in page
    assert "期待出力ファイル（golden_case.txt）" in page
    assert "観察: db.users" in page


def test_observed_binary_file_is_size_and_hash(project: pytest.Pytester) -> None:
    """
    observe の files で UTF-8 で読めないファイルは、大きさと SHA-256 の1行にする
    （置換文字で読むと、違うバイト列が同じ置換文字になり、変わっても気づけない）。
    改行だけのちがい（CRLF）は、テキストとして LF にそろえる。
    """

    def yaml_for(byte: int, expect: str = "") -> str:
        program = (
            f"import pathlib; pathlib.Path('out.bin').write_bytes(bytes([0, {byte}, 146, 150]));"
            " pathlib.Path('out.txt').write_bytes(bytes([97, 13, 10, 98, 13, 10]))"
        )
        return f"""
        command_prefix: [{PY}, -c]
        cases:
          - name: files
            command:
              - "{program}"
            observe: [files]
            {expect}
        """

    write_casebook(project, yaml_for(159))
    project.runpytest("--casebook-update").assert_outcomes(passed=2)
    digest = hashlib.sha256(bytes([0, 159, 146, 150])).hexdigest()
    text = golden(project, "files")
    assert f"<binary: 4 bytes, sha256={digest}>" in text
    assert "=== out.txt ===\na\nb" in text
    # もう一度流しても一致する
    project.runpytest().assert_outcomes(passed=2)
    # 中身（バイト列）が変われば一致しない（大きさが同じでも SHA-256 で分かる）。
    # expect: に替えるので、使わなくなる期待出力は消しておく（消し忘れの確認に掛からないように）
    shutil.rmtree(project.path / "golden")
    write_casebook(
        project,
        yaml_for(160, f"expect: {{files: {{out.bin: '<binary: 4 bytes, sha256={digest}>'}}}}"),
    )
    result = project.runpytest()
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(["*files.out.bin: 期待*sha256*"])
