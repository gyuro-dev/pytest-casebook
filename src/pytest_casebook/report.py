"""
ケースの結果を、グループの階層（大項目・中項目・小項目…）の表にした HTML レポート。

ケースファイルごとに、

- 大項目ごとの件数（成功・失敗など）の集計
- 失敗したケースの一覧（表の行へのリンク）
- 階層の列を縦に結合した表（ケース名・実行内容・確認内容・前提条件・期待結果・結果・時間）

を1つの HTML ファイルに出力する（外部のファイルを読まない）。
ページの上部には、結果と文字で表を絞り込む欄を出す（埋め込みの JavaScript で動かし、
JavaScript が動かなければ表の全体を出す）。
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
# notrun は、集めたが実行していないケース（--collect-only や、-x で途中で止まったとき）。
# manual は、手動のケースで、手で確かめた結果（result:）がまだ書かれていないもの
OUTCOMES: dict[str, int] = {
    "notrun": -1,
    "passed": 0,
    "updated": 1,
    "manual": 2,
    "skipped": 3,
    "xfailed": 4,
    "xpassed": 5,
    "failed": 6,
    "error": 7,
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


@dataclass
class ReportOutput:
    """
    出す HTML の 1 つ（`--casebook-html` の全体の表か、ini の casebook_html_reports の 1 行）。

    `files` は入れるケースファイル（rootdir からの相対パス。None なら全部）。
    枠・見出しの言語は、入ったケースのファイルの言語がそろっていればそれ、混ざっていれば
    ini の casebook_lang。`title` は ini の casebook_html_title（なければ言語の既定）。
    """

    path: Path
    files: frozenset[str] | None = None
    title: str | None = None
    # 書いたときに決まる（書かなかったときは None）
    lang: str | None = None

    def select(self, rows: list[CaseRow]) -> list[CaseRow]:
        if self.files is None:
            return rows
        return [row for row in rows if row.meta["file"] in self.files]


class CasebookHtmlReport:
    """`--casebook-html` か ini の casebook_html_reports があるときに登録する pytest プラグイン。"""

    def __init__(self, outputs: list[ReportOutput], lang: str = "en") -> None:
        self.outputs = outputs
        # ini の言語（ファイルの言語が混ざった表の枠と、書かなかった表の知らせに使う）
        self.lang = lang
        self.rows: dict[str, CaseRow] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """
        集めたケースを、まず「未実施」の行として入れる（実行したものは結果で上書きする）。

        手動のケースで result: がまだないものは、実行しても「手動」のままなので、
        `--collect-only` の計画の表でも「未実施」ではなく「手動」と出す。
        """
        for item in session.items:
            meta = dict(item.user_properties).get("casebook")
            if isinstance(meta, dict):
                outcome = "manual" if meta.get("manual_pending") else "notrun"
                self.rows.setdefault(item.nodeid, CaseRow(meta=meta, outcome=outcome))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        props = dict(report.user_properties)
        meta = props.get("casebook")
        outcome = _outcome_of(report)
        # pytest-rerunfailures の "rerun" のような、ほかのプラグインの結果は数えない
        # （やり直したときは、最後の試行の結果が表に出る）
        if not isinstance(meta, dict) or outcome not in OUTCOMES:
            return
        row = self.rows.setdefault(report.nodeid, CaseRow(meta=meta))
        # 情報は新しい報告のものにする。--casebook-update で書いた期待出力の内容は call のあとに
        # 入るので、setup の報告のまま（pytest-xdist では段階ごとに別の複製が届く）にしない
        row.meta = meta
        # 時間はケースの実行（call）だけを数える。setup には session の fixture（環境を作る
        # 時間など）が入り、最初のケースだけが遅く見えてしまうため
        if report.when == "call":
            row.duration += report.duration
        if outcome == "passed" and props.get("casebook_updated"):
            outcome = "updated"
        if outcome == "skipped" and props.get("casebook_manual"):
            outcome = "manual"
        row.update(outcome)
        if hasattr(report, "wasxfail"):
            row.note = report.wasxfail
        # skip の longrepr は (ファイル, 行, "Skipped: 理由") のタプル。理由だけを出す
        # （手動のケースは「手動」のバッジで分かるので、理由は出さない）
        elif outcome == "skipped" and isinstance(report.longrepr, tuple):
            row.note = str(report.longrepr[2]).removeprefix("Skipped: ")
        elif report.failed and report.longreprtext:
            row.details.append(report.longreprtext)

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        now = datetime.datetime.now()
        for output in self.outputs:
            rows = output.select(list(self.rows.values()))
            # 入るケースのない表は書かない（空の表を出さない。知らせは実行の最後に出す）
            if not rows:
                continue
            langs = {row.meta.get("lang", self.lang) for row in rows}
            output.lang = next(iter(langs)) if len(langs) == 1 else self.lang
            title = output.title or TEXTS[output.lang]["title"]
            output.path.parent.mkdir(parents=True, exist_ok=True)
            output.path.write_text(build_html(title, rows, now, output.lang), encoding="utf-8")

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        for output in self.outputs:
            if output.lang is not None:
                line = TEXTS[output.lang]["written"].format(path=output.path)
            else:
                line = TEXTS[self.lang]["not_written"].format(path=output.path)
            terminalreporter.write_sep("-", line)


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
    """1件のケースが表で使う行数（失敗の詳細か期待出力の内容があれば、その下にもう1行使う）。"""
    return 2 if row.details or row.meta.get("golden_text") else 1


def _level_spans(rows: list[CaseRow], depth: int) -> list[list[int | None]]:
    """
    各ケース・各階層のセルの rowspan を求める。

    同じグループ（外側の階層まで同じ）が続くケースはセルを縦に結合する。
    結合されて表示しないセルは None にする。グループのない階層は空セルにし、
    rowspan は負の数（-行数）で表す。rowspan には詳細（失敗の詳細・期待出力の内容）の行も数える。
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
    """ケースの表（階層の列を縦に結合し、失敗の詳細と期待出力の内容は次の行に出す）。"""
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
        if meta["kind"] == "manual":
            run = f"<div class='steps'>{_e(texts['manual_steps'].format(steps=meta['run']))}</div>"
        else:
            run = f"<code class='run'>{_e(meta['run'])}</code>"
        cells.append(f"<td class='case'><div class='name'>{_e(meta['name'])}</div>{run}</td>")
        cells.append(f"<td class='desc'>{_e(meta['description'])}</td>")
        cells.append(f"<td class='cond'>{_list(meta['precondition'])}</td>")
        golden_text = meta.get("golden_text") or ""
        golden_id = f"{_row_id(row)}-golden"
        cells.append(f"<td class='cond'>{_expected(texts, meta, golden_id)}</td>")
        note = f"<div class='muted note'>{_e(row.note)}</div>" if row.note else ""
        cells.append(f"<td class='result'>{_badge(texts, row.outcome)}{note}</td>")
        # 実行していないケース（未実施・手動）には時間を出さない
        not_run = row.outcome == "notrun" or meta["kind"] == "manual"
        duration = "—" if not_run else f"{row.duration * 1000:.0f} ms"
        cells.append(f"<td class='num'>{duration}</td>")
        # data-outcome と data-text は、ページ上部の絞り込み（_JS）が使う
        lines.append(
            f"<tr id='{_row_id(row)}' class='{row.outcome}' data-outcome='{row.outcome}'"
            f" data-text='{_e(_search_text(row))}'>{''.join(cells)}</tr>"
        )
        if row.details or golden_text:
            # 詳細は表の幅いっぱいの行に出す（差分の長い行で列の幅が広がらないように）
            details = "".join(
                f"<details><summary>{_e(texts['details'])}</summary>"
                f"<pre>{_colorize(text)}</pre></details>"
                for text in row.details
            )
            if golden_text:
                # 期待出力ファイルの比べる部分（失敗の詳細と同じ仕組みの、折りたたみの行）
                label = texts["golden_contents"].format(name=meta.get("golden_name", ""))
                details += (
                    f"<details class='golden' id='{golden_id}'><summary>{_e(label)}</summary>"
                    f"<pre>{_e(golden_text)}</pre></details>"
                )
            lines.append(
                f"<tr class='detail {row.outcome}'><td colspan='{len(columns)}'>{details}</td></tr>"
            )
    return (
        "<div class='scroll'><table class='cases'><thead><tr>"
        f"{head}</tr></thead><tbody>{''.join(lines)}</tbody></table></div>"
    )


