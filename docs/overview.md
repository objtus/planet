# Planet — LLMへの申し送り概要

このドキュメントはLLMが作業を引き継ぐ際に最初に読むファイルです。
詳細は `docs/design.md` を参照してください。

---

## プロジェクトの一言説明

個人のSNS投稿・音楽再生履歴・ヘルスデータ等を自動収集してPostgreSQLに蓄積し、
OllamaでAIサマリーを生成、Neocitiesの個人サイトに自動公開するライフログシステム。

---

## 技術スタック

| 役割 | 技術 |
|---|---|
| サーバーOS | Ubuntu（自宅）|
| 外部アクセス | Tailscale |
| DB | PostgreSQL + pg_bigm |
| バックエンド | Python / Flask |
| AI | Ollama（gemma3:12b）|
| 自動実行 | cron |
| バックアップ | pg_dump + rclone + pCloud |
| 公開先 | Neocities API |

---

## データソース（現在登録済み）

- Misskey: misskey.io @yuinoid / tanoshii.site @health
- Mastodon: mistodon.cloud @healthcare
- Last.fm: objtus
- 個人サイト RSS: yuinoid.neocities.org/rss.xml
- YouTube: 投稿動画
- OpenWeatherMap: 天気
- GitHub: 開発活動
- iPhone: 歩数・カロリー・心拍数・運動/スタンド / 写真メタデータ

---

## DBの核心設計

- `data_sources` テーブルでソースを管理（ここに1行追加するだけでソース追加）
- `logs` テーブルが全ソース共通の統合タイムライン（AI受け渡し・表示用）
- ソース別テーブル（misskey_posts等）は統計・詳細用
- 書き込みはトランザクションで両テーブルに同時保存
- タイムスタンプは全てUTC保存・表示時にJST変換

---

## ディレクトリ構成（簡略）

```
planet/
├── config/settings.toml     # APIキー等（gitignore対象）
├── collectors/              # 各ソースの収集スクリプト
├── importers/               # 過去JSONの一括インポート
├── summarizer/              # Ollamaサマリー生成
├── publisher/               # Neocities公開スクリプト
├── dashboard/               # Flaskダッシュボード
├── ingest/                  # iPhoneからのデータ受け取りAPI
├── backup/                  # バックアップスクリプト
└── docs/                    # ドキュメント群
```

---

## 現在の状態

→ `docs/current_state.md` を参照

## 次のタスク

→ `docs/next_tasks.md` を参照
