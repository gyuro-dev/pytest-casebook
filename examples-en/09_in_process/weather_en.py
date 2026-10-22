"""A CLI that calls an external API. In tests we want to replace the API with a mock."""

from __future__ import annotations

import argparse
import sys
from typing import Protocol


class WeatherClient(Protocol):
    def forecast(self, city: str) -> dict[str, object]: ...


class HttpWeatherClient:
    """A client that calls the real API (not used in tests)."""

    def forecast(self, city: str) -> dict[str, object]:
        raise RuntimeError("tests must not call the real API")


def main(argv: list[str], client: WeatherClient | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weather")
    parser.add_argument("city")
    args = parser.parse_args(argv)
    client = client or HttpWeatherClient()
    data = client.forecast(args.city)
    if "error" in data:
        print(f"error: {data['error']}", file=sys.stderr)
        return 1
    print(f"{args.city}: {data['condition']}, high of {data['high']} degrees")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
