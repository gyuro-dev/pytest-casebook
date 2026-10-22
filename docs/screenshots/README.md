# README のスクリーンショット用のケース

README に載せる HTML レポート（`--casebook-html`）の画像を作るためのケースです。小さなお店の価格・在庫・注文を題材に、大項目・中項目・小項目の表、前提条件と期待結果の列、成功・失敗・スキップ・既知の不具合（xfail）がひと目で分かるようにしています。

| ファイル | 中身 |
|---|---|
| `casebook_demo.yaml` | ケース。失敗・スキップ・既知の不具合を、見せるためにわざと1件ずつ入れている |
| `store.py` | 確かめる対象（CLI と Python の関数） |
| `conftest.py` | CLI を同じプロセスで動かす hook と、在庫の状態を当てる hook |
| `golden/` | 期待出力ファイル。`receipt_free_shipping.txt` は失敗させるため、正しい仕様（送料0円）を手で書いている |

`docs/` は pytest の `testpaths` に入っていないので、ふだんの `uv run pytest` では集めません。

## 画像の作り直し方

Windows の Git Bash で、リポジトリのルートから実行します。Microsoft Edge を使います。

```bash
scripts/screenshots.sh
```

`docs/images/` の次の画像が書き換わります（横幅 1280px、ライトモード）。英語版の README（README.md）の画像（`-en` の付いたもの）は、同じ内容を英語にした [docs/screenshots-en](../screenshots-en) から `casebook_lang=en` で作ります。

- `report-top.png` / `report-top-en.png`: README の冒頭用。題名・件数とケースの表の最初の7件だけ（縦に短い）
- `report-overview.png` / `report-overview-en.png`: 表の全体
- `report-failure.png` / `report-failure-en.png`: 失敗の詳細を開いたところ（色の付いた差分）

途中の HTML は `reports/screenshots/` に残ります。ケースを増やして表が長くなったら、`scripts/screenshots.sh` の最後にある高さを直してください。

`--casebook-update` は付けないでください。失敗させているケースの期待出力ファイルが、今の出力で書き換わってしまいます。
