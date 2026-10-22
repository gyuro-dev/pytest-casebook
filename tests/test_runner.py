"""別プロセスでのコマンドの実行（run_subprocess）を確かめる。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pytest_casebook import runner


def test_program_name_is_found_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    `python` のような名前は PATH の順に探す。

    Windows は PATH より先に親プロセスの実行ファイルのディレクトリを探すため、探しておかないと
    仮想環境ではなく元の Python が動き、仮想環境のパッケージ（coverage など）が使えない。
    """
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]])
    )
    result = runner.run_subprocess(["python", "-c", "import sys; print(sys.prefix)"], cwd=tmp_path)
    assert result.exit_code == 0
    assert Path(result.stdout.strip()) == Path(sys.prefix)


def test_program_with_path_is_used_as_is(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("パスを含む名前は PATH から探さない")

    monkeypatch.setattr(runner.shutil, "which", fail)
    result = runner.run_subprocess([sys.executable, "-c", "print('ok')"], cwd=tmp_path)
    assert result.stdout.strip() == "ok"


def test_unknown_program_is_reported(tmp_path: Path) -> None:
    with pytest.raises(runner.CasebookRunError, match="コマンドが見つかりません: no-such-casebook"):
        runner.run_subprocess(["no-such-casebook-command"], cwd=tmp_path)
