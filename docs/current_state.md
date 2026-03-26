# 現在の実装状況

**最終更新**: 2026-03-26（Phase 5 完了・Phase 6 計画反映）

---

## 完了済み

- [x] 要件定義・設計（docs/design.md）
- [x] ドキュメント整備（overview / decisions / next_tasks / dashboard_ui / api/ / importers.md）
- [x] モックアップ作成（mockup/calender_v3.html）

### Phase 1: 基盤構築（完了）

- [x] Python 3.12.3 確認
- [x] PostgreSQL 16.13 インストール・起動・自動起動設定
- [x] DBユーザー `planet` / DB `planet` 作成
- [x] pg_bigm v1.2-20250903 ビルド・インストール・拡張有効化
- [x] スキーマ作成（全11テーブル: data_sources / logs / misskey_posts / mastodon_posts / lastfm_plays / youtube_videos / weather_daily / github_activity / health_daily / rss_entries / url_metadata / summaries）
- [x] data_sources 初期データ投入（14ソース）
- [x] Python仮想環境（venv）作成
- [x] パッケージインストール（flask / psycopg2-binary / requests / feedparser / beautifulsoup4 / pylast / python-dateutil）
- [x] config/settings.toml 作成（[[misskey_accounts]] / [[mastodon_accounts]] 配列形式）

### APIキー取得状況

- [x] Last.fm
- [x] OpenWeatherMap
- [x] GitHub PAT
- [x] Misskey: misskey.io @yuinoid (source_id=1)
- [x] Misskey: tanoshii.site @health (source_id=2)
- [x] Misskey: misskey.io @vknsq (source_id=11)
- [x] Misskey: msk.ilnk.info @google (source_id=12)
- [x] Misskey: sushi.ski @idoko (source_id=13)
- [x] Mastodon: mistodon.cloud @healthcare (source_id=3)
- [x] Mastodon: mastodon.cloud @objtus (source_id=14)
- [x] Neocities
- [ ] YouTube Data API v3（後回し）

---

### Phase 2: 過去データインポート（完了）

- [x] importers/misskey_json.py 作成
- [x] importers/mastodon_json.py 作成
- [x] msk.ilnk.info @google: 938投稿 84RN
- [x] pon.icu @health (archived): 5,205投稿 478RN
- [x] groundpolis.app @healthcare (archived): 7,879投稿 176RN
- [x] tanoshii.site @health: 4,188投稿 195RN
- [x] misskey.io @vknsq: 4,147投稿 133RN
- [x] mastodon.cloud @objtus: 12,383投稿 369BT
- [x] logs合計: 36,175件（2025年12月末まで）

---

### Phase 3: 自動収集（完了）

- [x] collectors/base.py（共通基底クラス）
- [x] collectors/misskey.py（5アカウント・1時間ごと）
- [x] collectors/mastodon.py（2アカウント・1時間ごと、mastodon.cloudは不調）
- [x] collectors/lastfm.py（1時間ごと）
- [x] collectors/weather.py（1日1回 AM 6:00）
- [x] collectors/github.py（1日1回 AM 6:00）
- [x] collectors/rss.py（1日1回 AM 6:00）
- [x] collectors/youtube.py（APIキー取得後に有効化）
- [x] collect_all.py（一括実行スクリプト）
- [x] cron登録済み（cron/crontab.txt）

---

### Phase 4: iPhone連携（完了）

- [x] ingest/api.py 作成（Flask Blueprint）
  - `POST /api/ingest` — ヘルスデータ・写真メタデータを受け取り health_daily / logs に保存
  - `GET /api/health` — 死活確認用エンドポイント
  - `active_calories` の小数を整数に丸める処理
  - `date` / `dates` どちらのキーでも受け付ける
  - `photo_json` / `photos_json` どちらのキーでも受け付ける
  - 位置情報の住所中の改行をスペース変換して JSON パース
- [x] planet-dashboard.service に統合済み（planet-ingest.service は廃止）
- [x] iPhoneショートカット 1（ヘルスデータ）実機で動作確認済み
- [x] iPhoneショートカット 2（写真メタデータ）実機で動作確認済み
  - タイムスタンプ・位置情報（住所）・枚数を保存
