"""Print the release notes of one version from CHANGELOG.md.

CHANGELOG.md から、1つの版のリリースノートを出力する。

Usage / 使い方::

    python scripts/release_notes.py 0.4.0 > notes.md

The notes are the version's section (without its heading), a link to the version on PyPI
and the "compare" link at the bottom of the changelog. Exits with 1 when the version has
no section, so that a release is not made without notes.

版の節（見出しを除く）に、PyPI の版のページと、CHANGELOG の下にある比較のリンクを足す。
版の節がなければ 1 で終わる（ノートなしでリリースを作らないため）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
PYPI_URL = "https://pypi.org/project/pytest-casebook/{version}/"


def release_notes(changelog: str, version: str) -> str | None:
    """Return the notes of ``version``, or None when it has no section.

    ``version`` の版のノートを返す。節がなければ None。
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\]", re.MULTILINE)
    found = heading.search(changelog)
    if found is None:
        return None
    body_start = changelog.index("\n", found.end()) + 1
    # The section ends at the next "## [" heading or at the link definitions
    # 節は、次の「## [」の見出しか、リンクの定義の行で終わる
    end = re.compile(r"^(## \[|\[[^\]]+\]: )", re.MULTILINE).search(changelog, body_start)
    body = changelog[body_start : end.start() if end else len(changelog)].strip()
    lines = [body, "", f"**PyPI**: {PYPI_URL.format(version=version)}"]
    link = re.search(rf"^\[{re.escape(version)}\]: (\S+)$", changelog, re.MULTILINE)
    if link is not None and "/compare/" in link.group(1):
        lines += ["", f"**Full changelog**: {link.group(1)}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py VERSION", file=sys.stderr)
        return 2
    version = argv[0].removeprefix("v")
    notes = release_notes(CHANGELOG.read_text(encoding="utf-8"), version)
    if notes is None:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
