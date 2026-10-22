"""
テストと同じ YAML を pytest の外で読み、meta の demo が付いたケースだけを実行して見せる。

  uv run python examples/11_meta_load/show_demo.py
"""

from pathlib import Path

import pytest_casebook
from pytest_casebook.runner import import_callable

HERE = Path(__file__).resolve().parent

doc = pytest_casebook.load(HERE / "casebook_meta.yaml")
print(f"{doc.title}（担当: {doc.meta.get('owner')}）")
for case in doc.cases:
    if not case.meta.get("demo"):
        continue
    func = import_callable(str(case.call))
    print(f"- {' > '.join(case.path)} > {case.name}: {case.description}")
    print(f"  {case.call}{tuple(case.args)} -> {func(*case.args, **case.kwargs)!r}")
