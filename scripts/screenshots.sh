#!/usr/bin/env bash
# =============================================================================
# README に載せる HTML レポートのスクリーンショットを作り直す（Windows の Git Bash）
#
#   scripts/screenshots.sh
#   EDGE="/c/path/to/msedge.exe" scripts/screenshots.sh   # Edge の場所を指定する
#
# - docs/screenshots（日本語）と docs/screenshots-en（英語。casebook_lang=en）のケースを
#   --casebook-html 付きで実行し、HTML を作る
#   （わざと失敗を1件含むので、pytest の終了コードは 1 になる）
# - Microsoft Edge のヘッドレスモードで、ライトモードの画像を docs/images/ に書く
#     report-top.png / report-top-en.png            README の冒頭用（ケースの表の上のほう）
#     report-overview.png / report-overview-en.png  表の全体
#     report-failure.png / report-failure-en.png    失敗の詳細を開いたところ
#                                                   （HTML のコピーで details を開く）
# - 途中のファイルは reports/screenshots/ に残す
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
EDGE="${EDGE:-/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe}"
WORK="reports/screenshots"
OUT="docs/images"
WIDTH=1280
EXPECTED="1 failed, 11 passed, 1 skipped, 1 xfailed"
export PYTHONIOENCODING=utf-8

if [ ! -x "$EDGE" ]; then
  echo "Microsoft Edge が見つかりません: $EDGE（EDGE=... で場所を指定してください）" >&2
  exit 1
fi

rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

# $1: HTML、$2: 画像、$3: 高さ
shot() {
  "$EDGE" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --no-first-run --user-data-dir="$(cygpath -w "$PWD/$WORK/edge-profile")" \
    --window-size="$WIDTH,$3" --virtual-time-budget=2000 \
    --screenshot="$(cygpath -w "$PWD/$2")" "file:///$(cygpath -m "$PWD/$1")" \
    > "$WORK/edge.txt" 2>&1
  echo "$2"
}

# $1: ケースのディレクトリ、$2: レポートの言語、$3: 画像の名前の末尾（"" か "-en"）
render() {
  local dir="$WORK/$2"
  mkdir -p "$dir"
  # 失敗を含むので終了コードは見ない。HTML ができたかどうかで確かめる
  uv run pytest "$1" -p no:cacheprovider -q -o casebook_lang="$2" \
    --casebook-html="$dir/report.html" > "$dir/pytest.txt" 2>&1 || true
  if [ ! -s "$dir/report.html" ]; then
    cat "$dir/pytest.txt" >&2
    echo "HTML ができませんでした: $1" >&2
    exit 1
  fi
  if ! grep -q "$EXPECTED" "$dir/pytest.txt"; then
    cat "$dir/pytest.txt" >&2
    echo "結果が想定（$EXPECTED）と違います: $1" >&2
    exit 1
  fi

  # OS がダークモードでもライトモードで写す
  sed "s/<html lang=\"$2\">/<html lang=\"$2\" data-theme=\"light\">/" \
    "$dir/report.html" > "$dir/overview.html"
  # 失敗の詳細を開き、失敗した行の1つ上の行（大項目・中項目の名前がある行）から写す。
  # ヘッドレスの Edge はスクロールすると白い画像になるので、スクロールせずに body を上にずらす
  local top='const r = document.querySelector("tr.failed").previousElementSibling;'
  top+=' document.body.style.marginTop = (16 - r.getBoundingClientRect().top) + "px";'
  sed -e 's/<details>/<details open>/g' -e "s#</body>#<script>$top</script></body>#" \
    "$dir/overview.html" > "$dir/failure.html"
  # README の冒頭に置く、縦に短い画像。題名と全体の件数のすぐ下にケースの表が来るよう、
  # ファイルごとの説明・集計の表・確認が必要なケースの一覧を隠す。表は行の途中で切れない
  # よう、最初の7件（価格計算と、在庫の通常時）だけを出す
  local hide='document.querySelectorAll("section > :not(h2):not(.scroll),'
  hide+=' table.cases tbody tr:nth-child(n+8)").forEach(e => e.style.display = "none");'
  sed "s#</body>#<script>$hide</script></body>#" "$dir/overview.html" > "$dir/top.html"

  shot "$dir/top.html" "$OUT/report-top$3.png" 680
  shot "$dir/overview.html" "$OUT/report-overview$3.png" 1440
  shot "$dir/failure.html" "$OUT/report-failure$3.png" 648
}

render docs/screenshots ja ""
render docs/screenshots-en en "-en"
