"""
ケースの結果を、グループの階層（大項目・中項目・小項目…）の表にした HTML レポート。

ケースファイルごとに、

- 大項目ごとの件数（成功・失敗など）の集計
- 失敗したケースの一覧（表の行へのリンク）
- 階層の列を縦に結合した表（ケース名・実行内容・確認内容・前提条件・期待結果・結果・時間）

を1つの HTML ファイルに出力する（外部のファイルを読まない）。
"""

from __future__ import annotations

import datetime
import html
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from .messages import TEXTS

# 結果の種類 -> 優先度。
# 1件のケースで複数の段階（setup / call / teardown）の結果があるときは、優先度の高いほうを使う。
# notrun は、集めたが実行していないケース（--collect-only や、-x で途中で止まったとき）
OUTCOMES: dict[str, int] = {
    "notrun": -1,
    "passed": 0,
    "updated": 1,
    "skipped": 2,
    "xfailed": 3,
    "xpassed": 4,
    "failed": 5,
    "error": 6,
}
_PROBLEMS = {"failed", "error", "xpassed"}


@dataclass
class CaseRow:
    """表の1行（1件のケース）。"""

    meta: dict[str, Any]
    outcome: str = "notrun"
    duration: float = 0.0
    details: list[str] = field(default_factory=list)
    # スキップや想定どおりの失敗の理由（結果の下に出す）
    note: str = ""

    def update(self, outcome: str) -> None:
        """段階ごとの結果を受け取り、優先度の高いほうを残す。"""
        if OUTCOMES[outcome] > OUTCOMES[self.outcome]:
            self.outcome = outcome


def _outcome_of(report: pytest.TestReport) -> str:
    """pytest の段階ごとの報告を、表に出す結果の種類（passed・xfailed など）にする。"""
    xfail = hasattr(report, "wasxfail")
    if report.when == "call":
        if xfail:
            return "xfailed" if report.skipped else "xpassed"
        return report.outcome
    if report.failed:
        return "error"
    if report.skipped:
        return "xfailed" if xfail else "skipped"
    return "passed"


class CasebookHtmlReport:
    """`--casebook-html` を付けたときに登録する pytest プラグイン。"""

    def __init__(self, path: Path, title: str, lang: str = "en") -> None:
        self.path = path
        self.title = title
        self.lang = lang
        self.rows: dict[str, CaseRow] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """集めたケースを、まず「未実施」の行として入れる（実行したものは結果で上書きする）。"""
        for item in session.items:
            meta = dict(item.user_properties).get("casebook")
            if isinstance(meta, dict):
                self.rows.setdefault(item.nodeid, CaseRow(meta=meta))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        props = dict(report.user_properties)
        meta = props.get("casebook")
        if not isinstance(meta, dict):
            return
        row = self.rows.setdefault(report.nodeid, CaseRow(meta=meta))
        # 時間はケースの実行（call）だけを数える。setup には session の fixture（環境を作る
        # 時間など）が入り、最初のケースだけが遅く見えてしまうため
        if report.when == "call":
            row.duration += report.duration
        outcome = _outcome_of(report)
        if outcome == "passed" and props.get("casebook_updated"):
            outcome = "updated"
        row.update(outcome)
        if hasattr(report, "wasxfail"):
            row.note = report.wasxfail
        # skip の longrepr は (ファイル, 行, "Skipped: 理由") のタプル。理由だけを出す
        elif report.skipped and isinstance(report.longrepr, tuple):
            row.note = str(report.longrepr[2]).removeprefix("Skipped: ")
        elif report.failed and report.longreprtext:
            row.details.append(report.longreprtext)

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        if not self.rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            build_html(self.title, list(self.rows.values()), datetime.datetime.now(), self.lang),
            encoding="utf-8",
        )

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        if self.rows:
            terminalreporter.write_sep("-", TEXTS[self.lang]["written"].format(path=self.path))


# =============================================================================
# HTML の組み立て
# =============================================================================


def _e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _badge(texts: dict[str, Any], outcome: str, count: int | None = None) -> str:
    label = texts["outcomes"][outcome]
    text = f"{label} {count}" if count is not None else label
    return f'<span class="badge {outcome}">{_e(text)}</span>'


def _counts(texts: dict[str, Any], rows: list[CaseRow]) -> str:
    counts = Counter(r.outcome for r in rows)
    return " ".join(_badge(texts, o, counts[o]) for o in OUTCOMES if counts[o])


