"""
CLI を別プロセスではなく同じプロセスで動かし、モックのクライアントを渡す。

pytest_casebook_run_command で run_in_process を返すと、別プロセスを立てずに main を呼ぶ。
例外は終了コード 1 と stderr の「型名: メッセージ」になり、sys.exit() は終了コードになる。
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import weather

from pytest_casebook import run_in_process


class FakeWeatherClient:
    """決まった答えを返すモック。"""

    DATA: ClassVar[dict[str, dict[str, object]]] = {
        "tokyo": {"condition": "晴れ", "high": 25},
        "sapporo": {"condition": "雪", "high": -2},
    }

    def forecast(self, city: str) -> dict[str, object]:
        return self.DATA.get(city, {"error": f"{city} の予報はありません"})


@pytest.fixture(scope="session")
def casebook_env() -> FakeWeatherClient:
    return FakeWeatherClient()


def pytest_casebook_run_command(argv: list[str], env: FakeWeatherClient) -> Any:
    # command_prefix の "weather" を除いた残りを main に渡す
    return run_in_process(lambda args: weather.main(args, client=env), argv[1:])