def _search_text(row: CaseRow) -> str:
    """
    文字での絞り込みの対象にする、1件のケースの文字。

    グループの列は縦に結合していて、2件目以降の行にはセルがないので、
    グループの名前と説明もここに入れる。
    """
    meta = row.meta
    parts = [
        *meta["path"],
        *meta["path_descriptions"],
        meta["name"],
        meta["run"],
        meta["description"],
        *meta["precondition"],
        *meta["expected"],
        row.note,
    ]
    return "\n".join(str(part) for part in parts if part)


def _filter_bar(texts: dict[str, Any], rows: list[CaseRow]) -> str:
    """
    ページ上部の絞り込み（結果の切り替えと、文字の入力欄）。

    JavaScript が動くときだけ出す（hidden を外す）。JavaScript が動かなければ、
    今までどおり件数だけを出し、表は全部見える。期待出力の内容を出すケースがあれば、
    それをすべて開く・閉じるボタンも並べる（押すたびに開く・閉じるが入れ替わる）。
    """
    counts = Counter(r.outcome for r in rows)
    all_button = (
        '<button type="button" class="badge all" data-outcome="" aria-pressed="true">'
        f"{_e(texts['filter_all'])}</button>"
    )
    buttons = [all_button]
    buttons += [
        f'<button type="button" class="badge {o}" data-outcome="{o}" aria-pressed="false">'
        f"{_e(texts['outcomes'][o])} {counts[o]}</button>"
        for o in OUTCOMES
        if counts[o]
    ]
    golden_toggle = ""
    if any(r.meta.get("golden_text") for r in rows):
        golden_toggle = (
            '<button type="button" class="golden-toggle" aria-pressed="false"'
            f' data-open="{_e(texts["golden_open_all"])}"'
            f' data-close="{_e(texts["golden_close_all"])}">'
            f"{_e(texts['golden_open_all'])}</button>"
        )
    return (
        '<div class="filter" hidden>'
        f'<div class="toggles" role="group" aria-label="{_e(texts["result"])}">'
        f"{''.join(buttons)}</div>"
        f'<input type="search" aria-label="{_e(texts["filter"])}"'
        f' placeholder="{_e(texts["filter_placeholder"])}">'
        f"{golden_toggle}"
        f'<span class="shown muted" aria-live="polite"'
        f' data-template="{_e(texts["filter_shown"])}" data-none="{_e(texts["filter_none"])}">'
        "</span></div>"
    )


