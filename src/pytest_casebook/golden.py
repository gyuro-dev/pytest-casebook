"""
期待出力（ゴールデンファイル）の形式と比較。

`--casebook-update` で作る期待出力は、次の形になる。

```text
# case: add_cli
# command: python -m calc add 1 2
# exit_code: 0
----- stdout -----
3
```

比べるのは結果だけ（`# exit_code:`・`# status:` と、`----- 見出し -----` 以下の本文）。
`# case:` や `# command:` などの行は、読む人のための説明で、比べない。
そのため、手で書くときはこれらの行を省ける。

- `# exit_code:`（request なら `# status:`）を書かなければ、終了コードは比べない
- 見出しのない本文は、command なら stdout、call なら return、request なら json として扱う
  （出力が1つだけなら、期待出力ファイルに本文だけを書けばよい）
- 書いていない見出しは、空であることを期待する（stderr を書かなければ stderr は空）
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .messages import MESSAGES
from .model import Case

# 比べない（説明のための）ヘッダー。description は render では書かないが、手で書いた期待出力に
# あれば読み飛ばす
INFO_KEYS = frozenset(
    {"case", "description", "command", "call", "args", "kwargs", "request", "state"}
)
# 比べるヘッダー
RESULT_KEYS = frozenset({"exit_code", "status"})

_HEADER_RE = re.compile(r"^# ([a-z_]+): ?(.*)$")
_SECTION_RE = re.compile(r"^----- (.+) -----$")


@dataclass
class GoldenContent:
    """期待出力のうち、比べる部分。"""

    # 比べるヘッダー（exit_code / status -> 値）
    results: dict[str, str] = field(default_factory=dict)
    # 見出し（stdout・return・observe: db.users など）-> 本文
    sections: dict[str, str] = field(default_factory=dict)


def render(case: Case, header: list[tuple[str, str]], sections: list[tuple[str, str]]) -> str:
    """
    ケースの結果を期待出力の形式の文字列にする（`--casebook-update` で書く内容）。

    :param case: ケース
    :param header: `# キー: 値` として並べる行
    :param sections: `----- 見出し -----` に続けて並べる本文
    :return: 期待出力の形式の文字列（末尾は改行1つ）
    """
    lines = [f"# case: {case.name}"]
    lines += [f"# {key}: {value}" for key, value in header]
    for title, body in sections:
        lines += [f"----- {title} -----", body]
    return "\n".join(lines).rstrip() + "\n"


def parse_golden(text: str, default_section: str) -> GoldenContent:
    """
    期待出力の文字列から、比べる部分を取り出す。

    :param text: 期待出力の文字列
    :param default_section: 見出しのない本文を何として扱うか（`stdout`・`return`・`json`）
    :return: 比べる部分
    """
    lines = text.replace("\r\n", "\n").split("\n")
    content = GoldenContent()
    # 先頭の `# キー: 値` のヘッダーを読み、その次の行から本文を読む
    start = 0
    while start < len(lines):
        match = _HEADER_RE.match(lines[start])
        if not match or match.group(1) not in INFO_KEYS | RESULT_KEYS:
            break
        if match.group(1) in RESULT_KEYS:
            content.results[match.group(1)] = match.group(2).strip()
        start += 1

    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        section_text = "\n".join(body).rstrip("\n")
        # 既定の見出しが空（----- stdout ----- だけ）なら、書いていないのと同じなので記録しない
        # （同じ見出しが2回あれば、後のほうを使う）
        if title is not None and (
            title != default_section or section_text or title in content.sections
        ):
            content.sections[title] = section_text
        # 見出しより前の空行だけの部分は、本文として扱わない
        elif title is None and section_text.strip():
            content.sections[default_section] = section_text

    for line in lines[start:]:
        match = _SECTION_RE.match(line)
        if match:
            flush()
            title, body = match.group(1), []
        else:
            body.append(line)
    flush()
    return content


def golden_differs(expected: GoldenContent, actual: GoldenContent) -> bool:
    """比べる部分が違えば True。書いていない見出しは空として比べる。"""
    for key, value in expected.results.items():
        if actual.results.get(key) != value:
            return True
    titles = set(expected.sections) | set(actual.sections)
    return any(expected.sections.get(t, "") != actual.sections.get(t, "") for t in titles)


def comparable_text(content: GoldenContent, expected: GoldenContent, actual: GoldenContent) -> str:
    """
    差分を見せるための、比べる部分だけを並べた文字列。

    期待出力に書いた結果のヘッダーと、どちらかにある見出しを、実際の出力の順に並べる。
    期待と実際の両方を同じ並びにするため、`content` を変えて2回呼ぶ。

    :param content: 文字列にする側（expected か actual）
    :param expected: 並べる結果のヘッダーを決める側
    :param actual: 見出しの順を決める側
    """
    lines = [f"# {key}: {content.results.get(key, '')}" for key in expected.results]
    titles = [*actual.sections, *(t for t in expected.sections if t not in actual.sections)]
    for title in titles:
        lines += [f"----- {title} -----", content.sections.get(title, "")]
    return "\n".join(lines).rstrip() + "\n"


def read_golden(path: Path) -> str:
    """期待出力を読む（git の設定などで CRLF になっていても LF にそろえる）。"""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def write_golden(path: Path, text: str) -> bool:
    """
    期待出力を書く。内容が変わらないときは書かない。

    :return: 書いたら True
    """
    if path.exists() and read_golden(path) == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def unified_diff(expected: str, actual: str, label: str, lang: str = "en") -> str:
    """期待出力と実際の出力の unified diff（label は差分の見出しに出す期待出力のパス）。"""
    m = MESSAGES[lang]
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=m["diff_expected"].format(label=label),
            tofile=m["golden_actual"],
        )
    )
