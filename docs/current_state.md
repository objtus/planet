# 現在の実装状況

**最終更新**: 2026-03-23（Phase 5 着手）

---

## 完了済み

- [x] 要件定義・設計（docs/design.md）
- [x] ドキュメント整備（overview / decisions / next_tasks / api/ / importers.md）
- [x] Claude Code セットアップ済み

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

### Phase 4: iPhone連携（完了）

- [x] ingest/api.py 作成（Flask Blueprint）
  - `POST /api/ingest` — ヘルスデータ・写真メタデータを受け取り health_daily / logs に保存
  - `GET /api/health` — 死活確認用エンドポイント
  - `active_calories` の小数を整数に丸める処理
  - `date` / `dates` どちらのキーでも受け付ける
  - `photo_json` / `photos_json` どちらのキーでも受け付ける
  - 位置情報の住所中の改行をスペース変換して JSON パース
- [x] planet-ingest.service を systemd に登録・自動起動設定済み
- [x] iPhoneショートカット 1（ヘルスデータ）実機で動作確認済み
- [x] iPhoneショートカット 2（写真メタデータ）実機で動作確認済み
  - タイムスタンプ・位置情報（住所）・枚数を保存
- [x] docs/iphone_shortcuts.md 作成・実際の動作に合わせて更新済み

#### 実装上の注意点

- ヘルス: `ヘルスケアサンプルを検索` を使う（`ヘルスケアの数量を取得` には集計機能なし）
- 心拍数の最大・最小: `ヘルスケアサンプルを検索` で値の降順/昇順ソート + 上限1件
- 心拍数の平均の代わりに `安静時心拍数` サンプルを使用
- 写真: ループ内で**辞書ではなくテキスト**を `変数に追加` するのがポイント（辞書を追加すると 0 件になる iOS Shortcuts の挙動）
- `count` フィールドはダミー値 0 を送り、サーバー側で `photo_json` の要素数から実際の枚数を算出

## 進行中

### Phase 5: ダッシュボード（実装中）

- [x] `dashboard/app.py` 作成（Flask骨格 + `ingest_bp` 統合）
- [x] `dashboard/templates/base.html`（ダークテーマ・ナビ）
- [x] `dashboard/templates/calendar.html`（ヒートマップ + タイムライン Ajax）
- [x] `dashboard/templates/timeline.html`
- [x] `dashboard/templates/search.html`
- [x] `dashboard/templates/summaries.html`
- [x] `dashboard/templates/stats.html`（Chart.js 月別グラフ・ソース別バー）
- [x] `dashboard/templates/sources.html`（有効/無効トグル）
- [x] `planet-dashboard.service` 作成（`planet-ingest.service` を統合・廃止）
- [ ] pg_bigm 全文検索への切り替え（現在 LIKE 検索）
- [ ] タイムライン：週/月/年表示の実装
- [ ] サマリー公開トグル（is_published）

## 未着手

- [ ] Phase 6: AI生成・公開
- [ ] Phase 7: 自動化・バックアップ

---

## 既知の問題・注意事項

- pon.icuは閉鎖済み個人インスタンス。インポート専用でdata_sourcesには登録しない
- 過去JSONはMisskey・Mastodon両方とも同一構造（announce/type: Noteの混在）
- ブーストをインポートするかは settings.toml の include_boosts で制御
- YouTube収集スクリプトは後回し（APIキー未取得）

---

## 環境情報

- Ubuntu 24.04（自宅サーバー）
- Python 3.12.3
- PostgreSQL 16.13 + pg_bigm v1.2-20250903
- Tailscale インストール済み
- Ollama + Open WebUI インストール済み
- Claude Code インストール済み・認証済み
- 仮想環境: /home/objtus/planet/venv

---

## data_sources テーブル（現在）

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
