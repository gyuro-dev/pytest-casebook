"""
pytest-casebook: a pytest plugin that removes the need to maintain test specification
sheets and automated tests separately.

- Write cases in YAML as "preconditions -> action -> expected result". The action is one of
  running a CLI, calling a Python function, or sending a request to an HTTP API
- Cases can be classified by groups into any number of levels (e.g. category / subcategory / item),
  and `--casebook-html` outputs the results as a table in that hierarchy (a test specification
  sheet)

pytest-casebook: 試験項目表と自動テストの二重管理をなくす pytest プラグイン。

- YAML に「前提条件 → 操作 → 期待結果」の形でケースを書く。操作は CLI の実行・
  Python 関数の呼び出し・HTTP の API へのリクエストのどれか
- ケースはグループで大項目・中項目・小項目のように何階層でも分類でき、
  `--casebook-html` でその階層の表（試験項目表）として結果を出力できる
"""

from pathlib import Path

from .http import HttpRequest, HttpResponse
from .model import Case, CasebookDoc, CasebookError, Group, load
from .runner import CommandResult, run_in_process

__version__ = "0.5.0"

# JSON Schema for case files (casebook_*.yaml), used for editor completion and validation.
# ケースファイル（casebook_*.yaml）の JSON Schema。エディタの補完と検証に使う
SCHEMA_PATH = Path(__file__).resolve().parent / "casebook.schema.json"

__all__ = [
    "SCHEMA_PATH",
    "Case",
    "CasebookDoc",
    "CasebookError",
    "CommandResult",
    "Group",
    "HttpRequest",
    "HttpResponse",
    "__version__",
    "load",
    "run_in_process",
]
