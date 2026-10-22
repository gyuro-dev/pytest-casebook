"""
Hooks for the screenshot cases.

- command cases call store_en.main in-process instead of starting a subprocess
- the stock of a state (states:) and of a case's setup: is applied by temporarily changing
  store_en.STOCK
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import store_en

from pytest_casebook import run_in_process


def pytest_casebook_run_command(argv: list[str], case: Any) -> Any:
    # pass the rest after the command_prefix "store" to main
    return run_in_process(store_en.main, argv[1:], stdin=case.stdin)


@contextlib.contextmanager
def _stock(overrides: dict[str, int]) -> Iterator[None]:
    original = dict(store_en.STOCK)
    store_en.STOCK.update(overrides)
    try:
        yield
    finally:
        store_en.STOCK.clear()
        store_en.STOCK.update(original)


def pytest_casebook_setup(env: Any, data: dict[str, Any]) -> Any:
    return _stock(data.get("stock", {}))
