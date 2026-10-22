"""
Read the same YAML as the tests outside pytest, and run and show only the cases whose meta has demo.

  uv run python examples-en/11_meta_load/show_demo_en.py
"""

from pathlib import Path

import pytest_casebook
from pytest_casebook.runner import import_callable

HERE = Path(__file__).resolve().parent

doc = pytest_casebook.load(HERE / "casebook_meta.yaml")
print(f"{doc.title} (owner: {doc.meta.get('owner')})")
for case in doc.cases:
    if not case.meta.get("demo"):
        continue
    func = import_callable(str(case.call))
    print(f"- {' > '.join(case.path)} > {case.name}: {case.description}")
    print(f"  {case.call}{tuple(case.args)} -> {func(*case.args, **case.kwargs)!r}")
