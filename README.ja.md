# pytest-casebook

[![PyPI](https://img.shields.io/pypi/v/pytest-casebook)](https://pypi.org/project/pytest-casebook/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-casebook)](https://pypi.org/project/pytest-casebook/)
[![CI](https://github.com/gyuro-dev/pytest-casebook/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gyuro-dev/pytest-casebook/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/pypi/l/pytest-casebook)](https://github.com/gyuro-dev/pytest-casebook/blob/main/LICENSE)

[English](README.md) | 日本語

YAML に書いたテストケースを pytest で実行し、結果を、大項目・中項目・小項目で整理した**試験項目表**（HTML）として出力する pytest プラグインです。\
試験項目表と自動テストを同じ YAML から作るので、Excel の表と自動テストを別々に直して内容がずれていく、ということがなくなります。

## できること

- **CLI を実行**して、終了コード・標準出力・標準エラーを確かめる
- **Python の関数を呼んで**、戻り値や例外を確かめる（async の関数も）
- **HTTP の API にリクエストを送って**、ステータス・JSON・ヘッダーを確かめる（FastAPI や Flask などのテスト用クライアントで送る。[書き方](#http-の-api-request)）
- **前提条件を用意する**: ファイルを置く、DB に行を入れる、「障害時」のような状態に切り替える（[書き方](#前提条件-setup)）
- **実行後の DB やファイルの中身**も確かめる（[書き方](#実行後の値-observe)）
- 期待結果は **YAML に直接書く**か、実際の出力から**期待出力ファイルを作って差分で比べる**（[書き方](#期待結果-expect)）
- 自動にできない**手動の確認**（画面を目で見る、帳票など）も同じ表に載せ、結果を手で書き込める（[書き方](#手動のケース-manual)）
- ケースを**大項目・中項目・小項目**（何階層でも）に分け、**試験項目表の HTML** を出す（日本語・英語。[書き方](#html-レポート)）

`pytest --casebook-html=report.html` を実行すると、YAML に書いたケースが、次のような試験項目表として出力されます。\
グループの階層の列は縦に結合され、前提条件・期待結果・結果が1行に並びます。\
期待出力ファイルの中身も、ケースの行の下に折りたたんで出ます（下の図では price_one.txt を開いています）。

![試験項目表の HTML レポート](docs/images/report-top.png)

**[デモのレポート（実物）](https://gyuro-dev.github.io/pytest-casebook/)** で、実際に操作できます。\
失敗した差分を開いたり、表を絞り込んだりしてみてください（画像では分からないところです）。

> **レポートを日本語にする**: HTML レポートとメッセージ（比較の失敗、YAML の書き方の誤りなど）の既定は英語です。\
> 日本語にするときは、`pyproject.toml` に一度だけ書きます（[ini の設定](#ini-の設定)）。
>
> ```toml
> [tool.pytest.ini_options]
> casebook_lang = "ja"
> ```

上の表は、次の YAML から作りました（抜粋。全体は [docs/screenshots/casebook_demo.yaml](docs/screenshots/casebook_demo.yaml)）。\
`group:` の入れ子が大項目・中項目・小項目の列に、`description` が確認内容の列に、`expect:` が期待結果の列になります。\
`expect:` のないケースは、期待出力ファイルと比べます。

```yaml
title: 小さなお店
levels: [大項目, 中項目, 小項目]
command_prefix: store

cases:
  - group: 価格計算
    description: 会員割引とまとめ買い割引
    cases:
      - group: 通常の購入
        cases:
          - group: CLI
            cases:
              - name: price_one
                description: 1個だけなら割引はない
                command: price りんご 1
          - group: 関数
            cases:
              - name: quote_bulk
                description: 5個以上で50円引きになる
                call: store:quote
                args: [バナナ, 5]
                expect:
                  return: {discount: 50, total: 450}
```

## 向いている場面

テストを Python で書けば、型の補完もデバッガも使えます。\
単体テストなら、`@pytest.mark.parametrize` とスナップショットテスト（syrupy など）で足ります。\
pytest-casebook は、次のような場面に向いています。

- テストの一覧を、エンジニア以外（QA・顧客・企画）にも見せたい。\
  試験項目表として提出したい
- ケースは QA を含む多くの人が YAML で増やし、DB の準備などの仕組み（conftest.py の hook）はエンジニアが一度だけ書く、という分担にしたい
- 「DB に行を入れる → API や CLI を動かす → レスポンスと DB の変化を確かめる」を、1つのケースとして書きたい
- 同じ YAML を、デモ用のスクリプトなど pytest の外でも使いたい（`pytest_casebook.load()`）

対応する Python は 3.11〜3.15、pytest は 8 と 9 です（GitHub Actions の CI と [scripts/check.sh](scripts/check.sh) で確かめています）。

## インストール

```bash
pip install pytest-casebook
# uv を使っているなら
uv add --dev pytest-casebook
```

インストールすると pytest が自動で読み込むので、設定は要りません。

Python 3.15 では、PyYAML に 3.15 用の wheel がまだないため、インストールのときに PyYAML がソースからビルドされます。\
C コンパイラのない Windows で失敗するときは、環境変数 `PYYAML_FORCE_LIBYAML=0` を付けて入れてください（C 拡張を使わない PyYAML になります）。

依存は pytest・PyYAML・pluggy（pytest にも含まれる）だけです。\
HTTP の API を確かめるときも、HTTP のライブラリを追加で入れる必要はありません（リクエストは、FastAPI や Flask などフレームワークのテスト用クライアントで送ります）。

## はじめかた: 作るのは YAML 1つだけ

CLI を実行して確かめるだけなら、作るのは YAML のファイル1つです。\
conftest.py も Python のテストコードも要りません。\
ここでは、名前を渡すとあいさつを表示する小さな CLI `hello.py` を確かめます。\
`hello.py` は自作の CLI の代わりです。\
下のファイルをそのまま写せば、手順のとおりに動きます。

```text
myproject/
└── tests/
    ├── hello.py                   ← 確かめたい CLI（自作のもの）
    ├── casebook_hello.yaml        ← 1. これを作る
    └── golden/casebook_hello/     ← 2. pytest --casebook-update で自動で作られる
        └── greet.txt
```

```python
# tests/hello.py
import argparse

parser = argparse.ArgumentParser(prog="hello")
parser.add_argument("--name", required=True)
print(f"こんにちは、{parser.parse_args().name}さん")
```

**1. `tests/casebook_hello.yaml` を作る**

ファイル名は `casebook_` で始めます（`*.casebook.yaml` でも構いません）。

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gyuro-dev/pytest-casebook/main/src/pytest_casebook/casebook.schema.json
title: hello コマンド
command_prefix: [python, hello.py]  # どのケースでも先頭に付ける部分（確かめたいコマンド）

cases:
  - name: greet                         # ケース名: 文字（日本語も可）・数字・_ - .（先頭に . と - は不可）
    description: 名前を渡すとあいさつする
    command: --name 佐藤

  - name: greet_error
    description: 名前を渡さないとエラーになる
    command: --name
    expect:                             # 期待結果を YAML に書くこともできる
      exit_code: 2
      stderr: {$contains: --name}
```

各ケースは `python hello.py --name 佐藤` のように、`command_prefix` と `command` をつないで実行します。\
コマンドは、YAML のあるディレクトリ（ここでは `tests/`）で実行します。\
そのため `command_prefix` には、インストール済みのコマンド（`[mycli]` など）か、この例のように、そのディレクトリからのパスでスクリプトを書きます。

**2. 期待出力ファイルを作る**

```bash
uv run pytest --casebook-update
```

（uv を使っていなければ `pytest --casebook-update`。以下のコマンドも同じです）

`expect:` を書いていないケース（ここでは greet）は、実際の出力から `tests/golden/casebook_hello/<ケース名>.txt` が作られます。\
`expect:` を書いたケースは、YAML の期待結果と比べるだけで、ファイルは作りません。

```text
# case: greet
# command: python hello.py --name 佐藤
# exit_code: 0
----- stdout -----
こんにちは、佐藤さん
```

比べるのは結果（`# exit_code:` と `-----` の見出しより下）だけです。\
`# case:` や `# command:` の行は読む人のための説明なので、期待出力ファイルを手で書くときは省けます（`# exit_code:` など、`# …:` の行を書くときは、ファイルの一番上に置きます）。\
出力が1つだけなら、本文だけを書けば十分です（[期待出力ファイルの書き方](#期待出力ファイル)）。

```text
こんにちは、佐藤さん
```

**3. 中身を確かめて commit する**

期待出力ファイルの中身が正しいことを確かめて、YAML と一緒に commit します。\
これ以降は、`uv run pytest` を実行するたびに、実際の出力をこのファイルと比べます。\
動きを変えたときは `--casebook-update` で作り直し、git の差分で変わったところを確かめます。

**結果を表で見る**

```bash
uv run pytest --casebook-html=reports/casebook.html
```

レポートの既定は英語です。\
日本語にするときは、`pyproject.toml` に一度だけ書きます。

```toml
[tool.pytest.ini_options]
casebook_lang = "ja"
```

### 用語

| 用語 | 意味 |
|---|---|
| ケース | 確かめることの1件。YAML の `cases:` に1つずつ書く（試験項目表の1行） |
| ケースファイル | ケースを書いた YAML（`casebook_*.yaml`） |
| グループ | ケースの分類（`group:`）。入れ子にすると大項目・中項目・小項目になる |
| 期待出力ファイル | 実際の出力から作る「正しい結果」のファイル（ゴールデンファイル）。`--casebook-update` で作る |
| `expect:` | 期待結果を YAML に直接書く書き方。書いたときは期待出力ファイルを使わない |
| hook | conftest.py に書く、決まった名前の関数（`pytest_casebook_…`）。DB の準備など、YAML だけでは書けない部分を受け持つ |
| `casebook_env` | conftest.py で用意する「環境」（DB の接続やモックなど）。各 hook に `env` として渡る |

## HTML レポート

`--casebook-html=report.html` を付けると、結果を試験項目表（HTML のファイル1つ）として出力します。\
ケースファイルごとに、次の内容を出力します。

- 大項目ごとの件数と結果
- 確認が必要なケースの一覧（表の行へのリンク）
- どのケースにも使われていない期待出力ファイル（残っているときだけ。[期待出力ファイル](#期待出力ファイル)を参照）
- 階層（`levels`）の列を縦に結合した表。\
  ケース名・実行内容・確認内容・前提条件・期待結果・結果・時間を並べます。\
  失敗した行では差分を開いて見られます
- 期待出力ファイルと比べるケースでは、そのファイルの比べる部分を、行の下に折りたたんで出します。\
  ボタンでまとめて開け閉めできます（[詳しく](#レポートの期待出力の中身)は下）
- 前提条件には、default 以外の状態の名前と、ケースに書いた `setup:` を出します。\
  スキップや既知の不具合の理由は、結果の下に出します
- 時間はケースの実行だけを数えます（session の fixture で環境を作る時間は含みません）

ページの上部で、表を絞り込めます。\
結果（「失敗」など）を押すと、その結果のケースだけを出します（複数押すと、どれかに当てはまるケースを出します。「すべて」で元に戻ります）。\
入力欄に文字を入れると、グループ・ケース名・コマンド・確認内容・前提条件・期待結果にその文字を含むケースだけを出します（大文字と小文字は区別せず、空白で区切った語はすべて含むものに絞ります）。\
縦に結合したグループの列は残った行に合わせて結合し直し、合うケースのないファイルは隠します。\
ファイルごとの件数は、絞り込みによらず実行の全体を表します。\
レポートは1つの HTML ファイルで、ほかのファイルを読みません。\
JavaScript が動かない環境では、絞り込みの欄を出さずに、表の全体を出します。

試験の前に「これから何を確かめるか」を提出するときは、`--collect-only` と一緒に使います。\
ケースを実行せずに、結果の列が「未実施」の表を出します（前提条件と期待結果の列は、YAML から出ます。`result:` のない手動のケースは「手動」のまま）。

```bash
uv run pytest --collect-only --casebook-html=reports/plan.html
```

表の全体はこのようになります（[docs/screenshots](docs/screenshots) のケースから作ったもの。[デモの実物](https://gyuro-dev.github.io/pytest-casebook/)もあります）。

![試験項目表の HTML レポートの全体](docs/images/report-overview.png)

失敗したケースは、その行の下で差分を開いて見られます。

![失敗したケースの差分](docs/images/report-failure.png)

### 1回の実行で表を分ける (casebook_html_reports)

試験項目表は、ふつう決まった相手に向けて作ります（お客さん、開発チーム、英語で読むレビュアーなど）。\
相手ごとに YAML のファイルを分けてあれば、ini の `casebook_html_reports` で、1回の実行から相手ごとの表を出せます。\
1行が「出す HTML = 入れるケースファイルのパターン」で、パターンは `,` で区切ります。\
どちらも pytest の rootdir からのパスで、パターンにはグロブ（`*`・`**`）が使えるので、ディレクトリごとに1枚の表にもできます。

```toml
[tool.pytest.ini_options]
casebook_html_reports = [
  "reports/customer.html = tests/casebook_shop.yaml, tests/casebook_orders.yaml",
  "reports/ja.html       = tests/*_ja.yaml",
  "reports/en.html       = tests/*_en.yaml",
]
```

- `--casebook-html` で出す全体の表には、いつもすべてのケースが入ります。\
  どの行のパターンにも合わないファイルも、全体の表には必ず出ます。\
  2つは一緒に使えます
- 表の見出しと結果の文言は、入ったケースファイルの `lang:` がそろっていればその言語になります（[YAML の全体](#yaml-の全体)を参照）。\
  両方の言語のファイルが混ざった表は、全体の表と同じく ini の `casebook_lang` で決まります
- 表に入ったケースファイルが1つだけなら、ブラウザのタブの題名にそのファイルの `title:` を使います（ini に `casebook_html_title` を書いたときは、その題名）
- 入るケースのない表（パターンの綴りの誤り、`-k` / `-m` で全部除いたとき）は書かず、実行の最後にそう知らせます
- `--collect-only`・`casebook_html_golden`・`-k` / `-m` は、どの表にも同じように効きます
- 追加の表を出さずに実行するときは、`-o casebook_html_reports=`（空）を付けます（本番に近い環境で流すときに、いつもの表を上書きしたくない場合など）

完成例は [21_reports](examples/21_reports) にあります（同じ CLI を日本語と英語で確かめ、言語ごとに1枚の表にします）。

### レポートの期待出力の中身

期待出力ファイルを使うケース（`expect:` のないケース）では、期待出力の比べる部分も、同じようにケースの行の下に折りたたんで出します。\
出す量は ini の `casebook_html_golden` で選べます（`off`: 出さない / `summary`: 既定。`casebook_html_golden_lines` 行（既定 40）で打ち切る / `full`: 全部）。\
絞り込みの欄の横のボタンで、すべての期待出力をまとめて開く・閉じることができます。\
期待出力の中の `<datetime>` などの `<…>` は、実行ごとに変わる値の置き換えです（その注記を、ファイルの見出しの下に1行出します）。\
`--collect-only` でも出るので、実装の前に「期待値つきの試験項目表」としてレビューできます。

結果は「成功・更新（`--casebook-update` で書き直した）・手動（`result:` をまだ書いていない[手動のケース](#手動のケース-manual)）・スキップ・想定どおり失敗・想定外に成功・失敗・エラー・未実施」のどれかで表示します。\
「未実施」は、集めたが実行していないケースです（`-x` で途中で止まったときなど）。\
pytest-html は要りません（一緒に使うこともできます）。

## やりたいことから探す

ほとんどのことは YAML だけでできます。\
DB を使うときや、テスト用の環境を渡したいときだけ、conftest.py に hook（決まった名前の関数）を足します。

表のほとんどの行に、そのまま動くサンプルを [examples](examples) に用意しています（サンプルの列が「—」の行にはありません）。\
サンプルのディレクトリをコピーして、名前を書き換えるところから始められます。

| やりたいこと | 書く場所 | 書くもの | サンプル |
|---|---|---|---|
| CLI を実行して、出力を確かめたい | YAML | `command_prefix` と `command` | [01_cli](examples/01_cli) |
| Python の関数を呼んで、戻り値を確かめたい | YAML | `call: モジュール:関数` と `args` / `kwargs` | [02_function](examples/02_function) |
| 例外になることを確かめたい | YAML | `expect: {raises: ValueError}` | [03_exception](examples/03_exception) |
| 期待結果を YAML に直接書きたい | YAML | `expect:`（[書き方](#期待結果-expect)） | [04_expect](examples/04_expect) |
| 引数だけ違うケースを表の形で並べたい | YAML | `params:`（[書き方](#表の形で同じケースを並べる-params)） | [20_params](examples/20_params) |
| ケースを大項目・中項目・小項目に分けたい | YAML | `group:` の入れ子（[書き方](#グループ)） | [05_groups](examples/05_groups) |
| 入力ファイルを置いてから実行したい / できたファイルを確かめたい | YAML | `setup: {files: ...}` と `observe: [files]` | [06_files](examples/06_files) |
| 同じ操作を「通常時」「障害時」で確かめたい | YAML ＋ conftest.py | `states:` ＋ `pytest_casebook_setup` | [07_states](examples/07_states) |
| DB に行を入れてから実行し、実行後の DB を確かめたい | YAML ＋ conftest.py | `casebook_env`・`pytest_casebook_setup`・`pytest_casebook_observe`・`pytest_casebook_prepare_call` | [08_db](examples/08_db) |
| CLI を同じプロセスで動かして、モックを渡したい | YAML ＋ conftest.py | `pytest_casebook_run_command` ＋ `run_in_process` | [09_in_process](examples/09_in_process) |
| 実行のたびに変わる ID・日時をそろえたい | YAML | `normalize:`（hook でも書ける） | [10_normalize](examples/10_normalize) |
| ケースに自分用の情報を付け、同じ YAML を pytest の外でも使いたい | YAML ＋ Python | `meta:` と `pytest_casebook.load()` | [11_meta_load](examples/11_meta_load) |
| 期待出力ファイルを手で書きたい | 期待出力ファイル | 本文だけ（ヘッダーは省ける） | [12_handwritten_golden](examples/12_handwritten_golden) |
| 理由を付けてケースを止めたい / 既知の不具合を書いておきたい | YAML | `skip: 理由` / `xfail: 理由` | [13_skip_xfail](examples/13_skip_xfail) |
| 環境に足りないもの（ディスクイメージ・テスト用のデータ・サービス）があるときだけ、ケースを止めたい | YAML ＋ conftest.py | `marks: [needs_disk]` ＋ `pytest_collection_modifyitems` でスキップを足す（または `-m "not needs_disk"`）（[やり方](#環境によってスキップする)） | — |
| HTTP の API を呼んで、ステータスやレスポンスを確かめたい | YAML ＋ conftest.py | `request:` ＋ `pytest_casebook_request` | [14_http_hook](examples/14_http_hook) |
| FastAPI の API と DB を確かめたい | YAML ＋ conftest.py | `request:`・`setup:`・`expect:` ＋ TestClient | [15_fastapi](examples/15_fastapi) |
| Flask の API と DB を確かめたい | YAML ＋ conftest.py | `request:`・`setup:`・`expect:` ＋ test_client | [16_flask](examples/16_flask) |
| 同じケースを別々の環境（ローカルとステージング、モックと本物など）に流したい | conftest.py ＋ コマンドライン | `casebook_env` で切り替え、`-o casebook_golden_dir=…` と `-m`（[やり方](#複数の環境に流す)） | [17_targets](examples/17_targets) |
| AWS を確かめたい（S3 にファイル、DynamoDB に行を入れ、実行後の DynamoDB・SQS・S3 を見る） | YAML ＋ conftest.py | `setup:`・`expect:` ＋ `pytest_casebook_setup` / `pytest_casebook_observe` で boto3（moto のモック。[書き方](#aws-moto-と実-aws)） | [19_aws](examples/19_aws) |
| 手動の確認（目視・帳票など）も同じ表に載せたい | YAML | `manual:` と `result:`（[書き方](#手動のケース-manual)） | [18_manual](examples/18_manual) |
| 試験の前に、これから確かめる項目の表を出したい | コマンドライン | `pytest --collect-only --casebook-html=plan.html`（結果は「未実施」。[やり方](#html-レポート)） | — |
| HTML レポートを出しながら、カバレッジも測りたい | pyproject.toml ＋ コマンドライン | pytest-cov と、coverage.py の `patch = ["subprocess"]`（[やり方](#カバレッジを測る)） | — |

日時（`2026-10-19T12:34:56Z` など）と UUID は、何もしなくても `<datetime>` / `<uuid>` に置き換えてから比べます。

YAML を書くときの注意です。

- 値の途中に `: `（コロンと空白）や ` #`（空白とシャープ）があると、YAML の区切りやコメントとして読まれます。\
  `description: "setup: の説明"` のように、値全体を `"` で囲んでください
- `command:` にファイルのパスを書くときは、`/` で区切ってください（`C:/data/in.csv`）。\
  文字列の command は shell と同じ書き方で区切るため、`\` が消えます。\
  `\` のまま書きたいときは、`command: ['C:\data\in.csv']` のようにリストで書きます
- エディタで補完と検証を使えます（[エディタでの補完と検証](#エディタでの補完と検証)）
- `call:` で呼ぶモジュールは、YAML と同じディレクトリに置けば import できます。\
  ただし、ディレクトリが違っても同じ名前のモジュール（たとえば2か所の `utils.py`）は、先に import したほうが使われます。\
  モジュール名はプロジェクトの中で重ならないようにしてください

## 完成例: DB を使う関数を確かめる

DB を使うときは、YAML ＋ conftest.py の2つを作ります。

```text
myproject/
├── orders.py                      ← 確かめたい関数（place_order）
└── tests/
    ├── conftest.py                ← DB の用意・行の投入・行の取り出し
    └── casebook_orders.yaml       ← ケース
```

**tests/casebook_orders.yaml**

```yaml
title: 注文
levels: [大項目, 中項目]

cases:
  - group: 注文する
    cases:
      - group: 在庫がある
        cases:
          - name: order_ok
            description: 在庫が減り、注文が1行増える
            setup:
              db:                                      # pytest_casebook_setup に渡る
                stock: [{item: apple, count: 10}]
            call: orders:place_order
            args: [apple, 3]
            expect:
              return: {item: apple, quantity: 3}       # 書いたキーだけを比べる
              db.stock: [{item: apple, count: 7}]      # pytest_casebook_observe で取り出す
              db.orders: [{item: apple, quantity: 3}]
      - group: 在庫が足りない
        cases:
          - name: order_out_of_stock
            description: 例外になり、DB は変わらない
            setup:
              db:
                stock: [{item: melon, count: 2}]
            call: orders:place_order
            args: [melon, 5]
            expect:
              raises: OutOfStock
              db.stock: [{item: melon, count: 2}]
              db.orders: []
```

**tests/conftest.py**

```python
import contextlib
import sqlite3

import pytest


@pytest.fixture(scope="session")
def casebook_env():
    """テストで使う DB を用意する。この値が各 hook の env に渡る。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("create table stock (item text primary key, count integer)")
    conn.execute("create table orders (id integer primary key, item text, quantity integer)")
    yield conn
    conn.close()


@contextlib.contextmanager
def _insert(conn, tables):
    for table, rows in tables.items():
        for row in rows:
            marks = ", ".join("?" for _ in row)
            conn.execute(
                f"insert into {table} ({', '.join(row)}) values ({marks})", list(row.values())
            )
    try:
        yield
    finally:  # ケースが終わったら消す（次のケースに影響しないように）
        conn.execute("delete from stock")
        conn.execute("delete from orders")


def pytest_casebook_setup(env, data):
    """YAML の setup: の内容（files 以外）を受け取って準備する。"""
    return _insert(env, data.get("db", {}))


def pytest_casebook_prepare_call(env, args):
    """関数の先頭の引数に DB の接続を渡す。"""
    args.insert(0, env)


def pytest_casebook_observe(target, env):
    """observe: / expect: の db.<テーブル名> を取り出す。並び順は必ずそろえる。"""
    if target.startswith("db."):
        cur = env.execute(f"select * from {target[3:]} order by 1")
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur]
    return None
```

期待結果と違うときは、違う箇所を1つずつ並べ、そのあとに実際の値を1件1行で出します。

```text
[order_ok]（9 行目） 注文する > 在庫がある 在庫が減り、注文が1行増える
期待結果と違います:
  - db.stock[0].count: 期待 7 / 実際 10
----- 実際の db.stock -----
{"item": "apple", "count": 10}
```

[examples/shop](examples/shop) は、コマンド・関数・例外・ファイル・DB・状態を、1つの小さなお店のアプリで組み合わせた例です（3階層のグループ。期待出力ファイルと `expect:` を並べています）。\
次のように実行します。

```bash
uv run pytest examples/shop -o casebook_lang=ja --casebook-html=reports/shop.html
```

---

## リファレンス

### YAML の全体

```yaml
title: 見出し                  # レポートの見出し（省略時はファイル名）
description: 説明
lang: ja                       # このファイルのメッセージとレポートの行の言語（省略時は ini の casebook_lang）
levels: [大項目, 中項目, 小項目] # 階層の呼び名。いくつでも（省略時は ini の casebook_levels）
command_prefix: [python, -m, mytool]  # {casebook_dir} は YAML のあるディレクトリになる
states:                        # 状態名 -> 内容（名前を付けた setup:。下の「状態」を参照）
  default: {}
  outage: {db: down}
golden_dir: golden             # 期待出力の置き場所（このファイルからの相対パス）
check_orphans: true            # ケースのない期待出力ファイルが残っていたら失敗にする
normalize:                     # 出力に当てる置き換え
  - {pattern: 'req-[0-9a-f]+', replace: '<request-id>'}
meta: {owner: qa}              # 自由に使う情報（下の「meta」を参照）
env: {LANG: C}                 # ケースの環境変数（下の「環境変数」を参照）
timeout: 5                     # 中のケースの既定の timeout（グループやケースの値が優先）
cases: [...]                   # ケースまたはグループのリスト
```

`command_prefix` とケースの `command` は、どちらも文字列（shell と同じ書き方で区切る。`store add 'apple pie'`）か、リスト（区切らずにそのまま渡す。`[store, add, apple pie]`）で書けます。\
2つの書き方は混ぜて使えます。\
`command_prefix: store` と `command: [add, 'apple pie']` なら、`store add "apple pie"` を実行します。\
`command_prefix` は、いつも `command` の引数の前に付きます。\
ファイルに `command_prefix` がなければ、ini の `casebook_command_prefix` を使います。

`lang`（`en` か `ja`）は、このファイルの言語です。\
ケースのメッセージ（比較の失敗、実行の誤り、YAML の書き方の誤り）、レポートの行の文言（前提条件・期待結果）、`levels` の既定、`run_case()` の既定の言語がこれになります。\
書かなければ ini の `casebook_lang` が効きます。\
読む人ごとに言語の違うファイルを作るとき（[1回の実行で表を分ける](#1回の実行で表を分ける-casebook_html_reports)）に使います。

### グループ

```yaml
- group: 価格計算           # 名前（入れ子の深さがそのまま階層になる）
  description: 説明
  state: outage            # 中のケースの既定の状態
  marks: [slow]            # 中のケースに付ける pytest のマーク
  meta: {area: price}      # 中のケースに付ける meta
  env: {TZ: UTC}           # 中のケースに付ける環境変数
  timeout: 5               # 中のケースの既定の timeout
  skip: 仕様が決まるまで止める  # 中のケースすべてを、この理由でスキップする（xfail: も書ける）
  cases: [...]
```

`-k 価格計算` のように、グループ名で絞り込んで実行できます。\
HTML レポートの階層の列は、実際に使われているグループの深さだけ出します（`levels` に3つ書いても、グループが1階層なら列は1つです）。

### ケース

| キー | 内容 |
|---|---|
| `name` | ケース名。期待出力のファイル名になるので、文字（日本語も可）・数字・`_`・`-`・`.` で書く（先頭に `.` と `-` は使えない）。大文字小文字だけが違う名前（`Add` と `add`）は、Windows で期待出力が同じファイルになるため誤り |
| `description` | 確認する内容 |
| `command` | CLI として実行する引数。`command_prefix` の後ろに付く。文字列は shell と同じ書き方で区切り、リスト（`[a, 'b c']`）は区切らずにそのまま渡す。`command_prefix` とは書き方を混ぜてよい（`command_prefix: store` と `command: [add, 'apple pie']` など）。`command_prefix` があれば空文字（`""`）でもよい |
| `stdin` | command の標準入力 |
| `stdin_file` | 標準入力に渡すファイル。YAML のディレクトリからの相対パス。`stdin` とは同時に書けない |
| `timeout` | ケースを時間切れで失敗にするまでの秒数（`command`・`call`・`request`。[詳しく](#時間の上限-timeout)） |
| `env` | ケースを実行する間の環境変数。今の環境変数に重ねる（[書き方](#環境変数-env)） |
| `call` | 呼び出す関数（`モジュール:関数`、`モジュール:クラス.メソッド`）。`async def` の関数は終わるまで待つ |
| `args` / `kwargs` | 関数に渡す引数 |
| `request` | 送る HTTP のリクエスト（`"POST /users"` か、method・path・query・headers・json・body。[書き方](#http-の-api-request)） |
| `manual` | 手動のケースの手順。実行しない（[書き方](#手動のケース-manual)） |
| `result` | 手動のケースを手で確かめた結果。`passed`・`failed`・`skipped` のどれか |
| `state` | 状態名（`states:` に書いたもの） |
| `setup` | 前提条件。`files`（作業ディレクトリに置くファイル）と、`pytest_casebook_setup` に渡す内容 |
| `observe` | 実行後に取り出して、期待出力ファイルに残す対象。`files`（組み込み）か、`pytest_casebook_observe` で取り出す名前（[書き方](#実行後の値-observe)） |
| `expect` | 期待結果。書いたときは期待出力ファイルを使わない（手動のケースでは文章。文字列か文字列のリスト） |
| `marks` | pytest のマーク名のリスト |
| `skip` / `xfail` | 止める理由 / 失敗すると分かっている理由。ターミナル（`pytest -rsx`）と HTML の結果の列に出る |
| `meta` | 自由に使う情報（[meta](#meta)） |
| `golden` | 期待出力のファイル名（省略時は `<name>.txt`） |
| `params` | このケースに重ねる行。要素ごとに1件のケースになる（[書き方](#表の形で同じケースを並べる-params)） |

`command`・`call`・`request`・`manual` は、どれか1つだけを書きます。\
上の表にないキーは、打ち間違いを見つけるためにエラーにします。\
自分で使う情報は `meta:` の中に書きます。

### 期待結果 (expect)

ケースは、期待出力ファイルか `expect:` のどちらか一方と比べます。\
両方を組み合わせることはできません。\
`expect:` にどれか1つでもキーを書くと、そのケースは YAML の期待結果で確かめるケースに切り替わり、期待出力ファイルは読みも書きもしません。\
比べるのは `expect:` に書いた項目だけです。\
そのため、「`exit_code` は YAML に書き、stdout は期待出力ファイルで比べる」ことはできません。\
両方を確かめるときは、両方を `expect:` に書くか、`expect:` を書かずに期待出力ファイルに両方を残します。

```yaml
expect:
  exit_code: 1                          # command
  stdout: ""                            # 文字列は完全一致（末尾の改行は問わない）
  stderr: {$contains: エラー}             # {$contains: ...} 含む / {$regex: ...} 正規表現
  return: {item: apple}                 # call。辞書は書いたキーだけを比べる
  raises: ValueError                    # call。型名（継承した型も一致）
  db.stock: [{item: apple, count: 7}]   # 上記以外は observe の対象
```

| 項目 | 書けるケース | 比べ方 |
|---|---|---|
| `exit_code` | command | 整数の完全一致 |
| `status` | request | 整数の完全一致 |
| `json` | request | レスポンスの本文を JSON として読み、`return` と同じ方法で比べる |
| `body` | request | 本文の文字列。`stdout` と同じ比べ方 |
| `headers` | request | ヘッダー名 -> 期待値。書いたヘッダーだけを、名前の大文字小文字を区別せずに比べる。値は `stdout` と同じ比べ方 |
| `stdout` / `stderr` | command・call | 文字列なら完全一致、`{$contains: ...}` なら含む、`{$regex: ...}` なら正規表現。期待値の文字列には、実際の出力と同じ置き換え（`normalize:`・組み込みの日時と UUID）を当ててから比べる（`stdout: 1970-01-01T00:00:00` は `<datetime>` と比べる）。`raises`・`return`・`json`・observe の対象の中の文字列も同じ。`{regex}` / `{$regex}` の中だけは触らない |
| `return` | call | 辞書は書いたキーだけ、リストは件数と各要素、それ以外は完全一致 |
| `raises` | call | 下の表のとおり |
| 上記以外（`db.users`・`files` など） | すべて | observe の対象として取り出し（`observe:` は要らない）、`return` と同じ方法で比べる |

| `raises` の書き方 | 一致する例外 |
|---|---|
| `ValueError` | ValueError と、それを継承した例外 |
| `mypkg.errors.AppError` | モジュール名まで同じ型と、それを継承した例外 |
| `Outer.Inner` | クラスの中に定義した例外 |
| `"ValueError: 個数は1以上にしてください"` | 型は上と同じ比べ方で、メッセージは完全一致 |
| `{$contains: ...}` / `{$regex: ...}` | `実際の型名: メッセージ` の文字列に含む / 正規表現に合う |

call で例外が出たのに `raises` を書いていない場合は失敗にします。

比べ方のキーワードはいつも `$` で始めます（`{$contains: ...}`・`{$regex: ...}`）。覚える書き方は1つです。\
`return`・`json`・observe の対象（`db.*` など）の値の中では `$` が必須です（`contains` などのキーを本当に持つデータと区別するため）。\
`stdout`・`stderr`・`raises`・`body`・`headers` の下では、`$` を省いて `{contains: ...}` と書いても動きます。

```yaml
expect:
  json:
    message: {$contains: 在庫が足りません}     # この文字列を含む
    code: {$regex: '^E\d{3}$'}              # 正規表現に合う
  db.users:
    $unordered:                              # 順序を問わない（件数は同じ）
      - {name: 鈴木}
      - {name: 佐藤}
  db.history:
    $includes:                               # この要素があればよい（ほかにあってもよい）
      - {action: withdraw}
```

知らない比べ方（`$unorderd` などの打ち間違い）は、YAML を読む時点でエラーにします。

期待出力ファイルと `expect:` の使い分けの目安です。

- 長い出力（表やツリーの表示）や、実行後のテーブル全体を残したいとき → 期待出力ファイル（`--casebook-update` で作れます）
- 決まった値だけを確かめたいとき → `expect:`（YAML を読めば仕様が分かります。`--casebook-update` では書き換えません）

### 期待出力ファイル

`--casebook-update` は、次の形で期待出力ファイルを作ります。

```text
# case: price_member
# command: shop price apple 3 --member
# state: sold_out
# exit_code: 0
----- stdout -----
apple x 3 = 324 円
----- stderr -----
（stderr があるときだけ）
```

比べるのは、結果である `# exit_code:`（request なら `# status:`）と、`----- 見出し -----` より下の本文だけです。

- `# case:`・`# description:`・`# command:`・`# call:`・`# args:`・`# kwargs:`・`# request:`・`# state:` の行は説明で、比べません。\
  手で書くときは省けます
- `# キー: 値` のヘッダーは、ファイルの一番上に書きます。
  - ヘッダーは、これらのヘッダーでない行が出たところで終わります
  - そのため、手で書いたファイルが空行や自由なコメント（`# メモ`）で始まると、そのあとの `# exit_code:` は本文として読まれます
  - メモは、ケースの `description:` など、ほかの場所に書いてください
- ヘッダーの値は1行です（複数行のコマンドも1行にして書きます）
- `# exit_code:` / `# status:` を書かなければ、終了コード / ステータスは比べません
- 見出しのない本文は、command なら stdout、call なら return、request なら json として扱います。\
  出力が1つだけなら、本文だけを書けば十分です
- 書いていない見出しは、空であることを期待します（stderr の見出しがなければ、stderr は空でなければなりません）
- `--casebook-update` は、結果が変わったときだけファイルを書き直します。\
  手で書いた期待出力ファイルは、結果が同じなら書き方を変えません
- ケースを消したり名前を変えたりしたのに期待出力ファイルだけが残っていると、`unused_golden_files` という確認が失敗します（サブディレクトリの中も見ます）。
  - この確認は、pytest-casebook が YAML 1本につき1件のテストとして足します。\
    そのため pytest の collected は、ファイルごとにケースの数より1件多くなります
  - HTML レポートの行にはしませんが、失敗したときは、そのファイルの節に使われていない期待出力ファイルを出します
  - 調べるのは `.txt` と、`golden:` で使った拡張子（`.json` など）のファイルです。\
    置き場所に置いたメモなど、ほかのファイルは知らせません
  - 同じディレクトリのほかのケースファイルが使う期待出力は「使われている」と数えるので、複数の YAML で `golden_dir:` を共有しても、消し忘れと誤って報告しません
  - この確認を止めるときは、YAML に `check_orphans: false` を書きます

ini に `casebook_golden_description = true` を書くと、`--casebook-update` が書く期待出力ファイルの `# case:` の直後に、`# description: <ケースの description>` の行が入ります（description のあるケースだけ。複数行の description は1行にします）。\
ほかの `#` の説明の行と同じく比べないので、設定を入れても、既存のファイルが失敗したり書き直されたりはしません。\
既存のファイルには、次に書き直されたときにこの行が入ります。\
既存のファイル全部にすぐ入れるときは、`pytest --casebook-update-headers` を実行します。\
結果が同じ期待出力ファイルのヘッダーを書き直します（結果が違うファイルは、書き直さずに失敗します）。\
比べるのは結果だけなので、ヘッダーを省いて手で書いた期待出力ファイルも、`--casebook-update` が書くのと同じ形に書き直されます。

### 実行後の値 (observe)

`observe:` には、実行後に取り出して**期待出力ファイルに残す**値（DB のテーブル、ファイルなど）を書きます。\
期待出力ファイルと比べるケースのためのものです。\
`expect:` のあるケースでは、`observe:` を書かずに、確かめたい対象を `expect:` に直接書きます（例: `expect: {db.users: [...]}`）。\
それだけで自動で取り出して比べます。\
`expect:` のあるケースで、`expect:` にない対象を `observe:` に書くと誤りにします（取り出した値を捨てることになるためです）。

- 期待出力ファイルを使うケースでは、取り出した値を `----- observe: <対象> -----` として期待出力に加えます
- リスト（DB の行など）は、1件を1行の JSON にして書きます。\
  値が変わったときに差分がその行だけに出ます
- `files` は、作業ディレクトリのファイルとその中身を `=== ファイル名 ===` の形で書きます。\
  改行は LF にそろえて比べます。\
  UTF-8 で読めないファイル（画像など）は、大きさと SHA-256 の1行にします

### 前提条件 (setup)

- `setup`（またはケースの状態）に `files:` を書くと、ケースごとに新しい一時的な作業ディレクトリを作ってファイルを置き、command も call もそのディレクトリで実行します。\
  空の `files: {}` でも同じで、ケースごとにまっさらなディレクトリで動かせます（空でない出力先を受け付けない CLI など）。\
  `files:` を書かなければ（`observe:` / `expect:` で `files` を取り出すときを除き）、YAML のディレクトリで実行します。\
  出力に出る作業ディレクトリのパスは `<tmp>` に置き換えます
- 作業ディレクトリは YAML のディレクトリとは別の場所です。\
  YAML の隣のスクリプトなどは `{casebook_dir}` を付けて指します（例: `command_prefix: [python, "{casebook_dir}/tool.py"]`）。\
  出力に出る YAML のディレクトリのパスは `{casebook_dir}` に置き換えます
- `files` 以外の内容は `pytest_casebook_setup` に渡します。\
  hook がコンテキストマネージャを返したときは、ケースを実行して値を取り出し終えたあとに、それを閉じます（後片付けに使えます）
- 準備はケースごとにやり直すので、前のケースの影響は残りません

### 状態 (states)

状態は「名前を付けた setup:」です。\
何度も使う前提条件に名前を付けておき、ケースやグループの `state:` で選びます。

```yaml
states:
  default:
    flags: {maintenance: false}
  maintenance:
    flags: {maintenance: true}
    files: {notice.txt: メンテナンス中}

cases:
  - name: during_maintenance
    state: maintenance
    setup:
      db: {users: [...]}     # 状態の内容に重ね、同じキーはケースの値で上書きする
    call: app:handle
```

- 選んだ状態の内容にケースの `setup:` を重ね（同じキーはケースの値で上書きする）、`pytest_casebook_setup` の `data` に渡します（`files` はファイル名ごとに重ねます）
- `state:` を書かないケースは `default` の状態になります。\
  `states:` に `default` がなければ、状態の内容がないものとして動きます（1つの状態を足しただけで `default: {}` を書かされることはありません）
- 状態の書き方は `setup:` と同じで、書き方の誤りも同じように確かめます

### HTTP の API (request)

`request:` のケースは、HTTP のリクエストを送ってレスポンスを確かめます。\
pytest-casebook 自身は HTTP を送りません。\
送るのは conftest.py の `pytest_casebook_request` で、フレームワークのテスト用クライアントを使います。

```yaml
request_defaults:                     # どのリクエストにも付けるヘッダー
                                      # （ケースで上書きできる。ヘッダー名の大文字小文字は問わない）
  headers: {Authorization: Bearer test-token}

cases:
  - name: list
    request: GET /todos                # "メソッド パス" の文字列（メソッドを省くと GET）
  - name: create
    request:                           # マッピングでも書ける
      method: POST
      path: /todos
      query: {notify: true}            # /todos?notify=true
      headers: {X-Request-Id: abc}
      json: {title: 牛乳を買う}         # JSON 以外を送るときは body: に文字列
    expect:
      status: 201
      json: {title: 牛乳を買う}         # 書いたキーだけを比べる
      headers: {Location: {$regex: '^/todos/\d+$'}}
      db.todos: [{title: 牛乳を買う}]   # DB の変化も確かめられる
```

conftest.py には、リクエストを送る hook を書きます。\
よく使うクライアント向けのアダプターを `pytest_casebook.http` に用意しています（アダプターはクライアントのメソッドを呼ぶだけで、フレームワークを import しません）。

```python
from pytest_casebook.http import send_with_httpx_client, send_with_werkzeug_client


# FastAPI / Starlette の TestClient（httpx の API を持つクライアント）
def pytest_casebook_request(request, env):
    return send_with_httpx_client(env.client, request)


# Flask の test_client（Werkzeug のクライアント）
def pytest_casebook_request(request, env):
    return send_with_werkzeug_client(env.client, request)
```

ほかのクライアントでも、`request`（`HttpRequest`: `method`・`path`・`url`・`query`・`headers`・`json`・`body`）を読んで `HttpResponse(status, body, headers)` を返せば使えます（[14_http_hook](examples/14_http_hook) はフレームワークなしの例です）。

期待出力ファイルには `# status:` と、本文が JSON なら整形した `----- json -----`、それ以外なら `----- body -----` を書きます。\
レスポンスのヘッダーは期待出力ファイルに書きません（日時などで毎回変わるため）。\
ヘッダーを確かめるときは `expect:` の `headers` を使います。

### 例外の扱い

- **call**: 例外は戻り値と同じく結果として扱います。\
  期待出力では `----- raises -----` に `型名: メッセージ` を書きます。\
  例外が出たあとでも observe を行うので、「例外になったとき DB が変わらないこと」も確かめられます
- **command（別プロセス）**: CLI の中の例外は、終了コード（Python なら 1）と stderr のトレースバックとして比べます
- **command（`run_in_process`）**: `sys.exit()` は終了コードに、それ以外の例外は終了コード 1 と stderr の `型名: メッセージ` にします。\
  `run_in_process(main, argv, traceback=True)` ならトレースバック全体を stderr に書きます（行番号やパスが入るため、期待出力は変わりやすくなります）
- `setup` や `observe` の hook の中で出た例外は、比べる対象ではなくテストのエラーになります

### 時間の上限 (timeout)

`timeout:` は、ケースの実行にかけてよい秒数です。\
ケースごとに書くほか、ファイルの先頭やグループにも書けます（中のケースの既定になります）。\
いちばん近い値が使われ、ケース自身の `timeout:` が最優先です。\
手動のケース（`manual:`）は実行しないので、既定の値は当てはまりません。

- **command（別プロセス）**: プロセスを止めて、ケースを失敗にします
- **call / request**: 関数（request では `pytest_casebook_request` hook）を別のスレッドで動かし、時間内に終わらなければケースを失敗にします。\
  Python ではスレッドを止められないため、**関数は止まりません**。\
  終わるまで裏で動き続けます。\
  時間切れのあとの出力は取り込まず、pytest の終了も妨げません。\
  止まったテストを本当に打ち切りたいときは、[pytest-timeout](https://pypi.org/project/pytest-timeout/) を使ってください
- **command（`run_in_process`）**: `pytest_casebook_run_command` hook に任せます（`case.timeout` で秒数を読めます）

`timeout:` がなければ、関数と hook はテストと同じスレッドで動きます。\
書いたときは別のスレッドで動くので、作ったスレッドでしか使えないもの（`pytest_casebook_setup` で作った `sqlite3` の接続など）は使えません。\
呼ぶ前に設定したコンテキスト変数（`contextvars`）は、関数からも読めます（複製を渡します）。

カレントディレクトリは、プロセス全体で1つです。\
`setup.files` のある（`files: {}` も含む）ケースは専用の作業ディレクトリで動き、ケースが終わるとそのディレクトリから戻ります。\
そのため、時間切れのあとも動き続ける関数からは、カレントディレクトリが別の場所（元のディレクトリや、あとのケースの作業ディレクトリ）に見えます。\
相対パスでファイルを読み書きすると、違うファイルを触ることがあります（あとのケースの `files` の比較が壊れることもあります）。\
時間切れになりうる関数では、絶対パスを使ってください。

### 手動のケース (manual)

自動にできない確認（画面を目で見る、印刷した帳票を確かめるなど）も、同じ試験項目表に載せられます。\
`command` / `call` / `request` の代わりに、`manual:` に手順を書きます。\
手動のケースは実行しません。

```yaml
cases:
  - group: 印刷
    cases:
      - name: print_layout
        description: 印刷しても表が崩れない
        manual: |
          印刷プレビューを開く
          罫線がページをまたいで途切れていないか目で確かめる
        expect:                      # 期待結果を文章で書く（文字列かリスト）
          - 2ページ目の先頭にも見出し行が出る
          - 罫線が途切れない
        result: passed               # 手で確かめた結果（確かめるまでは書かない）
```

- HTML レポートでは、ケース名の下に手順を、期待結果の列に `expect:` を出します
- `result:` がなければ、pytest ではスキップになり、レポートには**手動**と出ます。\
  まだ手で確かめていないケースを見つけるのに使えます
- `result: passed` / `failed` / `skipped` と書くと、pytest でもレポートでも、成功・失敗・スキップになります。\
  結果を書き込めば、`pytest --casebook-html=…` を1回実行するだけで、自動と手動の結果がそろった試験項目表になります
- `setup:` と `state:` は書けますが、前提条件として表に出すだけです（`pytest_casebook_setup` hook は呼びません）。\
  `args`・`kwargs`・`stdin`・`stdin_file`・`timeout`・`env`・`observe`・`golden` は書けません

### 表の形で同じケースを並べる (params)

引数と期待値だけが違うケースを並べると、共通のキーの繰り返しになります。\
共通の部分を1回だけ書き、違う部分を `params:` に行として並べると、そのケースはテンプレートになり、要素ごとに1件のふつうのケースに展開されます。

```yaml
cases:
  - name: shipping
    description: 送料の計算
    call: shop:shipping
    params:
      - {name: "0",    description: 0 円は送料 500 円,    args: [0],    expect: {return: 500}}
      - {name: "2999", description: 2999 円は送料 500 円, args: [2999], expect: {return: 500}}
      - {name: "3000", description: 3000 円から送料無料,  args: [3000], expect: {return: 0}}
```

`shipping-0`・`shipping-2999`・`shipping-3000` という3件のケースになります。\
各要素には `name` が必須で、ケース名は `<ケース名>-<要素名>` になります。\
要素ごとに `description` も書いておくと、試験項目表（HTML）の各行がそれだけで読めます。

要素のキーはテンプレートのキーをまるごと置き換えます（深い併合はしません）。\
要素に `expect:` を書くと、テンプレートの `expect:` 全体が置き換わります。\
重ねた結果は、ふつうのケースと同じように検証します。\
YAML のほかの部分を共有したいときは、アンカー（`&` / `*` / `<<:`）も使えます。

### 環境変数 (env)

`env:` で、ケースを実行するときの環境変数を設定します。\
ファイルの先頭・グループ・ケースのどこにでも書けます。

```yaml
env: {LANG: C, TZ: UTC}          # ファイルのすべてのケース
cases:
  - group: デバッグ出力
    env: {MYTOOL_DEBUG: 1}       # 数値は文字列（"1"）にする
    cases:
      - name: debug_report
        command: report
      - name: default_locale
        command: report
        env: {LANG: null}        # null で、外側に書いた値を消す
```

- ケースを実行する間、pytest のプロセスの環境変数（`os.environ`）に上書きで重ね、終わったら元に戻します。\
  どの種類のケースにも効きます。\
  別プロセスで実行する command は、その環境を受け継ぎます（ここで `PATH` を変えると、プログラムもその `PATH` で探します）。\
  `pytest_casebook_run_command` で同じプロセスで動かす CLI、`call:` の関数、`request:` の hook からも見えます
- 値の中の `{casebook_dir}` は、`command:` と同じく YAML のディレクトリになります（例: `env: {DATA_DIR: "{casebook_dir}/data"}`）
- 内側が外側を、変数ごとに上書きします（ファイル → グループ → ケース）。\
  値は文字列か数値で書きます。\
  `true` / `false` は誤りにします（`"true"` と書きます）。\
  `null` は外側の `env:` の値を消すだけで、シェルから受け継いだ環境変数は消しません
- hook では、重ねた結果を `case.env` でも読めます
- HTML レポートの前提条件の列には、ファイル全体の `env:` と違う変数だけを出します。\
  期待出力ファイルには書きません

### meta

`meta:` の中身を、pytest-casebook は見ません。\
プロジェクトで自由に使う情報（デモで見せるケースの印、担当者、実行する環境の制限など）を書く場所です。

```yaml
- group: IPv6
  meta: {moto_only: true}       # グループに書くと、中のケースすべてに付く
  cases:
    - name: find_ipv6
      command: find 2001:db8::31
      meta: {demo: true}        # グループの meta に重ね、同じキーはケースの値で上書きする
```

- hook では `case.meta` で読めます（上の例の find_ipv6 は `{"moto_only": True, "demo": True}`）
- ファイル全体の `meta:` は `doc.meta` で読めます
- pytest の `-m` で絞り込みたいときは、`meta:` ではなく `marks:` を使います

### 環境によってスキップする

`skip:` は、いつでもスキップします。\
環境に足りないもの（ディスクイメージ・テスト用のデータ・サービス）があるときだけスキップしたいときは、YAML だけでは書けません。\
`marks:` にはマークの名前しか書けず、`skipif(条件)` は書けないからです。\
ケースにマークを付け、スキップは conftest.py で足します。

```yaml
- group: ディスクイメージ
  marks: [needs_disk]
  cases: [...]
```

```python
# conftest.py
from pathlib import Path
import pytest


def pytest_collection_modifyitems(config, items):
    if not Path("data/disk.img").exists():
        skip = pytest.mark.skip(reason="data/disk.img がない")
        for item in items:
            if "needs_disk" in item.keywords:
                item.add_marker(skip)
```

- casebook のケースはふつうの pytest のテストなので、pytest のスキップのやり方はどれも使えます（理由は HTML の結果の列に出ます）
- スキップではなく、実行の対象から外したいときは `-m "not needs_disk"` で除きます（除いたケースはレポートに出ません）
- 知らないマークの警告が出ないよう、ini にマークを登録しておきます

```toml
[tool.pytest.ini_options]
markers = ["needs_disk: data/disk.img が必要"]
```

### pytest の外から読む (load)

テストと同じ YAML を、デモ用のスクリプトなど pytest の外でも使えます。

```python
import pytest_casebook

doc = pytest_casebook.load("tests/casebook_demo.yaml")
for case in doc.cases:
    if case.meta.get("demo"):
        print(" > ".join(case.path), case.name, case.command)
```

`load()` は pytest で集めるときと同じ検証をして、`CasebookDoc`（`title`・`levels`・`states`・`meta`・`env`・`cases` など）を返します。\
書き方に誤りがあれば `pytest_casebook.CasebookError` を出します。

`load()` は、そのままでは ini の設定を読みません。\
`load(path, ini=True)` とすると、pytest の設定ファイルから `casebook_*` の設定を読み、pytest で動かすときと同じ設定になります。\
`casebook_golden_dir`・`casebook_levels`・`casebook_command_prefix`・`casebook_lang` は読んだファイルに当て、`casebook_lang`・`casebook_encoding`・`casebook_builtin_patterns`・`casebook_golden_description` は `run_case()` の既定になります。\
設定ファイルは YAML のディレクトリから上へ探し、ディレクトリごとに `pytest.ini`・`pyproject.toml`（`[tool.pytest.ini_options]` があるときだけ）・`tox.ini`（`[pytest]` があるときだけ）・`setup.cfg`（`[tool:pytest]` があるときだけ）の順で、最初に見つかったものを使います。\
`load()` や `run_case()` に渡した引数は、ini の値より優先します。\
pytest の探し方を簡単にしたもので、`-c`・`--rootdir`・`-o` は考えません。

読んだケースは `run_case()` で実行もできます（`--case <名前>` を持つお試しスクリプトなど）。

```python
import conftest  # hooks には import した conftest モジュールをそのまま渡せる
import pytest_casebook

doc = pytest_casebook.load("tests/casebook_demo.yaml", ini=True)
case = next(c for c in doc.cases if c.name == "add_cli")
print(pytest_casebook.run_case(doc, case, hooks=conftest), end="")  # 文字列は改行で終わる
```

`run_case()` はケースを1件実行し（setup hook → 操作 → observe → 後片付け）、`--casebook-update` が書くものと同じ文字列を返します。\
実行ごとに変わる値は、置き換えたあとの形で入ります。\
期待出力ファイルとは比べません。\
`hooks` は、`pytest_casebook_*` という名前の関数を持つオブジェクトやモジュールで、import した conftest モジュールをそのまま渡せます。\
hook には pytest で動かすときと同じ引数が渡りますが、`config` だけは None です。\
手動のケースは実行できず、`pytest_casebook.CasebookRunError` を出します。\
コマンドが見つからないなどの実行の誤りも同じです。\
`call:` のケースの例外や 0 以外の終了コードは誤りではなく、返す文字列の中に入ります。

### hook と fixture

conftest.py に書きます。\
どの hook も、使う引数だけを受け取れば動きます（例: `def pytest_casebook_observe(target, env): ...`）。\
hook は、その conftest.py があるディレクトリより下の YAML のケースにだけ効きます。

| 名前 | 呼ばれるとき | 返すもの |
|---|---|---|
| `casebook_env` fixture | テストの開始時に1回（session） | 各 hook の `env` に渡す値（既定は None） |
| `pytest_casebook_setup(case, data, env, workdir)` | すべてのケースの前（setup: も states: もなければ data は空） | 後片付けのコンテキストマネージャ、または None |
| `pytest_casebook_request(case, request, env, workdir)` | request の実行 | `HttpResponse`。request: を使うときは必須 |
| `pytest_casebook_run_command(case, argv, env, cwd)` | command の実行 | `CommandResult`（`run_in_process` の戻り値）。None なら別プロセスで実行。`argv` は `command_prefix` と command の引数を合わせたもの。`case.command_argv` は command の引数だけで、prefix を含まない |
| `pytest_casebook_prepare_call(case, env, args, kwargs, workdir)` | call の前 | なし（`args` / `kwargs` をその場で書き換える） |
| `pytest_casebook_observe(target, case, env, workdir)` | 実行のあと | 取り出した値（None なら失敗） |
| `pytest_casebook_placeholders(env)` | 比べる前 | `(実際の値, 置き換え後)` のリスト |
| `pytest_casebook_patterns(env)` | 比べる前 | `(正規表現, 置き換え後)` のリスト |

どの hook にも、`config`（pytest の Config）が渡ります。\
pytest の外で `run_case()` から実行したときは `config` が None なので、`run_case()` と共用する hook では、None でも動くように書きます。\
ケースの状態の名前と内容は、`case.state` と `case.state_data` で読めます。\
ケースの `env:` の環境変数は、`case.env` で読めます。\
別プロセスで実行するときは、子プロセスが Python なら出力の文字コードを `casebook_encoding` にそろえます（`PYTHONIOENCODING` を設定します）。

### 複数の環境に流す

同じケースを、別々の環境（ローカルとステージング、モックと本物の AWS など）に流せます。\
専用の機能はなく、pytest と pytest-casebook にある仕組みを組み合わせます。

| やりたいこと | やり方 |
|---|---|
| つなぐ先を切り替える | `--target` のようなオプションを conftest.py に足し、`casebook_env` の中で切り替える |
| 期待出力ファイルを環境ごとに分ける | `-o casebook_golden_dir=golden_staging` のように、ini の置き場所をコマンドラインで替える |
| その環境でしか流さないケースを除く | ケースやグループに `marks: [local_only]` を付け、`-m "not local_only"` で除く |

```python
# conftest.py（プロジェクトの一番上に置く。pytest_addoption は起動時に読む conftest.py でしか呼ばれない）
def pytest_addoption(parser):
    parser.addoption("--target", default="local", choices=["local", "staging"])


@pytest.fixture(scope="session")
def casebook_env(request):
    if request.config.getoption("--target") == "staging":
        return connect_staging()
    return connect_local()
```

```bash
uv run pytest                                    # local（期待出力は golden/）
uv run pytest --target staging -o casebook_golden_dir=golden_staging -m "not local_only"
```

- YAML に `golden_dir:` を書くと、`-o` より YAML が優先されます。\
  環境で置き場所を替えるときは、YAML には書かないでください
- 環境によって答えが変わる確認は期待出力ファイルで、どの環境でも同じになる確認は `expect:` で書くと、期待値の重複が減ります
- 例は [examples/17_targets](examples/17_targets) にあります

### AWS (moto と実 AWS)

pytest-casebook は、自分では AWS につなぎません。\
入力は `pytest_casebook_setup` で入れ、結果は `pytest_casebook_observe` で取り出します（どちらも boto3 で書きます。[19_aws](examples/19_aws)）。

- `setup: {s3: {バケット/キー: 中身}, dynamodb: {テーブル: [行]}}` で、S3 にファイルを置き、DynamoDB に行を入れる
- `expect:` / `observe:` の `dynamodb.<テーブル>`・`sqs.<キュー>`・`s3.<バケット>` で、実行後の中身を取り出す

moto（AWS のモック）での注意です。

- moto の `mock_aws()` は、pytest のプロセスの中でしか効きません。\
  `call:` と `request:`（と `run_in_process` を使う `command:`）はモックになりますが、`command:` で別プロセスとして動かす CLI はモックになりません。\
  そのときは、moto のサーバーか LocalStack を立て、`env:` で `AWS_ENDPOINT_URL` を渡します
- DynamoDB は数を `Decimal` で返しますが、pytest-casebook がふつうの数（int / float）に直します。\
  そのため、YAML の `price: 300` がそのまま一致します
- DynamoDB の scan と SQS の受信は、順番が決まっていません。\
  hook で並べるか、`expect:` に `$unordered` を使います
- SQS は1回で 10 件までしか受け取れません。\
  空になるまで受け取り、受け取ったものは消します（消さないと、見えない時間が過ぎたあとに、あとのケースで見えてしまいます）

同じ YAML を、`casebook_env` を切り替えて実 AWS にも流せます（[複数の環境に流す](#複数の環境に流す)）。\
実 AWS での注意です。

- **本物のデータを消さない**。\
  サンプルの後片付けは、行・メッセージ・ファイルをすべて消します。\
  テスト専用のアカウントを使うか、実行ごとに違う名前（`casebook-1a2b3c4d-orders` など）でリソースを作り、最後に丸ごと消してください。\
  確かめるアプリを、テーブル・キュー・バケットの名前を設定や環境変数から受け取る作りにしておくと、テスト用の名前を渡せます
- **`command:` がそのまま使える**。\
  別プロセスからも同じ AWS につながります。\
  `AWS_PROFILE` やリソースの名前は `env:` で渡します
- **非同期の処理は待つ**。\
  S3 に置くと Lambda が動いて DynamoDB に書くような作りでは、実行の直後にはまだ結果がありません。\
  observe の hook で、値がそろうまで数秒おきに読み直します（上限の時間を決めておきます）。\
  SQS は `WaitTimeSeconds` で待って受け取り、DynamoDB は `ConsistentRead=True` で読みます
- **実行ごとに変わる値をそろえる**。\
  メッセージ ID・ETag・日時・ARN の中のアカウント ID などは、`normalize:` か `pytest_casebook_placeholders` で置き換えます。\
  モックと期待出力が違うときは、`-o casebook_golden_dir=golden_real` で実 AWS の期待出力を分けます
- **遅さと並列**。\
  1件に数秒かかることがあるので、`timeout:` を付けます。\
  pytest-xdist（`-n`）で並べると、ワーカーが同じリソースを取り合います。\
  実 AWS の試験は `-n` なしで流すか、ワーカーごとに名前を分けます
- **認証**。\
  手元では SSO かプロファイルを使います。\
  GitHub Actions では、OIDC でテスト用アカウントのロールを引き受け（secrets にアクセスキーを置かない）、テスト用のリソースだけを許可します。\
  実 AWS の試験は、PR ごとではなく、手動か夜間に流すのが向いています

よくある使い分けは、PR ごとには moto で速く何度でも流し、リリースの前や夜間に同じ YAML を実 AWS に流す、というものです。\
実 AWS では、モックでは分からないこと（IAM の権限、実際の Lambda の連携、本物の API の細かい動き）を確かめます。

### カバレッジを測る

[pytest-cov](https://pypi.org/project/pytest-cov/) と一緒に使えます。\
HTML レポートを出しながら、カバレッジも測れます。

```bash
uv add --dev pytest-cov
uv run pytest --cov --casebook-html=reports/casebook.html
```

- `call:` と、テスト用クライアントで送る `request:` は pytest と同じプロセスで動くので、そのまま測れます
- `command:` は別プロセスで動くので、coverage.py の `patch = ["subprocess"]`（coverage.py 7.10 以上）を設定します。\
  別プロセスで動いた Python の分も集めて、まとめて数えます

```toml
[tool.coverage.run]
source = ["myapp"]
patch = ["subprocess"]
```

- 別プロセスは、coverage の入った環境の Python で動かす必要があります。\
  `command_prefix: [python, ...]` のようにパスを含まない名前は PATH から探すので、`uv run pytest` や、仮想環境を有効にした状態で実行すれば、その環境の Python で動きます
- `pytest_casebook_run_command` で `run_in_process` を返して同じプロセスで動かせば、この設定がなくても測れます（[09_in_process](examples/09_in_process)）

### エディタでの補完と検証

YAML の書き方の JSON Schema を、GitHub で公開し、パッケージにも同梱しています（`pytest_casebook.SCHEMA_PATH`）。\
VS Code の YAML 拡張（Red Hat）など yaml-language-server を使うエディタで、キーの補完、カーソルを合わせたときの説明、入力中の検証が効きます。

いちばん簡単なのは、ケースファイルの1行目に次のコメントを書くことです（examples/ のサンプルにも書いてあります）。

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gyuro-dev/pytest-casebook/main/src/pytest_casebook/casebook.schema.json
```

`main` は開発中の最新の版を指します。\
入れた版に合わせるときは、`main` の代わりにその版のタグ `v<版>` を使います（例: 0.7.1 なら `https://raw.githubusercontent.com/gyuro-dev/pytest-casebook/v0.7.1/src/pytest_casebook/casebook.schema.json`）。\
古いタグのスキーマは新しいキーを知らないので、そのキーを誤りとして示します。\
いつも最新のスキーマを使うときは、`main` の URL を使います。

コメントを書かずにすべてのケースファイルに当てるときは、VS Code の設定（settings.json）に書きます。

```json
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/gyuro-dev/pytest-casebook/main/src/pytest_casebook/casebook.schema.json": ["casebook_*.yaml", "*.casebook.yaml"]
  }
}
```

ネットワークにつながらないときは、パッケージに同梱したスキーマを使います（表示された `file:///...` のパスを、URL の代わりに書きます）。

```bash
uv run python -c "import pytest_casebook; print(pytest_casebook.SCHEMA_PATH.as_uri())"
```

失敗したケースは、YAML の何行目に書いたものかを出します（`[wrong]（8 行目）`）。\
pytest がテストの場所として受け取るので、JUnit XML（xunit1）や IDE からもその行へ移動できます。

### コマンドラインのオプション

| オプション | 内容 |
|---|---|
| `--casebook-update` | 期待出力ファイルを、今の出力で書き直す（結果が変わったものだけ。`expect:` のケースは比べるだけ。最後に書き直したファイルの一覧を出す。結果のヘッダーが変わったファイルには `exit_code 0 → 2`、失敗の結果で新しく作ったファイルには `new, exit_code 1` / `new, raises` のような注記が付く） |
| `--casebook-update-headers` | 結果が同じ期待出力ファイルの、ヘッダー（`# case:`・`# description:` など）を書き直し、`--casebook-update` と同じく一覧を出す。結果が違うファイルは失敗する。`--casebook-update` と一緒に付けたときは効かない |
| `--casebook-html=PATH` | 結果を HTML に出力する |

オプションの名前はすべて `--casebook-` で始めています。\
`--update-golden` のような一般的な名前は、プロジェクトの conftest.py がすでに定義していることがあり、同じ名前だと pytest が起動できなくなるためです。

### ini の設定

| 名前 | 既定値 | 内容 |
|---|---|---|
| `casebook_files` | `casebook_*.yaml` `casebook_*.yml` `*.casebook.yaml` `*.casebook.yml` | 集めるファイル名のパターン |
| `casebook_command_prefix` | （なし） | command の前に付ける引数 |
| `casebook_encoding` | `utf-8` | command の出力の文字コード |
| `casebook_golden_dir` | `golden` | 期待出力ファイルの置き場所。その下に、ケースファイル名（拡張子なし）のディレクトリを作る |
| `casebook_golden_description` | `false` | `--casebook-update`・`--casebook-update-headers` が書く期待出力ファイルに、ケースの `description:` を `# description:` の行として書く |
| `casebook_builtin_patterns` | `true` | 日時と UUID を `<datetime>` / `<uuid>` に置き換える |
| `casebook_levels` | `Category` `Subcategory` `Item`（`casebook_lang` が `ja` なら `大項目` `中項目` `小項目`） | 階層の呼び名 |
| `casebook_html_title` | `Test Specification`（`casebook_lang` が `ja` なら `試験項目表`） | HTML レポートの題名。書かないとき、ケースファイルが1つだけの表では、ブラウザのタブの題名にそのファイルの `title:` を使う（例: `お店 - 試験項目表`） |
| `casebook_html_golden` | `summary` | HTML レポートに期待出力ファイルの内容をどれだけ出すか。`off`（出さない）・`summary`（行数を打ち切る）・`full`（全部） |
| `casebook_html_golden_lines` | `40` | `casebook_html_golden` が `summary` のときに出す行数 |
| `casebook_html_reports` | （なし） | 1回の実行で追加で書く HTML の表。1行が `出す HTML = 入れるケースファイルのパターン`（`,` 区切り。グロブ可。rootdir からのパス）。[1回の実行で表を分ける](#1回の実行で表を分ける-casebook_html_reports)を参照 |
| `casebook_lang` | `en` | HTML レポートと、メッセージ（比較の失敗、YAML の書き方の誤り、ケースを実行するときの誤り）の言語。`en` か `ja`。ケースファイルごとに `lang:` で変えられる |

## つまずいたら

最初に引っかかりやすいところです。

- **ケースが集まらない（collected 0 items）** — ファイル名が `casebook_files` のパターン（`casebook_*.yaml`・`casebook_*.yml`・`*.casebook.yaml`・`*.casebook.yml`）に合っていません。\
  `mycases.yaml` のような名前は、黙って無視されます。\
  ファイル名を変えるか、`casebook_files` にパターンを足してください（[ini の設定](#ini-の設定)）
- **Windows で出力が文字化けする** — 確かめるコマンドが cp932 などの文字コードで出力しています。\
  `casebook_encoding` にその文字コードを書いてください（[ini の設定](#ini-の設定)）。\
  子プロセスが Python なら、出力は `PYTHONIOENCODING` で `casebook_encoding` にそろえます
- **Windows の Git Bash や VS Code のターミナルで、pytest の出力が文字化けする**（「書き直した期待出力」のような casebook の日本語のメッセージも） — Python は、パイプやターミナルへの出力をロケールの文字コード（cp932）で書きますが、これらのターミナルは UTF-8 を期待しています。\
  環境変数に `PYTHONUTF8=1`（または `PYTHONIOENCODING=utf-8`）を設定してください。\
  casebook に限った話ではありません（cmd.exe では正しく出ます）
- **`command:` の `\` が消える** — 文字列の command は shell と同じ書き方で区切るため、`\` が消えます。\
  `command: ['C:\data\in.csv']` のようにリストで書きます
- **値に `: ` や ` #` を書いたら YAML が壊れた** — 値全体を `"` で囲みます（`description: "setup: の説明"`）。\
  エディタの検証を使うと、入力中に気づけます（[エディタでの補完と検証](#エディタでの補完と検証)）
- **「期待出力ファイル … がありません」と出る** — 初回は `pytest --casebook-update` で期待出力ファイルを作ります。\
  中身を確かめてから commit してください（[期待出力ファイル](#期待出力ファイル)）
- **レポートやメッセージが英語で出る** — 既定が英語です。\
  ini に `casebook_lang = "ja"` を書いてください（[ini の設定](#ini-の設定)）

## 開発（このリポジトリで作業する人向け）

Python 3.11〜3.15 と pytest 8 / 9 の組み合わせを、同じ手順で確かめるスクリプトがあります。\
依存は uv.lock のとおりに入れ、組み合わせごとに別の仮想環境（`.venvs/`）を作ります。\
結果は `reports/check/summary.txt` に、OS や各ツールの版と一緒に残ります。

```bash
scripts/check.sh                 # 3.11〜3.15 × pytest 8 / 9
scripts/check.sh 3.12            # Python の版を指定する
PYTESTS=9 scripts/check.sh 3.13  # pytest の版も絞る
```

PostgreSQL と API サーバーを Docker で実際に起動して確かめる「実起動の試験」もあります（[integration/](integration)）。\
WSL なら、Docker Engine と uv を入れるスクリプトもあります。

```bash
scripts/integration.sh            # 起動 → 試験 → 片付け（結果は reports/integration/）
```

ふだんの確認は次のとおりです。

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```