- [x] docs/iphone_shortcuts.md 作成・実際の動作に合わせて更新済み
- [x] タイムスタンプを実際の受信時刻（`datetime.now(utc)`）に変更（固定 23:00/23:05 廃止）
  - 再送時は同一 date の upsert で値・タイムスタンプを最新に上書き

#### 実装上の注意点

- ヘルス: `ヘルスケアサンプルを検索` を使う（`ヘルスケアの数量を取得` には集計機能なし）
- 心拍数の最大・最小: `ヘルスケアサンプルを検索` で値の降順/昇順ソート + 上限1件
- 心拍数の平均の代わりに `安静時心拍数` サンプルを使用
- 写真: ループ内で**辞書ではなくテキスト**を `変数に追加` するのがポイント（辞書を追加すると 0 件になる iOS Shortcuts の挙動）
- `count` フィールドはダミー値 0 を送り、サーバー側で `photo_json` の要素数から実際の枚数を算出

---

## 進行中

### Phase 6: AI生成・公開（着手済み・計画あり）

- [x] **M1（週次 1 本）**: `./venv/bin/python -m summarizer.generate --period week --date YYYY-Www` — `summarizer/`、`config/settings.toml` の `[ollama]`（venv 必須: `psycopg2`）。詳細は **`docs/phase6_plan.md`**
- [ ] M2 以降（月次・バッチ・Neocities・Planet ページ）は同ファイルのマイルストーンに従う

---

### Phase 5: ダッシュボード（完了）

#### 完了済み（Phase 5）

- [x] `dashboard/app.py`（Flask 本体 + ingest_bp 統合・全ルート実装）
  - `/` — カレンダー画面
  - `/search` — 検索
  - `/summaries` — サマリー一覧
  - `/stats` — 統計（月別・年別集計クエリ）
  - `/sources` — ソース管理（有効/無効・並べ替え・略称・収集）
  - `/api/timeline` — タイムライン JSON API（day/week/month/year）、新着順（DESC）
  - `/api/stats` — 統計 JSON API（period=day/week/month/year 対応・集計）
  - `/api/ingest`・`/api/health` — iPhone ingest（Phase 4 Blueprint）
  - `POST /sources/<id>/move` — `{"direction":"up"|"down"}` で `sort_order` 入れ替え
  - `POST /sources/<id>/rename` — `{"short_name":"..."}` で略称更新
  - `POST /api/collect/<stype>` — 収集スクリプトをサブプロセス実行（`stype` は種別名または `all`）。`PYTHONPATH` にリポジトリルートを付与
  - `GET /api/summary` — `period=week|month|year` と `date`（週は `YYYY-Www`、月は `YYYY-MM`、年は西暦）。週・月は 1 件 or null、年は月次サマリー配列
  - `PATCH /api/summaries/<id>/publish` — JSON `{"is_published": bool}`、`published_at` 連動
- [x] `dashboard/static/css/dashboard.css`（CSS変数ベース・ライト/ダーク自動切替）
- [x] `dashboard/static/js/calendar.js`（カレンダーロジック全体・フィルター・タイムライン描画）
- [x] `dashboard/templates/base.html`（ナビ・共通レイアウト）
- [x] `dashboard/templates/calendar.html`（月カレンダーグリッド + 詳細パネル）
- [x] `dashboard/templates/search.html`
- [x] `dashboard/templates/summaries.html`
- [x] `dashboard/templates/stats.html`（Chart.js 月別積み上げ・ソース別バー。`static/js/chart.umd.min.js` ローカル配信、モバイル向けキャンバス最小高さ）
- [x] 統計: 「月別（直近12ヶ月）」と「年別（全期間）」の表示切替
- [x] `dashboard/templates/sources.html`（トグル・並べ替え・略称編集・収集ボタン）
- [x] `planet-dashboard.service` systemd 登録・自動起動設定済み
- [x] `planet-ingest.service` 廃止（dashboard に統合）

#### ダッシュボード機能詳細（実装済み）