def _colorize(text: str) -> str:
    """
    失敗の詳細の差分の行に色を付ける（+ は実際の出力、- は期待、@@ は場所）。

    色を付けるのは unified diff の中だけ。差分は `--- ` / `+++ ` のファイルの見出しか
    `@@` の行で始まり、` `・`+`・`-`・`@@`・`\\` で始まる行が続くあいだを差分とみなす。
    それ以外の行で差分は終わる。差分の外（「----- actual stdout -----」の下の実際の出力など）の
    `- 項目` や `+10` の行には色を付けない。

    expect: の失敗では、差分の行が4つの空白で字下げされている（「  - 項目: …」の箇条書きは
    2つの空白なので、差分の行とは区別できる）。差分の始まりの字下げを覚えておき、
    続く行も同じ字下げのときだけ差分とみなす。
    """
    out: list[str] = []
    # 今の差分の字下げ（差分の外なら None）
    indent: str | None = None
    for line in text.split("\n"):
        escaped = _e(line)
        if indent is not None:
            body = line[len(indent) :] if line.startswith(indent) else None
            # 空の行は、行末の空白が消えた差分の空の行として、差分の続きとみなす
            if line and (body is None or not body.startswith((" ", "+", "-", "@@", "\\"))):
                indent = None
        if indent is None:
            for candidate in ("    ", ""):
                if line.startswith(candidate) and line[len(candidate) :].startswith(
                    ("--- ", "+++ ", "@@")
                ):
                    indent = candidate
                    break
        if indent is None:
            out.append(escaped)
            continue
        body = line[len(indent) :]
        if body.startswith(("+++ ", "--- ")):
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


