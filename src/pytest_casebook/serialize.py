"""関数の戻り値や observe で取り出した値を、期待出力に書ける読みやすい文字列にする。"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import json
from pathlib import PurePath
from typing import Any


def to_jsonable(value: Any) -> Any:
    """
    JSON にできる形へ変換する。

    - tuple はリスト、辞書のキーは文字列にする
    - dataclass は `__type__`（クラス名）とフィールドの辞書にする
    - set / frozenset は順序が実行ごとに変わらないよう並べ替える
    - Enum は `クラス名.メンバー名`、日時は ISO 形式、パスは `/` 区切りにする
    - Decimal は数にする（DynamoDB の数は Decimal で返るため。整数なら int、そうでなければ float）
    - `model_dump()`（pydantic など）を持つものはその結果を使う
    - bytes とそれ以外は repr() にする
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        # YAML に書いた 300 や 1.5 と比べられるようにする（float は近い値への丸めを含む）
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            **{f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)},
        }
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, set | frozenset):
        items = [to_jsonable(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, bytes):
        return repr(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return to_jsonable(model_dump())
    return repr(value)


def serialize(value: Any) -> str:
    """戻り値を整形済みの JSON 文字列にする（日本語はそのまま）。"""
    return json.dumps(to_jsonable(value), ensure_ascii=False, indent=2)


def compact(value: Any) -> str:
    """JSON にできる値を1行の JSON にする（日本語はそのまま）。"""
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def render_rows(value: Any) -> str:
    """
    observe で取り出した値を、1件を1行にした文字列にする。

    DB の行のようなリストは、要素1つを1行の JSON にする。行の中の値が変わったときに
    差分がその1行だけに出るため、どの行が違うかが分かりやすい。

    - 文字列: そのまま
    - リスト: 要素ごとに1行（空なら `[]`）
    - 辞書: `キー: 値` を1行ずつ（空なら `{}`）。値がリストなら、その下に要素を字下げして1行ずつ
    - それ以外: 1行の JSON
    """
    if isinstance(value, str):
        return value
    value = to_jsonable(value)
    if isinstance(value, list):
        return "\n".join(compact(v) for v in value) if value else "[]"
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, list) and item:
                lines.append(f"{key}:")
                lines += [f"  {compact(v)}" for v in item]
            else:
                lines.append(f"{key}: {compact(item)}")
        return "\n".join(lines) if lines else "{}"
    return compact(value)


def describe_exception(error: BaseException) -> str:
    """例外を `型名: メッセージ` の1行にする。"""
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__
