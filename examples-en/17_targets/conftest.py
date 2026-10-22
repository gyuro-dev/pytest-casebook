"""
Run the same cases against different environments (here, local and staging).

pytest-casebook has no "environment" feature; this combines what pytest and casebook already offer.

1. Add an option that picks the environment (--target) and switch the connection in casebook_env
2. Switch where golden files live per environment by overriding the ini casebook_golden_dir with -o
3. Mark cases that run only on some environments with marks, and exclude them with -m

    uv run pytest examples-en/17_targets                    # local (golden files in golden/)
    uv run pytest examples-en/17_targets --target staging \\
        -o casebook_golden_dir=golden_staging -m "not local_only"

In a real project, put --target in the top-level conftest.py of the project
(pytest_addoption is only called for the conftest.py files read when pytest starts).
"""

from __future__ import annotations

from typing import Any

import pytest
from catalog_en import Catalog

TARGETS = {"local": Catalog.local, "staging": Catalog.staging}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--target", default="local", choices=sorted(TARGETS), help="environment to connect to"
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "local_only: cases that run only on local")


@pytest.fixture(scope="session")
def casebook_env(request: pytest.FixtureRequest) -> Catalog:
    # when pytest starts above this directory there is no --target, so fall back to local
    target = request.config.getoption("--target", default="local")
    return TARGETS[target]()


def pytest_casebook_prepare_call(env: Catalog, args: list[Any]) -> None:
    args.insert(0, env)
