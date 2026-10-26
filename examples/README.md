# サンプル

やりたいことごとに、そのまま動くサンプルを置いています。それぞれのディレクトリの YAML の先頭に、何を確かめるサンプルかと、実行のしかたを書いています。

| ディレクトリ | やりたいこと | 作るもの |
|---|---|---|
| [01_cli](01_cli) | CLI を実行して、出力を確かめる | YAML |
| [02_function](02_function) | Python の関数を呼んで、戻り値を確かめる | YAML |
| [03_exception](03_exception) | 例外になることを確かめる（親クラスの名前やメッセージでも） | YAML |
| [04_expect](04_expect) | 期待結果を YAML に直接書く（完全一致・含む・正規表現・書いたキーだけ） | YAML |
| [05_groups](05_groups) | ケースを大項目・中項目・小項目に分け、HTML の表で見る | YAML |
| [06_files](06_files) | 入力ファイルを置いてから実行し、できたファイルを確かめる | YAML |
| [07_states](07_states) | 同じ操作を「通常時」「メンテナンス中」などの状態で確かめる | YAML ＋ conftest.py |
| [08_db](08_db) | DB に行を入れてから実行し、実行後の DB を確かめる | YAML ＋ conftest.py |
| [09_in_process](09_in_process) | CLI を同じプロセスで動かして、モックを渡す | YAML ＋ conftest.py |
| [10_normalize](10_normalize) | 実行のたびに変わる ID・日時・UUID をそろえる | YAML |
| [11_meta_load](11_meta_load) | ケースに自分用の情報を付け、同じ YAML を pytest の外でも使う | YAML ＋ Python |
| [12_handwritten_golden](12_handwritten_golden) | 期待出力ファイルを手で書く（ヘッダーなし） | YAML ＋ 期待出力ファイル |
| [13_skip_xfail](13_skip_xfail) | 理由を付けてケースを止める / 既知の不具合を書いておく | YAML |
| [14_http_hook](14_http_hook) | HTTP の API を確かめる（フレームワークなしの最小の例） | YAML ＋ conftest.py |
| [15_fastapi](15_fastapi) | FastAPI の API と DB を確かめる | YAML ＋ conftest.py |
| [16_flask](16_flask) | Flask の API と DB を確かめる | YAML ＋ conftest.py |
| [17_targets](17_targets) | 同じケースを別々の環境に流し、期待出力を環境ごとに分ける | YAML ＋ conftest.py |
| [18_manual](18_manual) | 自動にできない確認（目視・帳票など）も同じ表に載せ、結果を手で書く | YAML |
| [19_aws](19_aws) | S3・DynamoDB に入力を置いて実行し、DynamoDB・SQS・S3 の中身を確かめる（moto のモック） | YAML ＋ conftest.py |
| [20_params](20_params) | 引数だけ違うケースを params で表の形に並べる | YAML |
| [shop](shop) | コマンド・関数・例外・ファイル・DB・状態を、1つの小さなお店のアプリで組み合わせた例（3階層のグループ。期待出力ファイルと `expect:` を並べています） | YAML ＋ conftest.py |

## 実行のしかた

リポジトリのルートで実行します。

```bash
uv run pytest examples
```

1つのサンプルだけを実行するときは、ディレクトリを指定します。

```bash
uv run pytest examples/08_db
```

結果を HTML の表で見るときは、`--casebook-html` を付けます。

```bash
uv run pytest examples -o casebook_lang=ja --casebook-html=reports/examples.html
```

期待出力ファイル（`golden/`）を作り直すときは、`--casebook-update` を付けます。

```bash
uv run pytest examples --casebook-update
```

15_fastapi・16_flask・19_aws は、FastAPI / Flask / moto が入っているときだけ実行します（入っていなければ集めません）。このリポジトリでは開発用の依存（`uv sync` で入る）に含めています。pytest-casebook 自身の依存ではありません。

## 自分のプロジェクトで使うとき

サンプルのディレクトリを自分のプロジェクトの `tests/` の下にコピーして、YAML のケースと、確かめたいモジュールの名前を書き換えます。`golden/` は消してから `--casebook-update` で作り直してください。
