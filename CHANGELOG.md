# 変更履歴

## 0.1.0（未公開）

最初の版。

### できること

- YAML に「前提条件 → 操作 → 期待結果」の形でケースを書き、pytest で実行する
  - 操作: CLI の実行（`command:`）、Python 関数の呼び出し（`call:`、async にも対応）、HTTP の API へのリクエスト（`request:`）
  - 前提条件: `setup:`（`files` は作業ディレクトリに置く。それ以外は `pytest_casebook_setup` hook に渡す）と、名前を付けた前提条件の `states:`
  - 期待結果: YAML の `expect:`、または期待出力ファイル（`--casebook-update` で作る。比べるのは結果だけで、手で書くときはヘッダーを省ける）
  - 実行後の値: `observe:`（DB の行などを1件1行で期待出力に残す）
- グループの入れ子で大項目・中項目・小項目のように分類し、`--casebook-html` で試験項目表の形の HTML を出す（ini の `casebook_lang = en` で、レポートと比較の失敗のメッセージを英語にもできる）
- `expect:` の比べ方: 文字列は完全一致・`{contains}`・`{regex}`、値は書いたキーだけ・`$contains`・`$regex`・`$unordered`・`$includes`
- 実行のたびに変わる値の正規化（日時・UUID は自動。ほかは `normalize:` か hook）
- `skip:` / `xfail:` に理由を書ける。`meta:` に自由な情報を書け、`pytest_casebook.load()` で pytest の外からも YAML を読める
- 失敗したケースの YAML の行番号を出す。YAML の JSON Schema（`pytest_casebook.SCHEMA_PATH`）でエディタの補完と検証が効く
- `command:` のプログラム名（`python` など）は PATH から探す（Windows でも仮想環境の Python で動く）。pytest-cov と一緒に使え、coverage.py の `patch = ["subprocess"]` で別プロセスの分も測れる
- 依存は pytest と PyYAML だけ。HTTP は利用する側のテスト用クライアントで送る（`pytest_casebook.http` にアダプター）
- Python 3.11〜3.15、pytest 8 / 9、pytest-xdist で確かめている（Windows と WSL の Ubuntu 22.04）
- 型の検査（mypy の strict）と ruff（pytest の書き方・pathlib などの規則も含む）で確かめている