**カレンダー・ナビゲーション**
- [x] 月カレンダーグリッド + ヒートマップ（投稿数を色で表示）
- [x] 前後月にまたがる日付セルは薄色表示（週の埋め）。他月クリックでその日へジャンプ
- [x] 週番号ボタンクリックで週ビュー選択
- [x] view-tabs `[‹][日][週][月][年][›]` — ‹/› で前後の日/週/月/年に移動
- [x] view-tabs ↔ カレンダー選択の双方向連動
- [x] 今日ボタン
- [x] カレンダー右上: 現在表示中の「○月」「○年」ボタンで月/年タイムラインへ（`goCalMonth` / `goCalYear`。カレンダー上の月は維持。view-tabs の年→月で1月へ落ちる挙動とは別経路）
- [x] タイムライン見出し `#detail-title`: **表示中タイムラインの期間**のみ表示。`calendar.js` の `tlTitle` + `setTlTitle()` で保持し、`buildCal()` 内の `updateDetailTitle()` は復元のみ（カレンダーの `«‹›»` ナビと表示内容を分離）

**サマリー（カレンダー・一覧・API）**
- [x] 週・月ビュー: `stat-row` と週天気帯の下・フィルターバー上の `#summary-panel` で `GET /api/summary` の本文を表示（`textContent` で XSS 回避）
- [x] 年ビュー: 同パネルで年内の月次サマリー一覧、「月表示へ」で月ビューへ遷移
- [x] `/summaries`: Neocities 公開チェックボックス + `PATCH .../publish`

**タイムライン**
- [x] 新着順表示（最新が上）
- [x] ソースバッジ（favicon 画像 + 絵文字フォールバック）
- [x] バッジクリック → ソロフィルタリング（もう一度でリセット）
- [x] CW（コンテンツ警告）折りたたみ
- [x] ブースト/リノート表示
- [x] 外部リンク（↗）
- [x] メディア添付表示（画像サムネイル・動画プレイボタン）
  - 旧データ（URL未保存）は 📎 アイコン表示
- [x] 画像サムネイル: ライトボックスで拡大（前後ナビ・キーボード）

**フィルターバー**
- [x] 折りたたみ式（デフォルト折りたたみ）
- [x] `[フィルター N/N ▾][すべて] | [📷 メディア]` — 常時表示
- [x] 展開時にソース別ボタン一覧（favicon + 短縮名）
- [x] 絞り込み中はトグルボタンをハイライト（`3/14` 表示）
- [x] メディアフィルター（画像・動画添付投稿のみ表示）

**統計カード**
- [x] 日ビュー: 投稿数・再生数・歩数・天気（その日の値）
- [x] 週/月/年ビュー: 各値の合計・天気は平均気温＋min–max 表示

**favicon**
- [x] lastfm・github・youtube: 既知 URL から直接取得
- [x] misskey/mastodon: `base_url/favicon.ico`
- [x] 廃止サーバー（is_active=False）: 絵文字フォールバック
- [x] 1×1px トラッキングピクセル自動フォールバック

**メディア添付収集**
- [x] `collectors/misskey.py`・`collectors/mastodon.py`: `metadata["media"]` に URL・type・サムネイル保存
- [x] `importers/misskey_json.py`: ActivityPub attachment を metadata に保存
- [x] `db/backfill_media.py`: 既存データの media URL バックフィルスクリプト
  - 廃止サーバー分は is_active=False で自動クリア

**iPhone ingest（改善済み）**
- [x] ヘルス・写真データのタイムスタンプを「実際の受信時刻」に変更（固定 23:00 → now()）
  - オートメーションの実行確認が可能になった

#### DB・天気・バックフィル（2026-03 追記）

- [x] `data_sources` に `sort_order`（表示順）・`short_name`（一覧用略称、任意）を追加。SQL: `db/migrate_sort_shortname.sql`（所有者は `postgres` で実行する想定）
- [x] 補助: `db/migrate_sort_shortname.py`（権限により SQL 直実行を推奨）
- [x] OpenWeatherMap 取得地点: `config/settings.toml` の `lat` / `lon` / `location` を名古屋（愛知）に変更
- [x] 過去天気バックフィル: `db/backfill_weather.py` — Open-Meteo 履歴を `weather_daily` と `logs` に投入可能（運用は手動実行）

