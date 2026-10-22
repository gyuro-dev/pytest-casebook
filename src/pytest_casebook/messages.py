"""
日本語と英語の文言（ini の casebook_lang で言語を選ぶ）。

- `TEXTS`: HTML レポートの決まった文言（列名・結果・集計など）
- `MESSAGES`: 期待値との比較で失敗したときのメッセージ

比較の失敗だけを対象にする。YAML の書き方の誤りや、コマンドが見つからないなどの
実行の誤りは、日本語のまま出す。
"""

from __future__ import annotations

from typing import Any

# HTML レポートの決まった文言
TEXTS: dict[str, dict[str, Any]] = {
    "ja": {
        "outcomes": {
            "passed": "成功",
            "updated": "更新",
            "skipped": "スキップ",
            "xfailed": "想定どおり失敗",
            "xpassed": "想定外に成功",
            "failed": "失敗",
            "error": "エラー",
        },
        "title": "試験項目表",
        "levels": ("大項目", "中項目", "小項目"),
        "level_n": "第{n}階層",
        "group": "分類",
        "ungrouped": "（分類なし）",
        "count": "件数",
        "result": "結果",
        "problems": "確認が必要なケース",
        "columns": ("ケース", "確認内容", "前提条件", "期待結果", "結果", "時間"),
        "details": "失敗の詳細",
        "golden_dir": "期待出力ファイルの置き場所: {dir}/",
        "cases": "{n} 件",
        "total": "全 {n} 件",
        "generated": "{at} に作成",
        "written": "試験項目表（HTML）: {path}",
        "state": "状態: {state}",
        "files": "ファイル: {files}",
        "golden": "期待出力ファイル（{name}）",
        "observe": "観察: {targets}",
        "contains": "{label} が「{pattern}」を含む",
        "regex": "{label} が「{pattern}」（正規表現）に合う",
    },
    "en": {
        "outcomes": {
            "passed": "Passed",
            "updated": "Updated",
            "skipped": "Skipped",
            "xfailed": "Expected failure",
            "xpassed": "Unexpected pass",
            "failed": "Failed",
            "error": "Error",
        },
        "title": "Test Specification",
        "levels": ("Category", "Subcategory", "Item"),
        "level_n": "Level {n}",
        "group": "Category",
        "ungrouped": "(ungrouped)",
        "count": "Cases",
        "result": "Results",
        "problems": "Cases to check",
        "columns": (
            "Case",
            "What is checked",
            "Preconditions",
            "Expected result",
            "Result",
            "Time",
        ),
        "details": "Failure details",
        "golden_dir": "Golden files: {dir}/",
        "cases": "{n} cases",
        "total": "{n} cases in total",
        "generated": "Generated at {at}",
        "written": "Test specification (HTML): {path}",
        "state": "State: {state}",
        "files": "Files: {files}",
        "golden": "Golden file ({name})",
        "observe": "Observe: {targets}",
        "contains": '{label} contains "{pattern}"',
        "regex": '{label} matches the regex "{pattern}"',
    },
}
LANGS = tuple(TEXTS)

# 期待値との比較で失敗したときのメッセージ
MESSAGES: dict[str, dict[str, str]] = {
    "ja": {
        "line": "（{line} 行目）",
        "mismatch": "{label}: 期待 {expected} / 実際 {actual}",
        "text_differs": "{label}: 期待と違います",
        "diff_expected": "{label}（期待）",
        "diff_actual": "{label}（実際）",
        "not_contained": "{label}: {pattern} が含まれていません（実際 {actual}）",
        "no_regex_match": "{label}: 正規表現 {pattern} に合いません（実際 {actual}）",
        "missing_key": "{label}: 実際の値にありません",
        "count_differs": "{label}: 件数が違います（期待 {expected} 件 / 実際 {actual} 件）",
        "not_string": "{label}: 文字列ではありません（実際 {actual}）",
        "not_list": "{label}: リストではありません（実際 {actual}）",
        "no_element": "{label}: {item} に合う要素がありません（期待の [{index}]）",
        "not_json": "json: 本文が JSON ではありません（本文 {body}）",
        "missing_header": "headers.{name}: レスポンスにありません",
        "raised": "例外が出ました: {described}",
        "not_raised": "raises: 例外が出ませんでした（戻り値 {returned}）",
        "expect_differs": "期待結果と違います:",
        "actual_section": "----- 実際の {name} -----",
        "golden_missing": (
            "[{name}] 期待出力 {label} がありません。"
            "`--casebook-update` を付けて作成し、内容を確認してください。"
        ),
        "golden_differs": (
            "出力が期待と異なります。意図した変更なら `--casebook-update` で更新してください。"
        ),
        "golden_actual": "実際の出力",
        "golden_orphans": "{yaml} にない期待出力が {golden_dir} にあります: {orphans}",
        "no_files": "（ファイルなし）",
    },
    "en": {
        "line": " (line {line})",
        "mismatch": "{label}: expected {expected} / actual {actual}",
        "text_differs": "{label}: differs from the expected value",
        "diff_expected": "{label} (expected)",
        "diff_actual": "{label} (actual)",
        "not_contained": "{label}: does not contain {pattern} (actual {actual})",
        "no_regex_match": "{label}: does not match the regex {pattern} (actual {actual})",
        "missing_key": "{label}: missing in the actual value",
        "count_differs": "{label}: number of items differs (expected {expected} / actual {actual})",
        "not_string": "{label}: not a string (actual {actual})",
        "not_list": "{label}: not a list (actual {actual})",
        "no_element": "{label}: no element matches {item} (expected [{index}])",
        "not_json": "json: the body is not JSON (body {body})",
        "missing_header": "headers.{name}: not in the response",
        "raised": "an exception was raised: {described}",
        "not_raised": "raises: no exception was raised (returned {returned})",
        "expect_differs": "Differs from the expected result:",
        "actual_section": "----- actual {name} -----",
        "golden_missing": (
            "[{name}] The golden file {label} does not exist. "
            "Create it with `--casebook-update` and review its contents."
        ),
        "golden_differs": (
            "The output differs from the golden file. "
            "If the change is intended, update it with `--casebook-update`."
        ),
        "golden_actual": "actual output",
        "golden_orphans": "golden files not used by {yaml} are left in {golden_dir}: {orphans}",
        "no_files": "(no files)",
    },
}
