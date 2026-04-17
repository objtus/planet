# 現在の実装状況

**最終更新**: 2026-04-18

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
`collectors/`（misskey / mastodon / lastfm / weather / github / rss / scrapbox）、`collect_all.py`（scrapbox 含む）、cron 登録済み（`cron/crontab.txt`）。

**リファクタリング済み（2026-03-29）**: `collect_all.py` をレジストリ駆動ループに整理（72行→53行）。`COLLECTORS` 辞書でコレクター名→クラスを管理、`GROUPS` でエイリアス（sns等）を定義。新コレクター追加は1行で済む。

### Phase 4: iPhone連携
`ingest/api.py`（Flask Blueprint → **`dashboard` に統合**、`POST /api/ingest`）、ヘルス・写真メタ・Jomo スクリーンタイム受信（手順・JSON 仕様: `docs/iphone_shortcuts.md`）。

**2026-04 追補（ingest）**: ヘルスは任意の **`health_segment`**（`movement` / `activity`）で同日に `logs` を2行に分割可能。手動の過去日投入は **`archive`**（真相当）で `logs.timestamp` を当該暦日の JST 23:49/23:50 に固定し、日タイムライン上の表示日と一致させる。写真は **`photo_json` 要素数**を `health_daily.photo_count` と **`logs` 本文の枚数**の両方に反映。**コード更新後は `planet-dashboard.service` の再起動が必要**。

### Phase 5: ダッシュボード

主要機能（`dashboard/app.py`、`planet-dashboard.service` で稼働中）:

- **カレンダー**: 月グリッド・ヒートマップ（posts/plays/steps/weather）・週番号・今日・月年ジャンプ
- **タイムライン**: 日/週/月/年ビュー・新着順・メディア添付・ライトボックス・ソースフィルター・バッジ・**Last.fm 行の「削除」（`POST /api/logs/<id>/soft-delete`、ソフト削除）**・時刻は `url` あればソース先へのリンク（メタ行で削除ボタンは右寄せ）
- **検索（`/search`）**: 同上キーワード検索。結果の日時は **カレンダー日ビュー**へのリンク（JST の `date_jst`）。Last.fm は **検索結果からも** 同じソフト削除 API・確認ダイアログ後に再表示
- **サマリーパネル**: 週/月/日ビューでトピック別サマリー（`GET /api/summary/topics`）、oneword バッジ・full・各トピックをアコーディオン表示。週次は best_post カード付き。「この期間で生成」ボタン＋**強制再生成ボタン**（確認ダイアログ付き）
- **プロンプト管理 (`/prompts`)**: プロンプトファイル一覧・編集・保存（`GET/POST /api/prompts/<name>`）
- **設定 (`/settings`)**: Ollama host/model・サマライザー設定の閲覧と変更（`GET/POST /api/settings`）
- **統計**: Chart.js（ローカル）・月別/年別切替
- **ソース管理**: 表示順・略称・今すぐ収集（`POST /api/collect/<stype>`、misskey〜youtube に加え **scrapbox**）
- **`/summaries`**: 公開トグル（`PATCH /api/summaries/<id>/publish`）、週行から7日リンク
- **DB拡張**: `data_sources` に `sort_order` / `short_name` 追加（`db/migrate_sort_shortname.sql`）

---

## 進行中：Phase 6（AI生成・公開）

詳細・マイルストーン手順: **`docs/phase6_plan.md`**

### 完了（M1・M2・サマライザー品質向上）

- **M1（週次）**: `./venv/bin/python -m summarizer.generate --period week --date YYYY-Www`
- **M2（月次）**: `./venv/bin/python -m summarizer.generate --period month --date YYYY-MM`
  - 月ログ上限 8000 件。`summarizer/month_bounds.py`、`prompts/monthly_hybrid.txt`

**リファクタリング済み（2026-03-29）**: `generate.py` のテンプレート読込を `_load_template(name)` 1関数に統合。

### サマライザー品質向上（2026-04 実装済み）

詳細設計: `docs/summarizer_quality_plan.md`、仕様: `docs/summary_daily_and_dashboard.md`

#### トピック別パイプライン（新規・既定）

日次生成を **7トピック** に分割して個別 LLM 呼び出し：

