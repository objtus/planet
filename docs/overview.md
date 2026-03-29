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

- Misskey: misskey.io @yuinoid / tanoshii.site @health / misskey.io @vknsq / msk.ilnk.info @google / sushi.ski @idoko
- Mastodon: mistodon.cloud @healthcare / mastodon.cloud @objtus
- Last.fm: objtus
- 個人サイト RSS: yuinoid.neocities.org/rss.xml
- YouTube: 投稿動画（APIキー未取得・収集待ち）
- OpenWeatherMap: 天気（取得地点は `config/settings.toml` で名古屋。過去分は Open-Meteo バックフィル可）
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

## ダッシュボード（Phase 5 実装済み）

- URL: `http://<tailscale-ip>:5000`（`planet-dashboard.service` で起動）
- 画面: カレンダー / 検索 / サマリー / 統計 / ソース管理
- 月カレンダー形式のヒートマップ（投稿数を青の濃淡で表現）。前後月の日付も薄く表示
- 日・週・月・年の切り替えによるタイムライン表示。見出し日付は表示中タイムラインと一致（カレンダー月送りのみでは変わらない）
- カレンダー右上から現在表示月・年のタイムラインへジャンプ可能
- 画像ライトボックス、統計は月別/年別グラフ切替・Chart.js は静的ファイル配信
- ソース管理: 表示順・略称・個別/一括の手動収集（`POST /api/collect/<stype>`）
- ソースフィルター（アカウント単位でオン/オフ）
- CSS変数ベース（ライトテーマ・ダークモード自動切替）
- `ingest/api.py` を統合済み（iPhone ショートカットからも引き続き利用可能）

---

## ディレクトリ構成（簡略）

```
planet/
├── config/settings.toml     # APIキー等（gitignore対象）
├── collectors/              # 各ソースの収集スクリプト
├── importers/               # 過去JSONの一括インポート
├── ingest/                  # iPhoneからのデータ受け取り API（Blueprint）
├── dashboard/               # Flaskダッシュボード（メインアプリ）
│   ├── app.py
│   ├── static/css/dashboard.css
│   ├── static/js/calendar.js
│   ├── static/js/chart.umd.min.js
│   └── templates/
├── mockup/                  # UI デザインモックアップ
├── summarizer/              # Ollama サマリー（週・月 CLI → `generate --period week|month`）
├── publisher/               # Neocities公開スクリプト（未実装）
├── backup/                  # バックアップスクリプト（未実装）
└── docs/                    # ドキュメント群
```

---

## 現在の状態・次のタスク

→ `docs/current_state.md` を参照

Phase 6（AI 生成・Neocities）の実装手順 → **`docs/phase6_plan.md`**
