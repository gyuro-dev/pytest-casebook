"""外部の API を呼ぶ CLI。テストでは API をモックに差し替えたい。"""

from __future__ import annotations

import argparse
import sys
from typing import Protocol


class WeatherClient(Protocol):
    def forecast(self, city: str) -> dict[str, object]: ...


class HttpWeatherClient:
    """本物の API を呼ぶクライアント（テストでは使わない）。"""

    def forecast(self, city: str) -> dict[str, object]:
        raise RuntimeError("テストでは本物の API を呼ばない")


def main(argv: list[str], client: WeatherClient | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weather")
    parser.add_argument("city")
    args = parser.parse_args(argv)
    client = client or HttpWeatherClient()
    data = client.forecast(args.city)
    if "error" in data:
        print(f"エラー: {data['error']}", file=sys.stderr)
        return 1
    print(f"{args.city}: {data['condition']}、最高 {data['high']} 度")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
