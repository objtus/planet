# Planet MCP セットアップ

Hermes Agent から Planet の PostgreSQL データ（投稿検索・タイムライン・統計・AI サマリー）を参照するための MCP サーバー。

## アーキテクチャ

```
Hermes WebUI (Docker)
    → http://172.20.0.1:9311/mcp
        → mcp-proxy (ホスト systemd)
            → planet_mcp.server (stdio, FastMCP)
                → PostgreSQL localhost:5432
```

Hermes CLI（ホスト）も同じ HTTP URL または stdio 設定で利用可能。

## 前提

- Planet DB が稼働（`config/settings.toml`）
- `pip install -r requirements-mcp.txt`（`planet/venv`）
- `mcp-proxy` がホストにインストール済み（`uv tool install mcp-proxy` 等）

## 1. MCP 依存関係

```bash
cd ~/planet
source venv/bin/activate
pip install -r requirements-mcp.txt
```

## 2. systemd（mcp-proxy）

`~/.config/systemd/user/mcp-proxy-planet.service` が Planet 用 proxy を `:9311` で起動する。

```bash
systemctl --user daemon-reload
systemctl --user enable --now mcp-proxy-planet.service
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9311/sse   # 200
```

## 3. Docker → ホスト ファイアウォール（WebUI 利用時必須）

Hermes WebUI コンテナから `172.20.0.1:9311` へ到達するには iptables ルールが必要（コンテナ→ホストは **INPUT** チェーン）。スクリプトは FORWARD / INPUT 両方に追加する。

```bash
sudo ~/planet/scripts/mcp-firewall-docker.sh 9311
```

**9310 は通るが 9311 がタイムアウトする**場合: 上記を再実行（INPUT ルール追加版）。古いスクリプトは FORWARD のみだった。

検証:

```bash
docker exec hermes-webui-hermes-webui-1 python3 -c \
  "import socket; s=socket.create_connection(('172.20.0.1',9311),3); print('OK')"
```

## 4. Hermes 設定

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  planet:
    url: http://172.20.0.1:9311/mcp
    enabled: true
    tools:
      include:
        - list_sources
        - search_posts
        - get_timeline
        - get_stats
        - get_activity_digest
        - get_summaries
```

**CLI（stdio）** を使う場合:

```yaml
  planet:
    command: /home/objtus/planet/venv/bin/python
    args: ["-m", "planet_mcp.server"]
    env:
      PYTHONPATH: /home/objtus/planet
    enabled: true
```

WebUI 再起動後、Settings → MCP Servers に 6 ツールが表示される。

## 5. 読取専用 DB ユーザー（推奨）

```bash
# パスワードを編集してから
sudo -u postgres psql -d planet -f ~/planet/db/migrate_planet_mcp_user.sql
```

`config/settings.toml` に `[database_mcp]` を追加（`settings.toml.example` 参照）。

## MCP ツール一覧

| ツール | 説明 |
|---|---|
| `list_sources` | 全 data_sources 一覧 |
| `search_posts` | キーワード検索（LIKE、最大 200 件） |
| `get_timeline` | 日/週/月タイムライン |
| `get_stats` | 投稿数・Last.fm・歩数・天気 |
| `get_activity_digest` | 1 日分 digest（任意 topic） |
| `get_summaries` | AI サマリー（topics） |

## 使用例（Hermes チャット）

- 「2026-05-11 のタイムラインを教えて」
- 「ツイッタ で投稿を検索して」
- 「2026-05-11 の SNS digest を取得して」
- 「2026-05-11 の統計を教えて」

## 手動テスト（クエリ層）

```bash
cd ~/planet
PYTHONPATH=. ./venv/bin/python -c "
from planet_mcp.queries import get_timeline, get_stats
print(get_timeline('day', '2026-05-11')['count'])
print(get_stats('day', '2026-05-11')['plays'])
"
```

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `systemctl --user status mcp-proxy-planet` が失敗 | `journalctl --user -u mcp-proxy-planet -n 30`。`PYTHONPATH` が subprocess に渡っているか確認 |
| Docker から 9311 タイムアウト | `sudo scripts/mcp-firewall-docker.sh 9311` |
| WebUI で MCP 405 | Hermes の URL は `/mcp` を使う（`/sse` では POST が 405）。`hermes mcp test planet` で確認 |
| `ModuleNotFoundError: planet_mcp` | `PYTHONPATH=/home/objtus/planet` を設定 |

## 関連ファイル

- [`planet_mcp/server.py`](../planet_mcp/server.py) — FastMCP エントリ
- [`planet_mcp/queries.py`](../planet_mcp/queries.py) — SQL クエリ
- [`scripts/mcp-firewall-docker.sh`](../scripts/mcp-firewall-docker.sh) — iptables ヘルパー
- [`db/migrate_planet_mcp_user.sql`](../db/migrate_planet_mcp_user.sql) — 読取専用ユーザー
