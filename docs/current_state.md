# 現在の実装状況

**最終更新**: 2026-03-29

---

## フェーズ状況

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | 基盤構築 | 完了 |
| 2 | 過去データインポート | 完了 |
| 3 | 自動収集 | 完了 |
| 4 | iPhone連携 | 完了 |
| 5 | ダッシュボード | 完了 |
| 6 | AI生成・公開 | **着手中**（M1週次・M2月次 完了） |
| 7 | 自動化・バックアップ | 未着手 |

---

## 完了フェーズ（Phase 1〜5）

### Phase 1: 基盤構築
PostgreSQL 16.13 + pg_bigm、全11テーブル（data_sources / logs / misskey_posts / mastodon_posts / lastfm_plays / youtube_videos / weather_daily / github_activity / health_daily / rss_entries / summaries 等）、14ソース初期投入、Python venv、settings.toml。

### Phase 2: 過去データインポート
Misskey（msk.ilnk.info / pon.icu archived / tanoshii.site / misskey.io @vknsq 他）、Mastodon（mastodon.cloud @objtus 12,383投稿 / groundpolis archived 7,879投稿 他）、logs 合計 36,175 件（2025年12月末まで）。

### Phase 3: 自動収集
`collectors/`（misskey / mastodon / lastfm / weather / github / rss）、`collect_all.py`、cron 登録済み（`cron/crontab.txt`）。

### Phase 4: iPhone連携
`ingest/api.py`（Flask Blueprint → dashboard 統合）、ヘルス・写真メタデータ受信、iPhoneショートカット動作確認済み（詳細: `docs/iphone_shortcuts.md`）。

### Phase 5: ダッシュボード

主要機能（`dashboard/app.py`、`planet-dashboard.service` で稼働中）:

- **カレンダー**: 月グリッド・ヒートマップ（posts/plays/steps/weather）・週番号・今日・月年ジャンプ
- **タイムライン**: 日/週/月/年ビュー・新着順・メディア添付・ライトボックス・ソースフィルター・バッジ
- **サマリーパネル**: 週/月/日ビューで `GET /api/summary`、年ビューで月次一覧。「この期間で生成」ボタン
- **統計**: Chart.js（ローカル）・月別/年別切替
- **ソース管理**: 表示順・略称・今すぐ収集（`POST /api/collect/<stype>`）
- **`/summaries`**: 公開トグル（`PATCH /api/summaries/<id>/publish`）、週行から7日リンク
- **DB拡張**: `data_sources` に `sort_order` / `short_name` 追加（`db/migrate_sort_shortname.sql`）

---

## 進行中：Phase 6（AI生成・公開）

詳細・マイルストーン手順: **`docs/phase6_plan.md`**

### 完了（M1・M2）

- **M1（週次）**: `./venv/bin/python -m summarizer.generate --period week --date YYYY-Www`
  - `--pipeline hierarchical`（**既定**）: 日次×7回 → 週マージ。日次を `summaries` に保存・再利用
  - `--pipeline flat`: 生ログ一括（比較・フォールバック用）
  - `--regenerate-daily`: 既存日次を強制再生成
- **M2（月次）**: `./venv/bin/python -m summarizer.generate --period month --date YYYY-MM`
  - 月ログ上限 8000 件。`summarizer/month_bounds.py`、`prompts/monthly_hybrid.txt`

### 未着手（M3〜M6）

- **M3**: 過去分一括生成バッチ（`summarizer/batch_backfill.py`）
- **M4**: Neocities 週次 HTML アップロード（`publisher/`）
- **M5**: Planet ページ生成（`publisher/build.py` + `templates/planet.html`）
- **M6**: cron 自動実行（最小追記）

### 並行作業：Scrapbox（Cosense）日記の追加

stallプロジェクトの日記を収集し、日次サマリーの文脈補完に使う。
仕様: `docs/api/scrapbox.md`

| タスク | 内容 |
|---|---|
| `db/migrate_scrapbox.sql` | `scrapbox_pages` テーブル作成 + `data_sources` 1行追加 |
| `config/settings.toml` | `[scrapbox]` ブロックを手動追記 |
| `config/settings.toml.example` | `[scrapbox]` のダミー値を追加 |
| `collectors/scrapbox.py` | 収集スクリプト実装 |
| `cron/crontab.txt` | 毎日 AM 6:00 に追記 |
| `summarizer/context.py` | `fetch_scrapbox_diary` 追加・日次 digest に統合 |

---

## 未着手：Phase 7（自動化・バックアップ）

1. cron 整理（全ジョブ統合）
2. `backup/backup.sh` — `pg_dump` → gzip → rclone → pCloud（毎週日曜 AM 3:00）
3. エラーログ整備

---

## バックログ（低優先・アイデア）