def _expected(texts: dict[str, Any], meta: dict[str, Any], golden_id: str) -> str:
    """
    期待結果の列。

    期待出力の内容を下の行に出すケースでは、最初の行（「期待出力ファイル（…）」）を、
    その折りたたみを開くリンク（golden_see）にする（同じファイル名が2回並ばないように）。
    内容を出すのは期待出力ファイルと比べるケース（expect: がなく、手動でもない）だけで、
    その期待結果の最初の行は、いつも期待出力ファイルの行（plugin の _expected_lines）。
    内容を出さないとき（casebook_html_golden が off・ファイルがない）は、今までどおりの文字にする。
    """
    lines = list(meta["expected"])
    if not meta.get("golden_text") or not lines:
        return _list(lines)
    label = texts["golden_see"].format(name=meta.get("golden_name", ""))
    link = f"<div class='line'><a class='golden-link' href='#{golden_id}'>{_e(label)}</a></div>"
    rest = _list(lines[1:]) if lines[1:] else ""
    return link + rest


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
    # 期待出力の内容を出すファイルには、<…>（実行ごとに変わる値の置き換え）の注記を1回だけ出す
    if any(r.meta.get("golden_text") for r in rows):
        golden += f"<div class='muted'>{_e(texts['golden_note'])}</div>"
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
{_filter_bar(texts, rows)}
</header>
<main>{sections}</main>
<script>{_JS}</script>
</body>
</html>
"""


_CSS = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --line: #d0d7de; --head: #f6f8fa;
  --group: #f6f8fa; --code: #eff1f3;
  --ok: #1a7f37; --ok-bg: #dafbe1; --ng: #cf222e; --ng-bg: #ffebe9;
  --warn: #9a6700; --warn-bg: #fff8c5; --info: #0969da; --info-bg: #ddf4ff;
  --skip: #57606a; --skip-bg: #eaeef2; color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0; --line: #30363d; --head: #161b22;
    --group: #161b22; --code: #1f242c;
    --ok: #3fb950; --ok-bg: #12261e; --ng: #f85149; --ng-bg: #2d1416;
    --warn: #d29922; --warn-bg: #2b2111; --info: #58a6ff; --info-bg: #121d2f;
    --skip: #8d96a0; --skip-bg: #21262d; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0; --line: #30363d; --head: #161b22;
  --group: #161b22; --code: #1f242c;
  --ok: #3fb950; --ok-bg: #12261e; --ng: #f85149; --ng-bg: #2d1416;
  --warn: #d29922; --warn-bg: #2b2111; --info: #58a6ff; --info-bg: #121d2f;
  --skip: #8d96a0; --skip-bg: #21262d; color-scheme: dark;
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
.badge.manual { color: var(--info); border: 1px dashed var(--info); }
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
td.case .steps { margin-top: 2px; font-size: 12px; white-space: pre-line; overflow-wrap: anywhere; }
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
tr.detail details.golden summary { color: var(--muted); font-weight: normal; }
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
a.golden-link { font-size: 12px; }
[hidden] { display: none !important; }
.filter { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 8px 0; }
.filter .toggles { display: flex; flex-wrap: wrap; gap: 4px; }
.filter button.badge {
  font-family: inherit; line-height: 1.6; cursor: pointer; border: 1px solid transparent;
}
.filter button.badge.notrun { border: 1px dashed var(--line); }
.filter button.badge.manual { border: 1px dashed var(--info); }
.filter button.badge.all { color: var(--fg); background: var(--bg); border-color: var(--line); }
.filter button.badge.all[aria-pressed="true"] {
  color: var(--bg); background: var(--fg); border-color: var(--fg);
}
.filter button.badge[aria-pressed="true"]:not(.all) { border: 1px solid currentColor; }
.filter.active button.badge[aria-pressed="false"]:not(.all) { opacity: .4; }
.filter button.badge:focus-visible { outline: 2px solid var(--info); outline-offset: 1px; }
.filter input {
  flex: 1 1 240px; max-width: 420px; padding: 3px 8px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--bg); color: var(--fg); font: inherit; font-size: 13px;
}
.filter input:focus { outline: 2px solid var(--info); outline-offset: -1px; }
.filter button.golden-toggle {
  padding: 2px 10px; border: 1px solid var(--line); border-radius: 6px; cursor: pointer;
  background: var(--bg); color: var(--fg); font: inherit; font-size: 12px; white-space: nowrap;
}
.filter button.golden-toggle[aria-pressed="true"] { background: var(--head); }
.filter button.golden-toggle:focus-visible { outline: 2px solid var(--info); outline-offset: 1px; }
"""

