"""
状態（states:）を当てる hook。

状態は「名前を付けた setup:」で、pytest_casebook_setup に渡る。ここでは flags を
features.FLAGS に一時的に当て、ケースが終わったら元に戻す。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import features


@contextlib.contextmanager
def _flags(overrides: dict[str, bool]) -> Iterator[None]:
    original = dict(features.FLAGS)
    features.FLAGS.update(overrides)
    try:
        yield
    finally:
        features.FLAGS.update(original)


def pytest_casebook_setup(data: dict[str, Any]) -> Any:
    return _flags(data.get("flags", {}))
