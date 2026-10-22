#!/usr/bin/env bash
# =============================================================================
# 再現できる形で試験を実施する（Linux・WSL・macOS・Windows の Git Bash）
#
#   scripts/check.sh                 # Python 3.11〜3.15 × pytest 8 / 9 を順に試す
#   scripts/check.sh 3.12            # Python の版を指定する
#   PYTESTS="9" scripts/check.sh     # pytest の版を絞る（既定は "8 9"）
#
# - 依存は uv.lock のとおりに入れる（uv sync --frozen）。pytest 8 の組だけは、
#   uv.lock の pytest 9 を pytest 8 の最新に入れ替える
# - 版ごとに別の仮想環境（$CASEBOOK_VENVS/py<版>-pytest<版>）を作るので、互いに混ざらない
# - 結果は reports/check/ に残す（summary.txt に、OS・Python・pytest・uv の版と、
#   それぞれの結果を書く）
# - 1つでも失敗すれば、終了コード 1 で終わる
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
PYTHONS=("$@")
[ ${#PYTHONS[@]} -eq 0 ] && PYTHONS=(3.11 3.12 3.13 3.14 3.15)
read -r -a PYTEST_MAJORS <<< "${PYTESTS:-8 9}"
VENVS="${CASEBOOK_VENVS:-.venvs}"
OUT="reports/check"
SUMMARY="$OUT/summary.txt"
export PYTHONIOENCODING=utf-8
# PyYAML に wheel のない Python（今は 3.15）では、ソースから作る。C コンパイラのない
# Windows でも作れるよう、C 拡張（libyaml）を使わない純粋な Python の版にする
export PYYAML_FORCE_LIBYAML="${PYYAML_FORCE_LIBYAML:-0}"

rm -rf "$OUT"
mkdir -p "$OUT"
{
  echo "# pytest-casebook の試験の結果"
  echo "date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "os:     $(uname -srm)"
  [ -r /etc/os-release ] && echo "distro: $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "uv:     $(uv --version)"
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null)$(git diff --quiet 2>/dev/null || echo ' (未 commit の変更あり)')"
  echo
} > "$SUMMARY"

failed=0

# ruff は Python の版によらないので1回だけ
if uv run --frozen ruff check . > "$OUT/ruff.txt" 2>&1 && uv run --frozen ruff format --check . >> "$OUT/ruff.txt" 2>&1; then
  echo "ruff                         : ok" >> "$SUMMARY"
else
  echo "ruff                         : NG（$OUT/ruff.txt）" >> "$SUMMARY"
  failed=1
fi

# 型の検査（mypy の strict）。pyproject.toml の python_version（3.11）で調べるので1回だけ
if uv run --frozen mypy > "$OUT/mypy.txt" 2>&1; then
  echo "mypy                         : ok" >> "$SUMMARY"
else
  echo "mypy                         : NG（$OUT/mypy.txt）" >> "$SUMMARY"
  failed=1
fi

for py in "${PYTHONS[@]}"; do
  for pt in "${PYTEST_MAJORS[@]}"; do
    name="py${py}-pytest${pt}"
    venv="$VENVS/$name"
    dir="$OUT/$name"
    mkdir -p "$dir"
    export UV_PROJECT_ENVIRONMENT="$venv"
    # .python-version（3.12）ではなく、この組の Python を使う
    export UV_PYTHON="$py"

    if ! uv sync --frozen --python "$py" > "$dir/setup.txt" 2>&1; then
      echo "$(printf '%-29s' "$name"): NG（環境を作れません。$dir/setup.txt）" >> "$SUMMARY"
      failed=1
      continue
    fi
    if [ "$pt" != "9" ]; then
      uv pip install --python "$venv" "pytest>=${pt},<$((pt + 1))" >> "$dir/setup.txt" 2>&1
    fi
    versions=$(uv run --no-sync python -c \
      "import sys, pytest; print(f'python {sys.version.split()[0]} / pytest {pytest.__version__}')")

    uv run --no-sync pytest -p no:cacheprovider -q \
      --junitxml="$dir/junit.xml" > "$dir/tests.txt" 2>&1
    tests=$?
    uv run --no-sync pytest examples -p no:cacheprovider -q -o casebook_lang=ja \
      --casebook-html="$dir/examples.html" > "$dir/examples.txt" 2>&1
    examples=$?

    result="ok"
    if [ $tests -ne 0 ] || [ $examples -ne 0 ]; then
      result="NG（tests=$tests examples=$examples。$dir/）"
      failed=1
    fi
    echo "$(printf '%-29s' "$name"): $result  [$versions] $(tail -n 1 "$dir/tests.txt" | tr -d '=')" >> "$SUMMARY"
  done
done

cat "$SUMMARY"
exit $failed