# ページ上部の絞り込み。外部のファイルを読まず、HTML に埋め込む。
#
# 階層の列は rowspan で縦に結合しているので、行を display: none で隠すだけでは表が崩れる
# （結合したセルを持つ行を隠すと、そのセルごと消えて、下の行の列がずれる）。そこで、
# 1. 最初に、各ケースの行がどの階層のセルに覆われているかを、rowspan をたどって覚える
# 2. 絞り込むたびに、階層のセルをすべて外し、条件に合う行だけを tbody に並べ直す
# 3. 同じセルに覆われた行が続くところ（同じグループ）は、その最初の行にセルを戻し、
#    rowspan を見えている行の数（失敗の詳細の行も数える）にする
# 元のセルをそのまま使い回すので、絞り込みを外すと最初の表とまったく同じになる。
# 詳細の行（失敗の詳細・期待出力の内容）は、ケースの行と一緒に出し入れする。
#
# 期待出力をすべて開く・閉じるボタンは、最初に覚えておいた details.golden をまとめて
# 開け閉めする（絞り込みで表から外れている行の分も。表に戻したとき、ほかの行とそろう）。
# 1つずつ開け閉めしたときもボタンの表示を合わせる（toggle は親に伝わらないので、
# document で捕捉の段階に受ける）。
#
# 期待結果の列の「下の期待出力を見る」のリンク（a.golden-link）は、# のリンクなので
# JavaScript がなくても折りたたみの行まで飛ぶが、それだけでは閉じたまま。そこで押したときに
# 行き先の details を開く（open を変えるので toggle が起き、すべて開く・閉じるボタンの表示も
# 合う）。移動はブラウザに任せる（preventDefault しない）。この部分は絞り込みの欄がなくても動かす。
# 埋め込みの JavaScript とCSS にはコメントを書かない（英語のレポートに日本語が入らないように）。
_JS = r"""
(() => {
  document.addEventListener("click", (event) => {
    const link = event.target.closest && event.target.closest("a.golden-link");
    if (!link) return;
    const target = document.getElementById(link.hash.slice(1));
    if (target && target.tagName === "DETAILS") target.open = true;
  });
  const bar = document.querySelector("header .filter");
  if (!bar) return;
  const input = bar.querySelector("input");
  const toggles = bar.querySelector(".toggles");
  const buttons = Array.from(toggles.querySelectorAll("button"));
  const shown = bar.querySelector(".shown");
  const selected = new Set();
  const tables = Array.from(document.querySelectorAll("table.cases")).map((table) => {
    const depth = table.tHead.querySelectorAll("th.level").length;
    const body = table.tBodies[0];
    const cover = [];
    const cases = [];
    for (const tr of Array.from(body.rows)) {
      if (tr.classList.contains("detail")) {
        cases[cases.length - 1].detail = tr;
      } else {
        let next = 0;
        const cells = [];
        for (let level = 0; level < depth; level++) {
          if (!cover[level] || cover[level].left === 0) {
            const cell = tr.cells[next++];
            cover[level] = { cell, left: cell.rowSpan };
          }
          cells.push(cover[level].cell);
        }
        const text = (tr.dataset.text || "").toLowerCase();
        cases.push({ tr, detail: null, cells, outcome: tr.dataset.outcome, text });
      }
      cover.forEach((c) => c.left--);
    }
    const cells = new Set(cases.flatMap((c) => c.cells));
    return { section: table.closest("section"), body, cases, cells };
  });

  const apply = () => {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    const match = (c) =>
      (selected.size === 0 || selected.has(c.outcome)) && words.every((w) => c.text.includes(w));
    let count = 0;
    let total = 0;
    for (const t of tables) {
      t.cells.forEach((cell) => cell.remove());
      const rows = [];
      const last = [];
      const visible = t.cases.filter(match);
      for (const c of visible) {
        const height = c.detail ? 2 : 1;
        const starts = [];
        c.cells.forEach((cell, level) => {
          if (last[level] === cell) {
            cell.rowSpan += height;
          } else {
            last[level] = cell;
            cell.rowSpan = height;
            starts.push(cell);
          }
        });
        c.tr.prepend(...starts);
        rows.push(c.tr);
        if (c.detail) rows.push(c.detail);
      }
      t.body.replaceChildren(...rows);
      if (t.section) t.section.hidden = rows.length === 0;
      count += visible.length;
      total += t.cases.length;
    }
    shown.textContent =
      count === 0
        ? shown.dataset.none
        : shown.dataset.template.replace("{shown}", count).replace("{total}", total);
    bar.classList.toggle("active", selected.size > 0);
    for (const b of buttons) {
      const o = b.dataset.outcome;
      b.setAttribute("aria-pressed", String(o ? selected.has(o) : selected.size === 0));
    }
  };

  toggles.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const o = button.dataset.outcome;
    if (!o) selected.clear();
    else if (selected.has(o)) selected.delete(o);
    else selected.add(o);
    apply();
  });
  input.addEventListener("input", apply);

  const goldenToggle = bar.querySelector(".golden-toggle");
  if (goldenToggle) {
    const golden = Array.from(document.querySelectorAll("details.golden"));
    const sync = () => {
      const allOpen = golden.length > 0 && golden.every((d) => d.open);
      goldenToggle.setAttribute("aria-pressed", String(allOpen));
      goldenToggle.textContent = allOpen
        ? goldenToggle.dataset.close
        : goldenToggle.dataset.open;
    };
    goldenToggle.addEventListener("click", () => {
      const open = !golden.every((d) => d.open);
      golden.forEach((d) => (d.open = open));
      sync();
    });
    document.addEventListener("toggle", (event) => {
      if (event.target.matches && event.target.matches("details.golden")) sync();
    }, true);
  }
  document.querySelector("header > .counts").hidden = true;
  bar.hidden = false;
  apply();
})();
"""
