# 実起動の試験

PostgreSQL と API サーバーを Docker で実際に起動し、pytest-casebook のケース（HTTP・CLI・関数 ＋ 実際の DB）を実行します。インメモリの DB やテスト用クライアントではなく、本物のサーバーとネットワークで動くことを確かめるためのものです。

| 動かすもの | 中身 |
|---|---|
| `db` | PostgreSQL 17.6（`db/init.sql` で todos テーブルを作る） |
| `api` | FastAPI + uvicorn の TODO API（`api/`。依存の版は `api/requirements.txt` で固定） |
| CLI | `todo_cli.py`（コンテナではなく、pytest を動かす側で別プロセスとして起動する。PostgreSQL に直接読み書きする） |

| ケースのファイル | 確かめること |
|---|---|
| `casebook_api.yaml` | `request:` で本物の HTTP を送り、ステータス・JSON と、実行後の DB（`db.todos`）を確かめる |
| `casebook_cli_db.yaml` | `command:` で CLI を動かし、出力と DB を確かめる。`call:` で DB を読む関数も確かめる |

`conftest.py` は、ケースの前にテーブルを空にして `setup:` の行を入れ、終わったらまた空にします。

## 実行のしかた（WSL）

```bash
# 1回だけ: Docker Engine と uv を入れる（Windows の PowerShell から）
wsl -d Ubuntu -u root -- bash scripts/wsl/setup-docker.sh <WSL のユーザー名>

# WSL の中に clone して実行する（Windows のディレクトリで直接動かすと遅い）
git clone <このリポジトリ> ~/pytest-casebook && cd ~/pytest-casebook
scripts/integration.sh
```

`scripts/integration.sh` は、起動 → 起動を待つ（healthcheck）→ 試験 → 片付け（`docker compose down -v`）までを行います。結果は `reports/integration/` に残ります。

| 書き方 | 内容 |
|---|---|
| `scripts/integration.sh` | 起動して試験し、片付ける |
| `KEEP=1 scripts/integration.sh` | 終わってもコンテナを残す（調べるとき） |
| `UPDATE=1 scripts/integration.sh` | 期待出力ファイル（`golden/`）を作り直す |
| `CASEBOOK_DB_PORT=… CASEBOOK_API_PORT=…` | ホスト側のポートを決める（指定しなければ空いているポートを選ぶ） |

接続先（`CASEBOOK_DB_URL` / `CASEBOOK_API_URL`）がないときは、このディレクトリのケースを集めません。ふだんの `uv run pytest` には影響しません。

