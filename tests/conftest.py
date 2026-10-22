"""テストで共通に使う fixture。"""

from __future__ import annotations

import pytest
from helpers import CALC_MODULE

pytest_plugins = ["pytester"]


@pytest.fixture
def project(pytester: pytest.Pytester) -> pytest.Pytester:
    """
    calc モジュールを置き、pythonpath = . で import できるようにした一時プロジェクト。

    テストは日本語のメッセージを確かめるので、言語を ja にする（既定の英語は別のテストで確かめる）。
    """
    pytester.makepyfile(calc=CALC_MODULE)
    pytester.makeini("[pytest]\npythonpath = .\ncasebook_lang = ja\n")
    return pytester
