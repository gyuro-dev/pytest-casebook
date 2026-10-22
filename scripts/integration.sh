#!/usr/bin/env bash
# =============================================================================
# 実起動の試験: PostgreSQL と API サーバーを Docker で本当に起動し、
# integration/ のケース（HTTP・CLI・関数 ＋ 実際の DB）を実行する
#
#   scripts/integration.sh            # 起動 → 試験 → 片付け
#   KEEP=1 scripts/integration.sh     # 終わってもコンテナを残す（調べるとき）
#   UPDATE=1 scripts/integration.sh   # 期待出力ファイルを作り直す（--casebook-update）
#
# 前提: Docker Engine（compose を含む）と uv。WSL なら scripts/wsl/setup-docker.sh で入る。
# 結果は reports/integration/ に残す（summary.txt に、OS・Docker・PostgreSQL・Python・
# pytest の版と結果を書く）。失敗すれば終了コード 1 で終わる。
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
OUT="reports/integration"
SUMMARY="$OUT/summary.txt"
COMPOSE=(docker compose -f integration/compose.yaml)
export CASEBOOK_DB_PORT="${CASEBOOK_DB_PORT:-55432}"
export CASEBOOK_API_PORT="${CASEBOOK_API_PORT:-58000}"
export CASEBOOK_DB_URL="postgresql://casebook:casebook@localhost:${CASEBOOK_DB_PORT}/casebook"
export CASEBOOK_API_URL="http://localhost:${CASEBOOK_API_PORT}"
export PYTHONIOENCODING=utf-8

cleanup() {
  # 片付けのコマンドの結果で、試験の終了コードが変わらないようにする
  local rc=$?
  if [ "${KEEP:-0}" = "1" ]; then
    echo "コンテナを残しました（片付け: ${COMPOSE[*]} down -v）"
  else
    "${COMPOSE[@]}" down -v --remove-orphans > "$OUT/down.txt" 2>&1
  fi
  exit $rc
}

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== 前の試験のコンテナを片付け、起動する（初回はイメージを作るので時間がかかる）"
"${COMPOSE[@]}" down -v --remove-orphans > /dev/null 2>&1
trap cleanup EXIT
if ! "${COMPOSE[@]}" up -d --build --wait > "$OUT/up.txt" 2>&1; then
  echo "起動できませんでした（$OUT/up.txt）"
  "${COMPOSE[@]}" logs > "$OUT/logs.txt" 2>&1
  tail -20 "$OUT/up.txt"
  exit 1
fi

echo "== 依存を uv.lock のとおりに入れる"
uv sync --frozen --group integration > "$OUT/setup.txt" 2>&1 || { tail -20 "$OUT/setup.txt"; exit 1; }

echo "== 試験を実行する"
update=()
[ "${UPDATE:-0}" = "1" ] && update=(--casebook-update)
uv run --no-sync pytest integration -p no:cacheprovider -v "${update[@]}" \
  --casebook-html="$OUT/report.html" --junitxml="$OUT/junit.xml" > "$OUT/tests.txt" 2>&1
status=$?
"${COMPOSE[@]}" logs api > "$OUT/api.log" 2>&1

{
  echo "# pytest-casebook の実起動の試験の結果"
  echo "date:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "os:         $(uname -srm)"
  [ -r /etc/os-release ] && echo "distro:     $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "docker:     $(docker version --format '{{.Server.Version}}') / $(docker compose version --short)"
  echo "postgres:   $("${COMPOSE[@]}" exec -T db psql -U casebook -tAc 'show server_version')"
  echo "api image:  $("${COMPOSE[@]}" exec -T api python -c 'import sys, fastapi, uvicorn, psycopg; print(f"python {sys.version.split()[0]} / fastapi {fastapi.__version__} / uvicorn {uvicorn.__version__} / psycopg {psycopg.__version__}")')"
  echo "runner:     $(uv run --no-sync python -c 'import sys, pytest, psycopg; print(f"python {sys.version.split()[0]} / pytest {pytest.__version__} / psycopg {psycopg.__version__}")')"
  echo "uv:         $(uv --version)"
  echo "commit:     $(git rev-parse --short HEAD 2>/dev/null)$(git diff --quiet 2>/dev/null || echo ' (未 commit の変更あり)')"
  echo
  echo "result:     $([ $status -eq 0 ] && echo ok || echo NG) $(tail -n 1 "$OUT/tests.txt" | tr -d '=')"
  echo
  grep -E "(PASSED|FAILED|ERROR|SKIPPED)" "$OUT/tests.txt" | sed 's/ *\[ *[0-9]*%\]//'
} > "$SUMMARY"

cat "$SUMMARY"
exit $status