| トピック | `summary_type` | 入力ソース |
|---|---|---|
| 音楽 | `music` | `lastfm`（直接クエリ）＋ SNS（音楽関連フィルタ） |
| メディア | `media` | `netflix`、`prime`、SNS（視聴・作品言及フィルタ） |
| 健康 | `health` | `health`、`photo`、`screen_time` |
| SNS | `sns` | `misskey`、`mastodon` |
| 開発 | `dev` | `github` |
| 行動傾向 | `behavior` | （補助トピック、`full` 生成の文脈補完用） |
| 日記まとめ | `full` | 上記全トピックの日次サマリーを統合 |
| 一言 | `oneword` | `full` をもとに一言要約 |
| ベスト投稿 | `best_post` | 週次のみ。週の生 SNS ログ → LLM が ID 選定 → DB から実文取得 |

CLIオプション:
- `--period day --date YYYY-MM-DD`: 日次トピック全件生成
- `--period week --date YYYY-Www`: 週次（各日の daily を再利用 → best_post を追加）
- `--period month --date YYYY-MM`: 月次
- `--regenerate-daily`: 既存日次キャッシュを無視して再生成
- `--legacy`: 旧 hierarchical パイプライン（互換維持用）
- `--dry-run`: LLM 呼び出しを省略し入力内容を標準出力

#### 新規プロンプト（`summarizer/prompts/`）

| ファイル | 用途 |
|---|---|
| `daily_music.txt` | 音楽トピック日次 |
| `daily_media.txt` | メディアトピック日次 |
| `daily_health.txt` | 健康トピック日次 |
| `daily_sns.txt` | SNS トピック日次 |
| `daily_dev.txt` | 開発トピック日次 |
| `daily_behavior.txt` | 行動傾向（full 生成用補助） |
| `daily_full.txt` | 日記まとめ（`{{DAY_LABEL}}` 含む） |
| `topic_summary.txt` | 週次トピック集約 |
| `period_full.txt` | 週次/月次 full |
| `oneword.txt` | 一言要約 |
| `best_post.txt` | ベスト投稿選定（`BEST_ID` / `REASON` 形式） |

#### DB変更（`summaries` テーブル）

`summary_type TEXT NOT NULL DEFAULT 'full'` カラム追加。UNIQUE 制約を `(period_type, period_start, summary_type)` に変更。マイグレーション: `db/migrate_summary_type.sql`（テーブル所有者 `postgres` で実行が必要）。

#### ソース名マッピング（`context.get_source_name_map`）

LLM への入力行でソース ID（数値）ではなく人間可読名（`(tanoshii.site @health)` 等）を付与。SNS/music/media トピックに適用。

#### Last.fm 直接クエリ（`context.fetch_lastfm_digest_for_day`）

`lastfm_plays` テーブルの `artist`/`track`/`album` カラムを直接取得し `[HH:MM] Artist - Track (Album)` 形式に整形。YouTube スクロブルのチャンネル名混入を回避。

#### ダッシュボード追加機能

| 機能 | エンドポイント/ファイル |
|---|---|
| トピック別サマリー表示（日次・週次・月次） | `GET /api/summary/topics?period=day&date=YYYY-MM-DD` |
| アコーディオン UI（oneword バッジ・full・各トピック） | `calendar.js` |
| ベスト投稿カード（週次） | `calendar.js` + CSS `.summary-best-post-card` |
| 強制再生成ボタン | `calendar.html` + `calendar.js`（確認ダイアログ付き） |
| プロンプト編集 UI | `GET/POST /api/prompts/<name>`、`/prompts` ページ |
| 設定 UI（Ollama・サマライザー） | `GET/POST /api/settings`、`/settings` ページ |

### 未着手（M3〜M6）

- **M3**: 過去分一括生成バッチ（`summarizer/batch_backfill.py`）
- **M4**: 雑記向け Neocities 週次 HTML アップロード（`publisher/`）
- **M5**: Planet ページ公開 — **JSON 生成（build_feed）✅** / **Neocities クライアント ✅**
- **M6**: cron 自動実行（最小追記）

### Planet ページ・planet-feed（実装の順序）

