"""
pytest の設定ファイル（pytest.ini・pyproject.toml・tox.ini・setup.cfg）を、pytest の外から読む。

`load(path, ini=True)` が、pytest で動かすときと同じ casebook_* の設定を使うためのもの。
pytest 自身の探し方を簡単にしたもので、次のものには対応しない。

- `-c` / `--config-file`・`--rootdir`・`-o` / `--override-ini`（コマンドラインで変えるもの）
- 引数のパスごとの探し方（ここでは YAML のディレクトリから上にたどるだけ）
- pytest.toml・.pytest.ini や、pyproject.toml の `[tool.pytest]`（ini_options でない書き方）
"""

from __future__ import annotations

import configparser
import tomllib
from pathlib import Path

IniValue = str | list[str]


def read_ini(start: Path) -> tuple[Path | None, dict[str, IniValue]]:
    """
    `start` から上のディレクトリへたどり、最初に見つかった pytest の設定ファイルを読む。

    ディレクトリごとに、次の順に確かめ、最初に当てはまったもので止める（pytest と同じ順）。

    1. `pytest.ini`（`[pytest]` の節。節がなくても、あれば必ずこれを使う）
    2. `pyproject.toml`（`[tool.pytest.ini_options]` の表があるときだけ）
    3. `tox.ini`（`[pytest]` の節があるときだけ）
    4. `setup.cfg`（`[tool:pytest]` の節があるときだけ）

    値は pytest の ini の書き方と同じく、文字列か文字列のリストにそろえる
    （pyproject.toml の `true` や数値は文字列にする。リストはそのまま）。

    :param start: 探し始めるディレクトリ（ふつうは YAML のディレクトリ）
    :return: (見つかった設定ファイルのパス, 名前 -> 値)。見つからなければ (None, {})
    :raises ValueError: 設定ファイルを TOML / ini として読めないとき（メッセージにパスを含む）
    """
    for base in (start, *start.parents):
        found = _read_one(base)
        if found is not None:
            return found
    return None, {}


def _read_one(base: Path) -> tuple[Path, dict[str, IniValue]] | None:
    """1つのディレクトリで、pytest の設定ファイルを探して読む（なければ None）。"""
    p = base / "pytest.ini"
    if p.is_file():
        # pytest.ini は [pytest] の節がなくても、あれば必ず設定ファイルになる
        return p, _ini_section(p, "pytest") or {}
    p = base / "pyproject.toml"
    if p.is_file():
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            # TOMLDecodeError も ValueError だが、どのファイルかが分かるようにパスを添える
            raise ValueError(f"cannot read {p}: {e}") from None
        options = data.get("tool", {}).get("pytest", {}).get("ini_options")
        if isinstance(options, dict):
            # pytest と同じく、リスト以外の値（true や数値）は文字列にする
            return p, {
                str(k): [str(x) for x in v] if isinstance(v, list) else str(v)
                for k, v in options.items()
            }
    for name, section in (("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        p = base / name
        if p.is_file():
            values = _ini_section(p, section)
            if values is not None:
                return p, values
    return None


def _ini_section(path: Path, section: str) -> dict[str, IniValue] | None:
    """
    ini 形式のファイルの節を読む（節がなければ None）。

    :raises ValueError: ini として読めないとき（load(ini=True) の説明どおり ValueError にする。
        configparser.Error は ValueError ではないため）
    """
    # % を値に書けるよう、補間はしない
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding="utf-8"), source=str(path))
    except configparser.Error as e:
        raise ValueError(f"cannot read {path}: {e}") from None
    if not parser.has_section(section):
        return None
    values: dict[str, IniValue] = dict(parser.items(section))
    return values


def ini_lines(value: IniValue) -> list[str]:
    """
    linelist の値（pytest と同じく、文字列なら行ごとに分け、空の行は除く）。
    """
    if isinstance(value, list):
        return value
    return [line.strip() for line in value.split("\n") if line.strip()]


def ini_bool(name: str, value: IniValue) -> bool:
    """
    bool の値（pytest と同じく true / false・yes / no・on / off・1 / 0 を、大文字小文字を問わず）。

    :raises ValueError: どれにも当てはまらないとき
    """
    text = str(value).strip().lower()
    if text in ("y", "yes", "t", "true", "on", "1"):
        return True
    if text in ("n", "no", "f", "false", "off", "0"):
        return False
    raise ValueError(f"{name} must be true or false: {value!r}")