def _row_id(row: CaseRow) -> str:
    return f"case-{row.meta['order']}"


def _summary_table(texts: dict[str, Any], rows: list[CaseRow], top_label: str) -> str:
    """大項目ごとの件数の表。"""
    groups: dict[str, list[CaseRow]] = {}
    for row in rows:
        name = row.meta["path"][0] if row.meta["path"] else texts["ungrouped"]
        groups.setdefault(name, []).append(row)
    body = "".join(
        f"<tr><td>{_e(name)}</td><td class='num'>{len(items)}</td>"
        f"<td>{_counts(texts, items)}</td></tr>"
        for name, items in groups.items()
    )
    return (
        f"<table class='summary'><thead><tr><th>{_e(top_label)}</th><th>{_e(texts['count'])}</th>"
        f"<th>{_e(texts['result'])}</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _problem_list(texts: dict[str, Any], rows: list[CaseRow]) -> str:
    problems = [r for r in rows if r.outcome in _PROBLEMS]
    if not problems:
        return ""
    items = "".join(
        f"<li>{_badge(texts, r.outcome)} <a href='#{_row_id(r)}'>"
        f"{_e(' > '.join([*r.meta['path'], r.meta['name']]))}</a></li>"
        for r in problems
    )
    return f"<div class='problems'><h3>{_e(texts['problems'])}</h3><ul>{items}</ul></div>"


def _height(row: CaseRow) -> int:
    """1件のケースが表で使う行数（失敗の詳細があれば、その下にもう1行使う）。"""
    return 2 if row.details else 1


def _level_spans(rows: list[CaseRow], depth: int) -> list[list[int | None]]:
    """
    各ケース・各階層のセルの rowspan を求める。

    同じグループ（外側の階層まで同じ）が続くケースはセルを縦に結合する。
    結合されて表示しないセルは None にする。グループのない階層は空セルにし、
    rowspan は負の数（-行数）で表す。rowspan には失敗の詳細の行も数える。
    """
    spans: list[list[int | None]] = [[-_height(row)] * depth for row in rows]
    for level in range(depth):
        start = 0
        while start < len(rows):
            path = rows[start].meta["path"]
            if len(path) <= level:
                start += 1
                continue
            key = path[: level + 1]
            end = start + 1
            while end < len(rows) and rows[end].meta["path"][: level + 1] == key:
                end += 1
            spans[start][level] = sum(_height(r) for r in rows[start:end])
            for i in range(start + 1, end):
                spans[i][level] = None
            start = end
    return spans


def _case_table(texts: dict[str, Any], rows: list[CaseRow], labels: list[str]) -> str:
    """ケースの表（階層の列を縦に結合し、失敗の詳細は次の行に出す）。"""
    depth = len(labels)
    spans = _level_spans(rows, depth)
    # 階層の列のあとに並ぶ列（失敗の詳細の行は、この列すべてにまたがる）
    columns = texts["columns"]
    head = "".join(f"<th class='level'>{_e(label)}</th>" for label in labels)
    head += "".join(f"<th>{_e(name)}</th>" for name in columns)
    lines: list[str] = []
    for row, row_spans in zip(rows, spans, strict=True):
        meta = row.meta
        cells: list[str] = []
        for level, span in enumerate(row_spans):
            if span is None:
                continue
            if span < 0:
                cells.append(f"<td class='level empty' rowspan='{-span}'></td>")
                continue
            desc = meta["path_descriptions"][level]
            desc_html = f"<div class='muted'>{_e(desc)}</div>" if desc else ""
            cells.append(
                f"<td class='level' rowspan='{span}'>"
                f"<div class='group'>{_e(meta['path'][level])}</div>{desc_html}</td>"
            )
        cells.append(
            f"<td class='case'><div class='name'>{_e(meta['name'])}</div>"
            f"<code class='run'>{_e(meta['run'])}</code></td>"
        )
        cells.append(f"<td class='desc'>{_e(meta['description'])}</td>")
        cells.append(f"<td class='cond'>{_list(meta['precondition'])}</td>")
        cells.append(f"<td class='cond'>{_list(meta['expected'])}</td>")
        note = f"<div class='muted note'>{_e(row.note)}</div>" if row.note else ""
        cells.append(f"<td class='result'>{_badge(texts, row.outcome)}{note}</td>")
        duration = "—" if row.outcome == "notrun" else f"{row.duration * 1000:.0f} ms"
        cells.append(f"<td class='num'>{duration}</td>")
        lines.append(f"<tr id='{_row_id(row)}' class='{row.outcome}'>{''.join(cells)}</tr>")
        if row.details:
            # 詳細は表の幅いっぱいの行に出す（差分の長い行で列の幅が広がらないように）
            details = "".join(
                f"<details><summary>{_e(texts['details'])}</summary>"
                f"<pre>{_colorize(text)}</pre></details>"
                for text in row.details
            )
            lines.append(
                f"<tr class='detail {row.outcome}'><td colspan='{len(columns)}'>{details}</td></tr>"
            )
    return (
        "<div class='scroll'><table class='cases'><thead><tr>"
        f"{head}</tr></thead><tbody>{''.join(lines)}</tbody></table></div>"
    )


def _colorize(text: str) -> str:
    """失敗の詳細の差分の行に色を付ける（+ は実際の出力、- は期待、@@ は場所）。"""
    out: list[str] = []
    for line in text.split("\n"):
        escaped = _e(line)
        # expect: の失敗では、差分の行が4つの空白で字下げされている
        # （「  - 項目: …」の箇条書きは2つの空白なので、差分の行とは区別できる）
        body = line.removeprefix("    ")
        if body.startswith(("+++", "---")):
            out.append(f"<span class='diff-file'>{escaped}</span>")
        elif body.startswith("+"):
            out.append(f"<span class='diff-add'>{escaped}</span>")
        elif body.startswith("-"):
            out.append(f"<span class='diff-del'>{escaped}</span>")
        elif body.startswith("@@"):
            out.append(f"<span class='diff-hunk'>{escaped}</span>")
        else:
            out.append(escaped)
    return "\n".join(out)


def _list(lines: list[str]) -> str:
    """前提条件・期待結果の行を並べる（なければ「—」）。"""
    if not lines:
        return "<span class='muted'>—</span>"
    return "".join(f"<div class='line'>{_e(line)}</div>" for line in lines)


def _file_section(texts: dict[str, Any], rows: list[CaseRow]) -> str:
    """1つのケースファイルの節（見出し・件数・大項目ごとの集計・確認が必要なケース・表）。"""
    first = rows[0].meta
    # 階層の列は、実際に使われているグループの深さだけ出す（levels に書いた数ではない）。
    # 大項目しかないファイルに、空の中項目・小項目の列が出ないようにする
    depth = max(len(r.meta["path"]) for r in rows)
    labels = [
        first["levels"][i] if i < len(first["levels"]) else texts["level_n"].format(n=i + 1)
        for i in range(depth)
    ]
    desc = f"<p>{_e(first['file_description'])}</p>" if first["file_description"] else ""
    golden = f"<div class='muted'>{_e(texts['golden_dir'].format(dir=first['golden_dir']))}</div>"
    return (
        f"<section><h2>{_e(first['title'])} <span class='file'>{_e(first['file'])}</span></h2>"
        f"{desc}{golden}"
        f"<div class='counts'>{_e(texts['cases'].format(n=len(rows)))} {_counts(texts, rows)}</div>"
        f"{_summary_table(texts, rows, labels[0] if labels else texts['group'])}"
        f"{_problem_list(texts, rows)}{_case_table(texts, rows, labels)}</section>"
    )


def build_html(
    title: str, rows: list[CaseRow], generated_at: datetime.datetime, lang: str = "en"
) -> str:
    """結果の行から HTML 全体を組み立てる。"""
    texts = TEXTS[lang]
    rows = sorted(rows, key=lambda r: r.meta["order"])
    files: dict[str, list[CaseRow]] = {}
    for row in rows:
        files.setdefault(row.meta["file"], []).append(row)
    sections = "".join(_file_section(texts, items) for items in files.values())
    generated = texts["generated"].format(at=generated_at.strftime("%Y-%m-%d %H:%M:%S"))
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
<h1>{_e(title)}</h1>
<div class="muted">{_e(generated)}</div>
<div class="counts">{_e(texts["total"].format(n=len(rows)))} {_counts(texts, rows)}</div>
</header>
<main>{sections}</main>
</body>
</html>
"""


_CSS = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --line: #d0d7de; --head: #f6f8fa;
  --group: #f6f8fa; --code: #eff1f3;
  --ok: #1a7f37; --ok-bg: #dafbe1; --ng: #cf222e; --ng-bg: #ffebe9;
  --warn: #9a6700; --warn-bg: #fff8c5; --info: #0969da; --info-bg: #ddf4ff;
  --skip: #57606a; --skip-bg: #eaeef2;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0; --line: #30363d; --head: #161b22;
    --group: #161b22; --code: #1f242c;
    --ok: #3fb950; --ok-bg: #12261e; --ng: #f85149; --ng-bg: #2d1416;
    --warn: #d29922; --warn-bg: #2b2111; --info: #58a6ff; --info-bg: #121d2f;
    --skip: #8d96a0; --skip-bg: #21262d;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0; --line: #30363d; --head: #161b22;
  --group: #161b22; --code: #1f242c;
  --ok: #3fb950; --ok-bg: #12261e; --ng: #f85149; --ng-bg: #2d1416;
  --warn: #d29922; --warn-bg: #2b2111; --info: #58a6ff; --info-bg: #121d2f;
  --skip: #8d96a0; --skip-bg: #21262d;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
  font: 14px/1.6 system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Meiryo", sans-serif;
}
header, main { max-width: 1280px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 {
  font-size: 18px; margin: 32px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--line);
}
h3 { font-size: 14px; margin: 16px 0 6px; }
.muted, .file { color: var(--muted); font-size: 12px; font-weight: normal; }
.counts { margin: 8px 0; }
.badge {
  display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
  font-weight: 600; white-space: nowrap;
}
.badge.notrun { color: var(--muted); border: 1px dashed var(--line); }
.badge.passed { color: var(--ok); background: var(--ok-bg); }
.badge.updated { color: var(--info); background: var(--info-bg); }
.badge.skipped, .badge.xfailed { color: var(--skip); background: var(--skip-bg); }
.badge.xpassed { color: var(--warn); background: var(--warn-bg); }
.badge.failed, .badge.error { color: var(--ng); background: var(--ng-bg); }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid var(--line); padding: 6px 8px; vertical-align: top; text-align: left; }
th { background: var(--head); font-size: 12px; white-space: nowrap; }
table.summary { width: auto; min-width: 360px; margin-bottom: 8px; }
.num { text-align: right; white-space: nowrap; }
.scroll { overflow-x: auto; }
td.level { background: var(--group); min-width: 96px; }
td.level .group { font-weight: 600; }
td.level.empty { background: var(--bg); }
td.case { min-width: 170px; }
td.case .name { font-weight: 600; overflow-wrap: anywhere; }
code.run {
  display: block; margin-top: 2px; padding: 1px 4px; background: var(--code); border-radius: 4px;
  font: 12px/1.5 ui-monospace, "Cascadia Code", Consolas, monospace; word-break: break-all;
}
td.cond { min-width: 160px; font-size: 12px; }
td.result .note { margin-top: 4px; font-size: 12px; max-width: 200px; }
td.cond .line { word-break: break-all; }
td.cond .line + .line { margin-top: 2px; }
td.desc { min-width: 200px; }
tr.failed td.case, tr.error td.case { box-shadow: inset 3px 0 0 var(--ng); }
tr:target td { outline: 2px solid var(--info); outline-offset: -2px; }
tr.detail td { padding: 4px 8px 8px; border-top: none; }
tr.failed:not(.detail) td:not(.level), tr.error:not(.detail) td:not(.level) { border-bottom: none; }
details summary { cursor: pointer; color: var(--muted); font-size: 12px; }
tr.detail.failed summary, tr.detail.error summary { color: var(--ng); font-weight: 600; }
pre {
  margin: 6px 0 0; padding: 8px; max-height: 480px; overflow: auto; background: var(--code);
  border-radius: 4px; font: 12px/1.5 ui-monospace, "Cascadia Code", Consolas, monospace;
  white-space: pre-wrap; overflow-wrap: anywhere;
}
pre .diff-add { color: var(--ok); background: var(--ok-bg); display: inline-block; width: 100%; }
pre .diff-del { color: var(--ng); background: var(--ng-bg); display: inline-block; width: 100%; }
pre .diff-hunk { color: var(--info); }
pre .diff-file { color: var(--muted); }
.problems { margin: 8px 0 12px; }
.problems ul { margin: 0; padding-left: 20px; }
a { color: var(--info); }
"""
