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
    - bytes とそれ以外は repr() にする（`model_dump()` が使えないもの、自分を含む値も）

    ケースの結果を読める形にするためのものなので、どんな値でも例外を上げない。
    """
    try:
        return _to_jsonable(value)
    except RecursionError:
        return _safe_repr(value)


def _safe_repr(value: Any) -> str:
    """repr() にする（`__repr__` が例外を上げたり、深すぎたりするときは型名だけにする）。"""
    try:
        return repr(value)
    # 利用する側のクラスの __repr__ は、どんな例外を上げるか分からない
    except Exception:  # noqa: BLE001
        return f"<{type(value).__name__}>"


def _to_jsonable(value: Any) -> Any:
    """to_jsonable の本体。"""
    # Enum は int や str より先に見る（IntEnum・StrEnum のメンバーも `クラス名.メンバー名` にする）
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            # NaN・Infinity は整数にできない（sNaN は float にもできないので repr にする）
            return repr(value) if value.is_snan() else float(value)
        # YAML に書いた 300 や 1.5 と比べられるようにする（float は近い値への丸めを含む）
        return int(value) if value == value.to_integral_value() else float(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            **{f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)},
        }
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, set | frozenset):
        items = [_to_jsonable(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, bytes):
        return repr(value)
    # クラス自身（インスタンスではない）の model_dump は、呼べない
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump) and not isinstance(value, type):
        try:
            dumped = model_dump()
        # 利用する側のクラスの model_dump は、どんな例外を上げるか分からない
        except Exception:  # noqa: BLE001
            return _safe_repr(value)
        # 結果もまた model_dump を持つなら、モデルではない（MagicMock は何度でも返す）
        if not callable(getattr(dumped, "model_dump", None)):
            return _to_jsonable(dumped)
    return _safe_repr(value)


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


def exception_name(error: BaseException) -> str:
    """
    例外の型名。クラスの中で定義した例外は `Outer.Inner` にする（__qualname__）。

    expect の raises: は `Outer.Inner` で一致するので、期待出力や失敗の説明でも同じ名前を出す
    （`Inner` だけだと、どのクラスの例外か分からない）。組み込みの例外は __name__ と同じ。
    """
    return type(error).__qualname__


def describe_exception(error: BaseException) -> str:
    """例外を `型名: メッセージ` の1行にする（型名は exception_name()）。"""
    message = str(error)
    name = exception_name(error)
    return f"{name}: {message}" if message else name