1. **サーバー側（本リポジトリ）**: ✅ `publisher/build_feed.py` 実装済み。過去30日分（JST・`--days` で変更可）の `planet-meta.json` / `planet-data.json` を `~/planet-feed/` に書き出し、差分があれば git **1 コミット**で push → `data.idoko.org`。手順・仕様は **`docs/planet_feed_setup.md`**。
2. **クライアント**: `neocities/planet/` を Neocities の `/planet/` にアップロードし、`planet-meta.json` / `planet-data.json` を `fetch` して描画。手順・アイコンは **`neocities/planet/README.md`**。モックは **`mockup/neocities_planet_mockup.html`**（参照用）。

`docs/phase6_plan.md` にある `publisher/build.py` + `templates/planet.html` 案は、feed（JSON）方式を採用する場合は **build_feed + 静的クライアント**が実体となり、必要ならドキュメント側を後続で整合させる。

### 並行作業：Scrapbox（Cosense）日記の追加

stallプロジェクトの日記を収集し、日次サマリーの文脈補完に使う。
仕様: `docs/api/scrapbox.md`

全タスク完了。

### Netflix / Amazon Prime 視聴履歴（CSV インポート）

- **状態**: 実装済み（`importers/streaming_csv.py`、`db/migrate_streaming_views.sql`）。
- **手順**: `docs/importers.md` の「Netflix / Amazon Prime Video（CSV）」を参照。
- **入力例**: `~/planet-data/exports/NetflixViewingHistory.csv`、`watch-history-export-*.csv`。
  - **補足**: CSVによっては日時にタイムゾーン表記が無く、視聴時刻がズレる場合がある。`config/settings.toml` の `[streaming_import]`（`netflix_activity_tz` / `prime_tz` 等）で解釈TZを調整（詳細は `docs/importers.md`）。

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
│   ├── scrapbox.py
│   └── ogp_worker.py
├── importers/
│   ├── misskey_json.py
│   ├── mastodon_json.py
│   └── streaming_csv.py   # Netflix / Prime Video CSV
├── ingest/
│   └── api.py                  # Flask Blueprint（dashboard に統合済み）
├── summarizer/
│   ├── generate.py             # 週次・月次・日次 CLI（トピック別パイプライン）
│   ├── db.py / context.py / week_bounds.py / month_bounds.py / ollama_client.py
│   └── prompts/
│       ├── daily_music.txt / daily_media.txt / daily_health.txt
│       ├── daily_sns.txt / daily_dev.txt / daily_behavior.txt
│       ├── daily_full.txt / topic_summary.txt / period_full.txt
│       ├── oneword.txt / best_post.txt
│       ├── weekly_hybrid.txt / weekly_from_dailies.txt
│       ├── daily_hybrid.txt / monthly_hybrid.txt  ← 旧pipeline用（--legacy）
├── publisher/                  # build_feed.py（planet-feed JSON）／雑記 HTML（M4）は今後
├── dashboard/
│   ├── app.py
│   ├── planet-dashboard.service
│   ├── static/css/dashboard.css
│   ├── static/js/calendar.js / chart.umd.min.js
│   └── templates/
│       ├── base.html / calendar.html / search.html
│       ├── summaries.html / stats.html / sources.html / timeline.html
│       ├── prompts.html                # プロンプト編集UI
│       └── settings.html               # Ollama・サマライザー設定UI
├── db/
│   ├── backfill_media.py / backfill_weather.py
│   ├── migrate_streaming_views.sql
│   ├── migrate_sort_shortname.sql / .py
│   └── migrate_summary_type.sql       # summaries.summary_type カラム追加
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
| 15 | pon.icu @health (archived) | misskey |
| 16 | groundpolis.app @healthcare (archived) | misskey |
| 17 | Cosense stall | scrapbox |
| 18 | Jomo スクリーンタイム | screen_time |
| 19 | Netflix | netflix |
| 20 | Amazon Prime Video | prime |

`db/migrate_jomo_screen_time.sql` / `db/migrate_streaming_views.sql` 適用で id 18〜20 が追加される。

---

## LLMへの渡し方

**最初に読む**: `docs/overview.md` → このファイル

**Phase 6 実装時**: `docs/phase6_plan.md` → `docs/design.md` §7–8 → サマライザー全体は `docs/summary_daily_and_dashboard.md`

**サマライザー品質向上の背景**: `docs/summarizer_quality_plan.md`

**必要に応じて**: `docs/dashboard_ui.md` / `docs/iphone_shortcuts.md` / `docs/importers.md` / `docs/api/*.md`
