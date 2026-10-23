"""
scripts/release_notes.py（CHANGELOG.md から GitHub のリリースノートを作る）の確認。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest_casebook

ROOT = Path(__file__).resolve().parent.parent


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_notes", ROOT / "scripts" / "release_notes.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHANGELOG = """\
# Changelog

## [Unreleased]

## [0.2.0] - 2026-10-22

### Changed

- Two.

## [0.1.0] - 2026-10-21

The first release.

[Unreleased]: https://example.com/compare/v0.2.0...HEAD
[0.2.0]: https://example.com/compare/v0.1.0...v0.2.0
[0.1.0]: https://example.com/releases/tag/v0.1.0
"""


def test_notes_are_the_section_with_links() -> None:
    """節の本文に、PyPI と比較のリンクを足す。"""
    notes = _script().release_notes(CHANGELOG, "0.2.0")
    assert notes == (
        "### Changed\n\n- Two.\n\n"
        "**PyPI**: https://pypi.org/project/pytest-casebook/0.2.0/\n\n"
        "**Full changelog**: https://example.com/compare/v0.1.0...v0.2.0\n"
    )


def test_last_section_stops_at_the_link_definitions() -> None:
    """最後の節は、リンクの定義の手前で終わる。比較のリンクがなければ足さない。"""
    notes = _script().release_notes(CHANGELOG, "0.1.0")
    assert notes == (
        "The first release.\n\n**PyPI**: https://pypi.org/project/pytest-casebook/0.1.0/\n"
    )


def test_unknown_version_is_none() -> None:
    """節のない版は None（似た版の名前にも当たらない）。"""
    assert _script().release_notes(CHANGELOG, "0.2") is None
    assert _script().release_notes(CHANGELOG, "9.9.9") is None


def test_current_version_has_notes() -> None:
    """今の __version__ の節が CHANGELOG.md にある（ないとタグからの公開が止まる）。"""
    assert _script().main([pytest_casebook.__version__]) == 0
