"""
The hook that applies a state (states:).

A state is a "named setup:" and is passed to pytest_casebook_setup. Here the flags are
applied to features_en.FLAGS for the duration of the case and restored afterwards.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import features_en


@contextlib.contextmanager
def _flags(overrides: dict[str, bool]) -> Iterator[None]:
    original = dict(features_en.FLAGS)
    features_en.FLAGS.update(overrides)
    try:
        yield
    finally:
        features_en.FLAGS.update(original)


def pytest_casebook_setup(data: dict[str, Any]) -> Any:
    return _flags(data.get("flags", {}))
