"""
日本語と英語の文言（ini の casebook_lang で言語を選ぶ）。

- `TEXTS`: HTML レポートの決まった文言（列名・結果・集計など）
- `MESSAGES`: 期待値との比較で失敗したときのメッセージ
- `ERRORS`: YAML の書き方の誤りと、実行の誤り（コマンドが見つからないなど）のメッセージ
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

# HTML レポートの決まった文言
TEXTS: dict[str, dict[str, Any]] = {
    "ja": {
        "outcomes": {
            "notrun": "未実施",
            "passed": "成功",
            "manual": "手動",
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
        "golden_contents": "期待出力（{name}）",
        "golden_note": "期待出力の中の <…> は、実行ごとに変わる値の置き換えです",
        "more_lines": "…（あと {n} 行）",
        "golden_open_all": "期待出力をすべて開く",
        "golden_close_all": "期待出力をすべて閉じる",
        "golden_dir": "期待出力ファイルの置き場所: {dir}/",
        "cases": "{n} 件",
        "total": "全 {n} 件",
        "generated": "{at} に作成",
        "filter": "絞り込み",
        "filter_all": "すべて",
        "filter_placeholder": "グループ・ケース名・コマンド・確認内容などの文字で絞り込み",
        "filter_shown": "{shown} / {total} 件を表示",
        "filter_none": "条件に合うケースはありません",
        "written": "試験項目表（HTML）: {path}",
        "updated_golden": "書き直した期待出力: {n} 件",
        "state": "状態: {state}",
        "files": "ファイル: {files}",
        "env": "環境変数: {env}",
        "golden": "期待出力ファイル（{name}）",
        "golden_see": "下の期待出力を見る（{name}）",
        "observe": "実行後の値: {targets}",
        "contains": "{label} が「{pattern}」を含む",
        "regex": "{label} が「{pattern}」（正規表現）に合う",
        "manual_steps": "手動: {steps}",
    },
    "en": {
        "outcomes": {
            "notrun": "Not run",
            "passed": "Passed",
            "manual": "Manual",
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
        "golden_contents": "Golden file ({name})",
        "golden_note": (
            "<…> in the golden contents stands for a value replaced because it changes between runs"
        ),
        "more_lines": "… ({n} more lines)",
        "golden_open_all": "Expand all golden files",
        "golden_close_all": "Collapse all golden files",
        "golden_dir": "Golden files: {dir}/",
        "cases": "{n} cases",
        "total": "{n} cases in total",
        "generated": "Generated at {at}",
        "filter": "Filter",
        "filter_all": "All",
        "filter_placeholder": "Filter by group, case name, command, description, ...",
        "filter_shown": "Showing {shown} of {total} cases",
        "filter_none": "No matching cases",
        "written": "Test specification (HTML): {path}",
        "updated_golden": "Updated golden files: {n}",
        "state": "State: {state}",
        "files": "Files: {files}",
        "env": "Environment: {env}",
        "golden": "Golden file ({name})",
        "golden_see": "See the golden file below ({name})",
        "observe": "Observe: {targets}",
        "contains": '{label} contains "{pattern}"',
        "regex": '{label} matches the regex "{pattern}"',
        "manual_steps": "Manual: {steps}",
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
        "golden_shared": (
            "[{name}] 期待出力 {label} はケース {other} も使っていて、結果が違います。"
            "golden: でファイルを分けてください。"
        ),
        "golden_orphans": "{yaml} にない期待出力が {golden_dir} にあります: {orphans}",
        "no_files": "（ファイルなし）",
        "manual_not_run": "手動のケース（result: がまだありません）",
        "manual_failed": "[{name}] 手動で確かめた結果が failed です",
        "manual_skipped": "手動の確認を行っていません（result: skipped）",
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
        "golden_shared": (
            "[{name}] The golden file {label} is also used by case {other} with a different "
            "result. Give the cases separate files with golden:."
        ),
        "golden_orphans": "golden files not used by {yaml} are left in {golden_dir}: {orphans}",
        "no_files": "(no files)",
        "manual_not_run": "manual case (no result: yet)",
        "manual_failed": "[{name}] the manual check result is failed",
        "manual_skipped": "the manual check was not done (result: skipped)",
    },
}

# YAML の書き方の誤りと、実行の誤り（コマンドが見つからないなど）のメッセージ
ERRORS: dict[str, dict[str, str]] = {
    "ja": {
        "line": "（{line} 行目）",
        "in_group": "（グループ {name}）",
        "in_case": "（ケース {name}）",
        "unknown_keys": "{where}: 知らないキーがあります: {keys}",
        "not_string": "{where}: {key} は文字列で書いてください",
        "not_bool": "{where}: {key} は true か false で書いてください",
        "not_string_list": "{where}: {key} は文字列のリストで書いてください",
        "normalize_list": "{where}: normalize は {{pattern, replace}} のリストで書いてください",
        "normalize_item": "{where}: {{pattern, replace}} の形で書いてください",
        "bad_regex": "{where}: 正規表現の誤りです: {error}",
        "yaml_hint": (
            "\nヒント: 値の途中に「: 」（コロンと空白）があると区切りとして読まれます。"
            '値全体を " で囲んでください（例: description: "setup: の説明"）'
        ),
        "yaml_error": "{where}: YAML として読めません: {error}{hint}",
        "top_mapping": "{where}: 先頭は title や cases を持つマッピングで書いてください",
        "states_mapping": "{where}: states は 状態名 -> 内容 のマッピングで書いてください",
        "no_cases": "{where}: cases にケースがありません",
        "duplicate_names": "{where}: ケース名が重複しています: {names}",
        "duplicate_names_case": (
            "{where}: 大文字小文字だけが違うケース名があります"
            "（Windows では期待出力が同じファイルになります）: {names}"
        ),
        "reason_string": (
            "{where}: {key} には理由を文字列で書いてください（例: {key}: 不具合 #12 の修正待ち）"
        ),
        "reserved_name": (
            "{where}: ケース名 {name} は期待出力の消し忘れの確認に使うので、"
            "別の名前にしてください（または check_orphans: false）"
        ),
        "items_list": "{where}: ケースまたはグループのリストで書いてください",
        "item_mapping": "{where}: ケースまたはグループをマッピングで書いてください",
        "params_list": (
            "{where}: params は、ケースに重ねる内容のマッピングを1つ以上並べたリストで"
            "書いてください"
        ),
        "params_name": "{where}: params の各要素には name（ケース名に足す名前）を書いてください",
        "params_nested": "{where}: params の中に params は書けません",
        "bad_name": (
            "{where}: name に使えるのは文字（日本語も可）・数字・_・-・. で、"
            "先頭に . と - は使えません: {name}"
        ),
        "one_action": "{where}: command・call・request・manual のどれか1つだけを書いてください",
        "manual_keys": "{where}: manual のケースには {keys} を書けません",
        "manual_expect": (
            "{where}: manual のケースの expect は、文字列か文字列のリストで書いてください"
        ),
        "result_only_manual": "{where}: result は manual のケースにだけ書けます",
        "result_value": "{where}: result は {values} のどれかで書いてください",
        "empty_command": "{where}: command が空です（command_prefix もありません）",
        "bad_shell": "{where}: {key} を引数に区切れません（{error}）",
        "not_utf8": "{where}: UTF-8 で読めません（{error}）",
        "bad_call": "{where}: call は 'モジュール:関数' の形で書いてください: {call}",
        "args_only_call": "{where}: args / kwargs は call のケースにだけ書けます",
        "stdin_only_command": "{where}: stdin は command のケースにだけ書けます",
        "stdin_file_only_command": "{where}: stdin_file は command のケースにだけ書けます",
        "stdin_and_file": "{where}: stdin と stdin_file は同時に書けません",
        "stdin_file_path": (
            "{where}: stdin_file は YAML のディレクトリの中を指す相対パスで書いてください: {name}"
        ),
        "env_only_command": "{where}: env は command のケースにだけ書けます",
        "env_mapping": (
            "{where}: env は 変数名 -> 値（文字列か数値。null で外側の値を消す）の"
            "マッピングで書いてください"
        ),
        "args_list": "{where}: args はリストで書いてください",
        "kwargs_mapping": "{where}: kwargs は 引数名 -> 値 のマッピングで書いてください",
        "timeout_number": "{where}: timeout は 0 より大きい秒数（数値）で書いてください",
        "state_without_states": "{where}: states がないのに state: {state} を指定しています",
        "unknown_state": "{where}: states に {state} がありません",
        "meta_mapping": "{where}: meta は キー -> 値 のマッピングで書いてください",
        "setup_mapping": "{where}: setup は マッピングで書いてください",
        "setup_files": "{where}: setup.files は ファイル名 -> 内容（文字列）で書いてください",
        "setup_file_path": (
            "{where}: setup.files のファイル名は作業ディレクトリからの相対パスで書いてください: "
            "{name}"
        ),
        "golden_path": "{where}: golden は期待出力の置き場所からの相対パスで書いてください: {name}",
        "expect_regex": "{where}: expect.{key} の正規表現の誤りです: {error}",
        "expect_text": (
            "{where}: expect.{key} は文字列か、{{contains: ...}} / {{regex: ...}} の"
            "どれかで書いてください"
        ),
        "expect_mapping": "{where}: expect は 項目 -> 期待値 のマッピングで、1つ以上書いてください",
        "expect_kind": "{where}: expect.{key} は {kinds} のケースにだけ書けます",
        "return_and_raises": (
            "{where}: expect には return と raises のどちらか一方だけを書いてください"
        ),
        "observe_not_in_expect": (
            "{where}: observe: の {targets} が expect: にありません。expect: のケースでは、"
            "確かめる値を expect: に書いてください（expect: に書けば observe: は要りません）"
        ),
        "exit_code_int": "{where}: expect.exit_code は整数で書いてください",
        "status_int": "{where}: expect.status は整数で書いてください",
        "headers_mapping": "{where}: expect.headers は ヘッダー名 -> 値 で書いてください",
        "name_value_mapping": "{where}: {key} は 名前 -> 値 のマッピングで書いてください",
        "request_defaults_mapping": "{where}: request_defaults は マッピングで書いてください",
        "request_form": (
            "{where}: request は 'メソッド パス'（例: 'POST /users'）の形で書いてください"
        ),
        "request_type": "{where}: request は 文字列かマッピングで書いてください",
        "request_method": "{where}: request.method が HTTP のメソッドではありません: {method}",
        "request_path": "{where}: request.path は / で始めてください: {path}",
        "query_mapping": "{where}: request.query は 名前 -> 値 のマッピングで書いてください",
        "json_and_body": "{where}: request には json と body のどちらか一方だけを書いてください",
        "unknown_matcher": "{where}: 知らない比べ方です: {name}（使えるのは {known}）",
        "matcher_string": "{where}: {name} には文字列を書いてください",
        "matcher_list": "{where}: {name} にはリストを書いてください",
        "command_not_found": "コマンドが見つかりません: {program}",
        "command_start_failed": "コマンドを起動できません: {program}（{error}）",
        "stdin_file_missing": "stdin_file が見つかりません: {name}",
        "command_timeout": "{timeout} 秒以内に終わりませんでした: {argv}",
        "call_timeout": (
            "call: {call} が {timeout} 秒以内に終わりませんでした"
            "（関数は止められないため、裏で動き続けます）"
        ),
        "request_timeout": (
            "request: {request} が {timeout} 秒以内に終わりませんでした"
            "（pytest_casebook_request hook は止められないため、裏で動き続けます）"
        ),
        "import_failed": "call: モジュール {module} を import できません: {error}",
        "attr_missing": "call: {spec} が見つかりません（{attr} がありません）",
        "not_callable": "call: {spec} は呼び出せません",
        "no_request_hook": (
            "request: を送れません（conftest.py に pytest_casebook_request hook を書いてください）"
        ),
        "bad_response": (
            "pytest_casebook_request hook は HttpResponse を返してください（返したもの: {type}）"
        ),
        "observe_failed": (
            "observe: {target} を取り出せません"
            "（pytest_casebook_observe hook がないか、None を返しました）"
        ),
        "did_you_mean": "。expect の {key} の書き間違いではありませんか？",
        "manual_not_runnable": "手動のケースは実行できません: {name}",
    },
    "en": {
        "line": " (line {line})",
        "in_group": " (group {name})",
        "in_case": " (case {name})",
        "unknown_keys": "{where}: unknown keys: {keys}",
        "not_string": "{where}: {key} must be a string",
        "not_bool": "{where}: {key} must be true or false",
        "not_string_list": "{where}: {key} must be a list of strings",
        "normalize_list": "{where}: normalize must be a list of {{pattern, replace}}",
        "normalize_item": "{where}: write it as {{pattern, replace}}",
        "bad_regex": "{where}: invalid regular expression: {error}",
        "yaml_hint": (
            "\nHint: a ': ' (colon and space) in the middle of a value is read as a separator. "
            'Quote the whole value (e.g. description: "setup: explanation")'
        ),
        "yaml_error": "{where}: cannot read as YAML: {error}{hint}",
        "top_mapping": "{where}: the top level must be a mapping with title, cases, etc.",
        "states_mapping": "{where}: states must be a mapping of state name -> contents",
        "no_cases": "{where}: there are no cases in cases",
        "duplicate_names": "{where}: duplicate case names: {names}",
        "duplicate_names_case": (
            "{where}: case names differ only in letter case "
            "(on Windows their golden files are the same file): {names}"
        ),
        "reason_string": (
            "{where}: write the reason for {key} as a string "
            "(e.g. {key}: waiting for the fix of #12)"
        ),
        "reserved_name": (
            "{where}: the case name {name} is used by the check for leftover golden files; "
            "rename the case (or set check_orphans: false)"
        ),
        "items_list": "{where}: must be a list of cases or groups",
        "item_mapping": "{where}: each case or group must be a mapping",
        "params_list": "{where}: params must be a list of one or more mappings laid over the case",
        "params_name": "{where}: every params element needs a name (appended to the case name)",
        "params_nested": "{where}: params cannot be nested inside params",
        "bad_name": (
            "{where}: name can only contain letters (any language), digits, _, - and ., "
            "and must not start with . or -: {name}"
        ),
        "one_action": "{where}: write exactly one of command, call, request and manual",
        "manual_keys": "{where}: manual cases cannot have {keys}",
        "manual_expect": "{where}: expect of a manual case must be a string or a list of strings",
        "result_only_manual": "{where}: result can only be used in manual cases",
        "result_value": "{where}: result must be one of {values}",
        "empty_command": "{where}: command is empty (and there is no command_prefix)",
        "bad_shell": "{where}: cannot split {key} into arguments ({error})",
        "not_utf8": "{where}: cannot read as UTF-8 ({error})",
        "bad_call": "{where}: call must be 'module:function': {call}",
        "args_only_call": "{where}: args / kwargs can only be used in call cases",
        "stdin_only_command": "{where}: stdin can only be used in command cases",
        "stdin_file_only_command": "{where}: stdin_file can only be used in command cases",
        "stdin_and_file": "{where}: stdin and stdin_file cannot be used together",
        "stdin_file_path": (
            "{where}: stdin_file must be a relative path inside the YAML's directory: {name}"
        ),
        "env_only_command": "{where}: env can only be used in command cases",
        "env_mapping": (
            "{where}: env must be a mapping of variable name -> value "
            "(a string or a number; null removes an outer value)"
        ),
        "args_list": "{where}: args must be a list",
        "kwargs_mapping": "{where}: kwargs must be a mapping of argument name -> value",
        "timeout_number": "{where}: timeout must be a positive number of seconds",
        "state_without_states": "{where}: state: {state} is set, but there are no states",
        "unknown_state": "{where}: {state} is not in states",
        "meta_mapping": "{where}: meta must be a mapping of key -> value",
        "setup_mapping": "{where}: setup must be a mapping",
        "setup_files": "{where}: setup.files must be a mapping of file name -> contents (string)",
        "setup_file_path": (
            "{where}: setup.files file names must be relative to the working directory: {name}"
        ),
        "golden_path": "{where}: golden must be relative to the golden directory: {name}",
        "expect_regex": "{where}: invalid regular expression in expect.{key}: {error}",
        "expect_text": (
            "{where}: expect.{key} must be a string, {{contains: ...}} or {{regex: ...}}"
        ),
        "expect_mapping": (
            "{where}: expect must be a mapping of item -> expected value with at least one item"
        ),
        "expect_kind": "{where}: expect.{key} can only be used in {kinds} cases",
        "return_and_raises": "{where}: write either return or raises in expect, not both",
        "observe_not_in_expect": (
            "{where}: {targets} in observe: are not in expect:. In a case with expect:, "
            "write the values to check in expect: (then observe: is not needed)"
        ),
        "exit_code_int": "{where}: expect.exit_code must be an integer",
        "status_int": "{where}: expect.status must be an integer",
        "headers_mapping": "{where}: expect.headers must be a mapping of header name -> value",
        "name_value_mapping": "{where}: {key} must be a mapping of name -> value",
        "request_defaults_mapping": "{where}: request_defaults must be a mapping",
        "request_form": "{where}: request must be 'METHOD PATH' (e.g. 'POST /users')",
        "request_type": "{where}: request must be a string or a mapping",
        "request_method": "{where}: request.method is not an HTTP method: {method}",
        "request_path": "{where}: request.path must start with /: {path}",
        "query_mapping": "{where}: request.query must be a mapping of name -> value",
        "json_and_body": "{where}: write either json or body in request, not both",
        "unknown_matcher": "{where}: unknown matcher: {name} (available: {known})",
        "matcher_string": "{where}: {name} needs a string",
        "matcher_list": "{where}: {name} needs a list",
        "command_not_found": "command not found: {program}",
        "command_start_failed": "cannot start the command: {program} ({error})",
        "stdin_file_missing": "stdin_file not found: {name}",
        "command_timeout": "did not finish within {timeout} seconds: {argv}",
        "call_timeout": (
            "call: {call} did not finish within {timeout} seconds "
            "(the function cannot be stopped and keeps running in the background)"
        ),
        "request_timeout": (
            "request: {request} did not finish within {timeout} seconds "
            "(the pytest_casebook_request hook cannot be stopped and keeps running in the "
            "background)"
        ),
        "import_failed": "call: cannot import module {module}: {error}",
        "attr_missing": "call: {spec} not found (no {attr})",
        "not_callable": "call: {spec} is not callable",
        "no_request_hook": (
            "request: cannot be sent (write a pytest_casebook_request hook in conftest.py)"
        ),
        "bad_response": (
            "the pytest_casebook_request hook must return an HttpResponse (returned: {type})"
        ),
        "observe_failed": (
            "observe: cannot fetch {target} "
            "(there is no pytest_casebook_observe hook, or it returned None)"
        ),
        "did_you_mean": ". Did you mean {key} in expect?",
        "manual_not_runnable": "a manual case cannot be run: {name}",
    },
}

# 今の言語。YAML を読むときと、ケースを実行するときに決める（language() で囲む）。
# メッセージを作る関数は奥深くにあるので、言語を引数で渡さずにここから読む
_LANG: ContextVar[str] = ContextVar("casebook_lang", default="en")


@contextlib.contextmanager
def language(lang: str) -> Iterator[None]:
    """この中で作る error() のメッセージを、lang の言語にする。"""
    token = _LANG.set(lang)
    try:
        yield
    finally:
        _LANG.reset(token)


def error(key: str, /, **values: Any) -> str:
    """今の言語で、YAML の誤り・実行の誤りのメッセージを作る。"""
    return ERRORS[_LANG.get()][key].format(**values)
