"""
Run the CLI in-process instead of in a subprocess, and pass it a mock client.

When pytest_casebook_run_command returns run_in_process, main is called without starting a
subprocess. An exception becomes exit code 1 and "TypeName: message" on stderr, and
sys.exit() becomes the exit code.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import weather_en

from pytest_casebook import run_in_process


class FakeWeatherClient:
    """A mock that returns fixed answers."""

    DATA: ClassVar[dict[str, dict[str, object]]] = {
        "tokyo": {"condition": "sunny", "high": 25},
        "sapporo": {"condition": "snow", "high": -2},
    }

    def forecast(self, city: str) -> dict[str, object]:
        return self.DATA.get(city, {"error": f"no forecast for {city}"})


@pytest.fixture(scope="session")
def casebook_env() -> FakeWeatherClient:
    return FakeWeatherClient()


def pytest_casebook_run_command(argv: list[str], env: FakeWeatherClient) -> Any:
    # pass main everything after the "weather" of command_prefix
    return run_in_process(lambda args: weather_en.main(args, client=env), argv[1:])
