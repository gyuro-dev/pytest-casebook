"""別プロセスでのコマンドの実行（run_subprocess）を確かめる。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from pytest_casebook import runner
from pytest_casebook.messages import language


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
    with pytest.raises(runner.CasebookRunError, match="command not found: no-such-casebook"):
        runner.run_subprocess(["no-such-casebook-command"], cwd=tmp_path)
    with (
        language("ja"),
        pytest.raises(runner.CasebookRunError, match="コマンドが見つかりません: no-such-casebook"),
    ):
        runner.run_subprocess(["no-such-casebook-command"], cwd=tmp_path)


def test_env_is_put_over_os_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASEBOOK_X", "outer")
    monkeypatch.setenv("CASEBOOK_Y", "kept")
    code = "import os; print(os.environ['CASEBOOK_X'], os.environ['CASEBOOK_Y'])"
    result = runner.run_subprocess(
        [sys.executable, "-c", code], cwd=tmp_path, env={"CASEBOOK_X": "inner"}
    )
    assert result.stdout.split() == ["inner", "kept"]
    # このプロセスの os.environ は変えない
    assert os.environ["CASEBOOK_X"] == "outer"


def test_program_is_found_on_path_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """env: で PATH を変えると、その PATH でプログラムを探す。"""
    seen: list[str | None] = []

    def which(name: str, path: str | None = None) -> None:
        seen.append(path)

    monkeypatch.setattr(runner.shutil, "which", which)
    with pytest.raises(runner.CasebookRunError):
        runner.run_subprocess(["no-such-casebook-command"], cwd=tmp_path, env={"PATH": "x"})
    assert seen == ["x"]


@pytest.mark.skipif(os.name != "nt", reason="Windows だけ環境変数の名前の大文字小文字を区別しない")
def test_env_names_are_case_insensitive_on_windows() -> None:
    merged = runner._overlay_env({"PATH": "a", "X": "1"}, {"Path": "b"})
    assert merged == {"X": "1", "Path": "b"}


def test_timeout_also_stops_grandchildren(tmp_path: Path) -> None:
    """
    時間切れのときは、コマンドが起動したプロセス（孫）も止める。

    子だけを止めると、孫が出力のパイプを持ったまま動き続け、Windows では孫が終わるまで
    待ってしまう（timeout が効かない）。POSIX でも孫が残り、あとで動き続ける。
    """
    started, finished = tmp_path / "started", tmp_path / "finished"
    grandchild = (
        f"import time; open({str(started)!r}, 'w').close(); time.sleep(2.5);"
        f" open({str(finished)!r}, 'w').close()"
    )
    child = f"import subprocess, sys; subprocess.run([sys.executable, '-c', {grandchild!r}])"
    begin = time.monotonic()
    with pytest.raises(runner.CasebookRunError, match="did not finish within"):
        runner.run_subprocess([sys.executable, "-c", child], cwd=tmp_path, timeout=1.5)
    assert started.exists()  # 孫が動き出してから時間切れになった
    assert time.monotonic() - begin < 2.5  # 孫が終わるのを待っていない
    time.sleep(3)
    assert not finished.exists()  # 孫も止まった


def test_program_that_cannot_start_is_reported(tmp_path: Path) -> None:
    """見つかっても起動できない（ディレクトリを指したなど）ときも、実行の誤りにする。"""
    with pytest.raises(runner.CasebookRunError, match="cannot start the command"):
        runner.run_subprocess([str(tmp_path)], cwd=tmp_path)


@pytest.mark.parametrize("spec", [":f", ".m:f"])
def test_bad_module_name_is_reported(spec: str) -> None:
    """空のモジュール名（ValueError）・相対 import（TypeError）も import の誤りにする。"""
    with pytest.raises(runner.CasebookRunError, match="cannot import module"):
        runner.import_callable(spec)
