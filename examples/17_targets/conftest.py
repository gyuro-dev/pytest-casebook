"""
同じケースを、別々の環境（ここでは local と staging）に流す。

pytest-casebook に「環境」の機能はなく、pytest と casebook の今の仕組みを組み合わせる。

1. 環境を選ぶオプション（--target）を足し、casebook_env の中でつなぐ先を切り替える
2. 期待出力の置き場所は、ini の casebook_golden_dir を -o で環境ごとに替える
3. その環境でしか流さないケースには marks を付け、-m で除く

    uv run pytest examples/17_targets                       # local（期待出力は golden/）
    uv run pytest examples/17_targets --target staging \\
        -o casebook_golden_dir=golden_staging -m "not local_only"

本物のプロジェクトでは、--target はプロジェクトの一番上の conftest.py に書く
（pytest_addoption は、pytest を起動したときに読む conftest.py でしか呼ばれないため）。
"""

from __future__ import annotations

from typing import Any

import pytest
from catalog import Catalog

TARGETS = {"local": Catalog.local, "staging": Catalog.staging}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--target", default="local", choices=sorted(TARGETS), help="つなぐ環境")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "local_only: local でしか流さないケース")


@pytest.fixture(scope="session")
def casebook_env(request: pytest.FixtureRequest) -> Catalog:
    # このディレクトリより上から pytest を起動したときは --target がないので、既定の local にする
    target = request.config.getoption("--target", default="local")
    return TARGETS[target]()


def pytest_casebook_prepare_call(env: Catalog, args: list[Any]) -> None:
    args.insert(0, env)