- ソース管理: 新規追加フォーム（種別でフィールド切替・接続テスト）
- 年全体カレンダー一覧（12ヶ月同時表示）
- 検索の高速化（`pg_bigm` + GIN を活かす書き方）
- YouTube Data API v3 取得 → `collectors/youtube.py` 有効化
- mastodon.cloud @objtus 収集不調の原因調査
- 画像ローカル保存（収集時非同期ダウンロード → `media/YYYY/MM/`、DB に `metadata["media"][].local_path`）

---

## 既知の問題・注意事項

- ソース管理の「今すぐ収集」APIは `POST /api/collect/<stype>` のパスパラメータ方式（Tailscale + iOS Safari の `Failed to fetch` 回避）
- `data_sources` マイグレーションはテーブル所有者権限が必要。`/tmp` にコピーして `psql -f` する
- pon.icu / groundpolis.app は閉鎖済み個人インスタンス。`is_active=False`、favicon 絵文字フォールバック
- YouTube 収集スクリプトは後回し（APIキー未取得）
- mastodon.cloud @objtus の収集が不調（原因未調査）

---

## APIキー取得状況

- [x] Last.fm / OpenWeatherMap / GitHub PAT / Neocities
- [x] Misskey: misskey.io @yuinoid / tanoshii.site @health / misskey.io @vknsq / msk.ilnk.info @google / sushi.ski @idoko
- [x] Mastodon: mistodon.cloud @healthcare / mastodon.cloud @objtus
- [ ] YouTube Data API v3（後回し）

---

## 環境情報

- Ubuntu 24.04（自宅サーバー）
- Python 3.12.3 / PostgreSQL 16.13 + pg_bigm v1.2-20250903
- Tailscale インストール済み
- Ollama + Open WebUI インストール済み
- 仮想環境: `/home/objtus/planet/venv`
- 稼働サービス: `planet-dashboard.service`（ポート 5000）

---

## ディレクトリ構成（現在）

```
planet/
├── config/settings.toml
├── collectors/
│   ├── base.py
│   ├── misskey.py / mastodon.py / lastfm.py
│   ├── weather.py / github.py / rss.py / youtube.py
│   ├── scrapbox.py                 # 未実装
│   └── ogp_worker.py
├── importers/
│   ├── misskey_json.py
│   └── mastodon_json.py
├── ingest/
│   └── api.py                  # Flask Blueprint（dashboard に統合済み）
├── summarizer/
│   ├── generate.py             # 週次・月次・日次 CLI
│   ├── db.py / context.py / week_bounds.py / month_bounds.py / ollama_client.py
│   └── prompts/
│       ├── weekly_hybrid.txt
│       ├── weekly_from_dailies.txt
│       ├── daily_hybrid.txt
│       └── monthly_hybrid.txt
├── publisher/                  # 未実装（Phase 6 M4〜M5）
├── dashboard/
│   ├── app.py
│   ├── planet-dashboard.service
│   ├── static/css/dashboard.css
│   ├── static/js/calendar.js / chart.umd.min.js
│   └── templates/
│       ├── base.html / calendar.html / search.html
│       ├── summaries.html / stats.html / sources.html / timeline.html
├── db/
│   ├── backfill_media.py / backfill_weather.py
│   └── migrate_sort_shortname.sql / .py
├── mockup/calender_v3.html
├── docs/
│   ├── overview.md / current_state.md（このファイル）
│   ├── design.md / decisions.md / dashboard_ui.md
│   ├── phase6_plan.md
│   ├── summary_daily_and_dashboard.md
│   ├── importers.md / iphone_shortcuts.md / setup.md
│   └── api/（lastfm / mastodon / misskey / github / neocities / openweathermap / youtube）
└── cron/crontab.txt
```

---

## data_sources テーブル（現在）

`sort_order`（表示順）・`short_name`（略称、NULL 可）を含む。

| id | name | type |
|---|---|---|
| 1 | misskey.io @yuinoid | misskey |
| 2 | tanoshii.site @health | misskey |
| 3 | mistodon.cloud @healthcare | mastodon |
| 4 | Last.fm objtus | lastfm |
| 5 | yuinoid.neocities.org RSS | rss |
| 6 | YouTube | youtube |
| 7 | OpenWeatherMap | weather |
| 8 | GitHub | github |
| 9 | iPhone ヘルス | health |
| 10 | iPhone 写真 | photo |
| 11 | misskey.io @vknsq | misskey |
| 12 | msk.ilnk.info @google | misskey |
| 13 | sushi.ski @idoko | misskey |
| 14 | mastodon.cloud @objtus | mastodon |
| 15 | Cosense stall | scrapbox |（追加予定）|

---

## LLMへの渡し方

**最初に読む**: `docs/overview.md` → このファイル

**Phase 6 実装時**: `docs/phase6_plan.md` → `docs/design.md` §7–8 → 日次要約は `docs/summary_daily_and_dashboard.md`

**必要に応じて**: `docs/dashboard_ui.md` / `docs/iphone_shortcuts.md` / `docs/importers.md` / `docs/api/*.md`
