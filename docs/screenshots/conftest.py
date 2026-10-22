"""
スクリーンショット用のケースの hook。

- command のケースは、別プロセスを立てずに store.main を同じプロセスで呼ぶ
- 状態（states:）とケースの setup: の stock は、store.STOCK の在庫数を一時的に書き換えて表す
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import store

from pytest_casebook import run_in_process


def pytest_casebook_run_command(argv: list[str], case: Any) -> Any:
    # command_prefix の "store" を除いた残りを main に渡す
    return run_in_process(store.main, argv[1:], stdin=case.stdin)


@contextlib.contextmanager
def _stock(overrides: dict[str, int]) -> Iterator[None]:
    original = dict(store.STOCK)
    store.STOCK.update(overrides)
    try:
        yield
    finally:
        store.STOCK.clear()
        store.STOCK.update(original)


def pytest_casebook_setup(env: Any, data: dict[str, Any]) -> Any:
    return _stock(data.get("stock", {}))