#### Phase 5 で任意・低優先に回したもの

- mockup とのピクセル級の差分、モバイル幅の細かい詰め → 必要時に `docs/next_tasks.md` 参照
- 検索（`/search`）の `pg_bigm` / GIN 最適化はログ増加後に検討（`next_tasks.md` バックログ）

---

## 未着手

- [ ] Phase 6: 残り（月次・一括・Neocities 等。**手順書**: `docs/phase6_plan.md`）
- [ ] Phase 7: 自動化・バックアップ

---

## 既知の問題・注意事項

- ソース管理の「今すぐ収集」APIは、クライアント都合で JSON ボディではなく `POST /api/collect/<stype>` のパスパラメータ方式（Tailscale + iOS Safari での `Failed to fetch` 回避）
- `data_sources` のマイグレーションはテーブル所有者権限が必要。ホーム直下の `.sql` を `postgres` が読めない場合は `/tmp` にコピーして `psql -f` する
- pon.icu / groundpolis.app は閉鎖済み個人インスタンス。is_active=False、favicon は絵文字フォールバック
- 過去JSONはMisskey・Mastodon両方とも同一構造（announce/type: Noteの混在）
- ブーストをインポートするかは settings.toml の include_boosts で制御
- YouTube収集スクリプトは後回し（APIキー未取得）
- mastodon.cloud @objtus の収集が不調（原因未調査）
- `db/backfill_media.py` で既存 Misskey 投稿の media URL をバックフィル済み（206件更新・削除済み投稿は has_files=FALSE にクリア）

---

## 環境情報

- Ubuntu 24.04（自宅サーバー）
- Python 3.12.3
- PostgreSQL 16.13 + pg_bigm v1.2-20250903
- Tailscale インストール済み
- Ollama + Open WebUI インストール済み
- 仮想環境: /home/objtus/planet/venv
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
│   └── ogp_worker.py
├── importers/
│   ├── misskey_json.py
│   └── mastodon_json.py
├── ingest/
│   └── api.py                  # Flask Blueprint（dashboard に統合済み）
├── summarizer/
│   ├── generate.py             # 週次サマリー CLI（Ollama → summaries UPSERT）
│   ├── db.py, context.py, week_bounds.py, ollama_client.py
│   └── prompts/weekly_hybrid.txt
├── dashboard/
│   ├── app.py                  # Flask 本体
│   ├── planet-dashboard.service
│   ├── static/
│   │   ├── css/dashboard.css
│   │   └── js/
│   │       ├── calendar.js
│   │       └── chart.umd.min.js   # 統計ページ用 Chart.js（ローカル）
│   └── templates/
│       ├── base.html
│       ├── calendar.html
│       ├── search.html
│       ├── summaries.html
│       ├── stats.html
│       ├── sources.html
│       └── timeline.html
├── db/
│   ├── backfill_media.py       # 既存 Misskey 投稿の media URL バックフィル
│   ├── backfill_weather.py     # Open-Meteo による過去天気のバックフィル
│   ├── migrate_sort_shortname.sql
│   └── migrate_sort_shortname.py  # 権限次第では SQL を postgres で実行
├── mockup/
│   └── calender_v3.html        # UI デザインモックアップ
├── docs/
│   ├── overview.md
│   ├── current_state.md        # このファイル
│   ├── next_tasks.md
│   ├── phase6_plan.md          # Phase 6 実装プラン（AI・Neocities）
│   ├── summary_integration_plan.md
│   ├── design.md
│   ├── dashboard_ui.md
│   ├── decisions.md
│   ├── importers.md
│   ├── iphone_shortcuts.md
│   ├── setup.md
│   └── api/
└── cron/
    └── crontab.txt
```

---

## data_sources テーブル（現在）

表示順・略称: `sort_order`（整数、小さいほど上）、`short_name`（varchar、NULL 可。未設定時は従来どおり自動短縮名）。

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
