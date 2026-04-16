# Planet 設計書

**プロジェクト名**: Planet
**バージョン**: 1.3
**作成日**: 2026-03-22
**ステータス**: 設計確定・実装準備中

---

## 1. プロジェクト概要

### 目的
SNS投稿・音楽再生履歴・健康データ・天気等の個人活動データを自動収集し、PostgreSQLに蓄積。週次・月次のAIサマリーを自動生成して個人サイトに公開する、自動ライフログシステム。

### 名前の由来
2000年代のRSSアグリゲーターサービス「Planet」へのオマージュ。複数のデータソースを一つのタイムラインに集約するコンセプトを引き継ぐ。

### 基本方針
- ユーザーの手動アクションを極力増やさない（完全自動化）
- 過去データ（2017年4月〜）も含めて一元管理
- プライバシーに配慮し、公開するデータと非公開データを明確に分ける
- 自宅Ubuntuサーバーで完結させる
- データソースは今後追加できる拡張性を持たせる（ダッシュボードのUIから追加可能）

---

## 2. システム構成

```
【収集層】
data_sources テーブルで管理された全ソースを動的に処理
  - Misskey API（misskey.io / tanoshii.site 等）
  - Mastodon API（mistodon.cloud 等）
  - Last.fm API
  - OpenWeatherMap API
  - GitHub API
  - YouTube Data API v3（投稿動画）
  - 個人サイト RSS
  - iPhone ショートカット → Flask API（ヘルス・写真メタデータ）
  - 過去JSONデータ一括インポート（Misskey・Twitter）
        ↓ cron で定期自動実行
【保存層】
PostgreSQL on Ubuntu
  - data_sources テーブル（ソース管理）
  - logs テーブル（統合タイムライン）
  - ソース別詳細テーブル
  - url_metadata テーブル（OGP情報）
  - summaries テーブル
        ↓
【処理層】
  - URL OGP取得（収集時バックグラウンド非同期処理）
  - Ollama（gemma3:12b）で週次・月次サマリー自動生成
        ↓
        ├──────────────────────────────────┐
【ダッシュボード層】               【公開層】
Flask + ブラウザ                  HTML自動生成（1日1回 AM 7:00）
Tailscale 経由でアクセス          → Neocities API でアップロード
（ローカル閲覧専用）              （Planetページ・週次サマリー）
ダークテーマ・シンプル・クール
        ↓
【バックアップ層】
pg_dump → gzip → rclone → pCloud（週1回 cron）
```

---

## 3. インフラ

| 項目 | 内容 |
|---|---|
| サーバー OS | Ubuntu（自宅）|
| 外部アクセス | Tailscale |
| DB | PostgreSQL（pg_bigm拡張で日本語全文検索）|
| スクリプト言語 | Python |
| Webフレームワーク | Flask |
| 自動実行 | cron |
| AIモデル | Ollama（gemma3:12b）※品質次第で変更 |
| バックアップ先 | pCloud（rclone 経由、900GB）|
| 公開先 | Neocities（yuinoid.neocities.org）|

---

## 4. データソース一覧

| ソース | 種別 | アカウント / URL | 収集頻度 | 公開 |
|---|---|---|---|---|
| misskey.io | Misskey | @yuinoid@misskey.io | 1時間ごと | ○ |
| tanoshii.site | Misskey | @health@tanoshii.site | 1時間ごと | ○ |
| mistodon.cloud | Mastodon | @healthcare@mistodon.cloud | 1時間ごと | ○ |
| Last.fm | 音楽再生履歴 | objtus | 1時間ごと | ○ |
| 個人サイト RSS | サイト更新 | yuinoid.neocities.org/rss.xml | 1日1回 | ○ |
| YouTube | 投稿動画 | （チャンネルID設定）| 1日1回 | ○ |
| OpenWeatherMap | 天気 | （位置情報設定）| 1日1回 | △（統計のみ）|
| GitHub | 開発活動 | （アカウント設定）| 1日1回 | △（統計のみ）|
| iPhone ヘルス | 歩数・カロリー・心拍数・運動/スタンド | HealthKit → Flask | 1日1回（夜）| ✗ |
| iPhone 写真 | 撮影メタデータ（日時・位置）| HealthKit → Flask | 1日1回（夜）| ✗ |
| Cosense (Scrapbox) | 日記（stallプロジェクト）| scrapbox.io API | 1日1回 | ✗ |
| 過去 JSON | 一括インポート | Misskey・Twitter エクスポート | 初回のみ | ○（SNS分）|

※公開列: ○=Planetページに表示 △=統計のみダッシュボード表示 ✗=非公開

### 拡張性について
新しいデータソースや同一サーバーの別アカウントを追加する際は、ダッシュボードのソース管理画面から追加できる。追加操作は`data_sources`テーブルへの1行追加に相当する。収集スクリプトはこのテーブルを動的に読んで処理するため、コード変更不要。

---

## 5. データベーススキーマ

### 設計方針
**ハイブリッド方式**を採用。

- `data_sources`テーブル：ソース定義をDBで管理（拡張性の核心）
- `logs`テーブル：全ソース共通の統一ビュー（タイムライン表示・AI受け渡し用）
- ソース別テーブル：ソース固有のデータ（統計・詳細クエリ用）
- データ書き込み時はトランザクションで両方に同時保存（整合性保証）

### 重要な設計上の注意点
- 全タイムスタンプはUTC（TIMESTAMPTZ）で保存し、表示時にJSTへ変換する
- 投稿削除への対応：削除フラグ（is_deleted）で非表示にする（物理削除しない）
- visibility が public 以外の投稿は Neocities に公開しない
- CW付き投稿はダッシュボードでも折りたたみ表示にする

### 5-0. data_sources テーブル

```sql
CREATE TABLE data_sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,          -- 表示名 例: 'misskey.io @yuinoid'
    type        TEXT NOT NULL,          -- 'misskey' / 'mastodon' / 'lastfm' /
                                        -- 'weather' / 'github' / 'youtube' /
                                        -- 'rss' / 'health' / 'photo' /
                                        -- 'netflix' / 'prime' / …
    base_url    TEXT,                   -- 'https://misskey.io'
    account     TEXT,                   -- '@yuinoid'
    config      JSONB,                  -- APIキー・インスタンス固有設定等
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### 5-1. logs テーブル（統合）

```sql
CREATE TABLE logs (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INT REFERENCES data_sources(id),
    original_id   TEXT,
    content       TEXT,
    url           TEXT,
    metadata      JSONB,
    is_deleted    BOOLEAN DEFAULT FALSE,
    timestamp     TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source_id, original_id)
);

CREATE INDEX idx_logs_timestamp   ON logs (timestamp DESC);
CREATE INDEX idx_logs_source_id   ON logs (source_id);
CREATE INDEX idx_logs_metadata    ON logs USING GIN (metadata);
CREATE INDEX idx_logs_content_fts ON logs USING GIN (content gin_bigm_ops);
```

### 5-2. misskey_posts テーブル

```sql
CREATE TABLE misskey_posts (
    id             BIGSERIAL PRIMARY KEY,
    log_id         BIGINT REFERENCES logs(id),
    source_id      INT REFERENCES data_sources(id),
    post_id        TEXT NOT NULL,
    text           TEXT,
    cw             TEXT,
    url            TEXT,
    reply_count    INT DEFAULT 0,
    renote_count   INT DEFAULT 0,
    reaction_count INT DEFAULT 0,
    has_files      BOOLEAN DEFAULT FALSE,
    visibility     TEXT,
    is_deleted     BOOLEAN DEFAULT FALSE,
    posted_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, post_id)
);
```

### 5-3. mastodon_posts テーブル

```sql
CREATE TABLE mastodon_posts (
    id              BIGSERIAL PRIMARY KEY,
    log_id          BIGINT REFERENCES logs(id),
    source_id       INT REFERENCES data_sources(id),
    post_id         TEXT NOT NULL,
    content         TEXT,
    spoiler_text    TEXT,
    url             TEXT,
    reply_count     INT DEFAULT 0,
    reblog_count    INT DEFAULT 0,
    favourite_count INT DEFAULT 0,
    visibility      TEXT,
    is_deleted      BOOLEAN DEFAULT FALSE,
    posted_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, post_id)
);
```

### 5-4. lastfm_plays テーブル

```sql
CREATE TABLE lastfm_plays (
    id          BIGSERIAL PRIMARY KEY,
    log_id      BIGINT REFERENCES logs(id),
    track_id    TEXT UNIQUE NOT NULL,
    artist      TEXT NOT NULL,
    track       TEXT NOT NULL,
    album       TEXT,
    url         TEXT,
    played_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_lastfm_artist ON lastfm_plays (artist);
```

### 5-5. youtube_videos テーブル

```sql
CREATE TABLE youtube_videos (
    id             BIGSERIAL PRIMARY KEY,
    log_id         BIGINT REFERENCES logs(id),
    video_id       TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT,
    url            TEXT,
    duration_sec   INT,
    view_count     BIGINT DEFAULT 0,
    like_count     BIGINT DEFAULT 0,
    comment_count  BIGINT DEFAULT 0,
    published_at   TIMESTAMPTZ NOT NULL
);
```

### 5-6. weather_daily テーブル

```sql
CREATE TABLE weather_daily (
    id            BIGSERIAL PRIMARY KEY,
    log_id        BIGINT REFERENCES logs(id),
    date          DATE UNIQUE NOT NULL,
    temp_max      NUMERIC(4,1),
    temp_min      NUMERIC(4,1),
    temp_avg      NUMERIC(4,1),
    weather_main  TEXT,
    weather_desc  TEXT,
    humidity      INT,
    location      TEXT
);
```

### 5-7. github_activity テーブル

```sql
CREATE TABLE github_activity (
    id           BIGSERIAL PRIMARY KEY,
    log_id       BIGINT REFERENCES logs(id),
    event_id     TEXT UNIQUE NOT NULL,
    event_type   TEXT,
    repo_name    TEXT,
    url          TEXT,
    commit_count INT DEFAULT 0,
    summary      TEXT,
    occurred_at  TIMESTAMPTZ NOT NULL
);
```

### 5-8. health_daily テーブル

```sql
CREATE TABLE health_daily (
    id                  BIGSERIAL PRIMARY KEY,
    log_id              BIGINT REFERENCES logs(id),
    date                DATE UNIQUE NOT NULL,
    steps               INT,
    active_calories     INT,
    heart_rate_avg      INT,
    heart_rate_max      INT,
    heart_rate_min      INT,
    exercise_minutes    INT,
    stand_hours         INT,
    screen_time_seconds INT,        -- Jomo 経由の1日合計（秒）
    photo_count         INT DEFAULT 0,
    photo_locations     JSONB
);
```

### 5-8b. streaming_views テーブル

Netflix / Prime Video の視聴履歴 CSV インポート用。`logs` と 1:1（`log_id` UNIQUE）。

```sql
CREATE TABLE streaming_views (
    id                   BIGSERIAL PRIMARY KEY,
    log_id               BIGINT NOT NULL UNIQUE REFERENCES logs(id) ON DELETE CASCADE,
    source_id            INT NOT NULL REFERENCES data_sources(id),
    provider             TEXT NOT NULL CHECK (provider IN ('netflix', 'prime')),
    title                TEXT NOT NULL,
    episode_title        TEXT,
    watched_on           DATE NOT NULL,
    watched_at           TIMESTAMPTZ NOT NULL,
    content_kind         TEXT,
    external_series_id   TEXT,
    external_episode_id  TEXT,
    metadata             JSONB
);
```

### 5-9. rss_entries テーブル

```sql
CREATE TABLE rss_entries (
    id           BIGSERIAL PRIMARY KEY,
    log_id       BIGINT REFERENCES logs(id),
    entry_id     TEXT UNIQUE NOT NULL,
    title        TEXT,
    url          TEXT,
    summary      TEXT,
    published_at TIMESTAMPTZ NOT NULL
);
```

### 5-10. url_metadata テーブル

```sql
CREATE TABLE url_metadata (
    id           BIGSERIAL PRIMARY KEY,
    url          TEXT UNIQUE NOT NULL,
    site_name    TEXT,
    title        TEXT,
    description  TEXT,
    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
    fetch_status INT DEFAULT 0,      -- 0=未取得 200=成功 4xx/5xx=失敗
    retry_count  INT DEFAULT 0
);
```

### 5-11. summaries テーブル

```sql
CREATE TABLE summaries (
    id           BIGSERIAL PRIMARY KEY,
    period_type  TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end   DATE NOT NULL,
    week_number  INT,
    content      TEXT NOT NULL,
    model        TEXT,
    prompt_style TEXT DEFAULT 'hybrid',
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (period_type, period_start)
);
```

---

## 6. ダッシュボード仕様

### アクセス方法
- URL: `http://<tailscale-ip>:5000`
- 認証: Tailscaleネットワーク内のみ（追加認証なし）

### デザイン方針
- ダークテーマ
- シンプル・クール・情報密度高め
- 装飾最小限
- モバイル（iPhone）対応レスポンシブ

### 画面構成

| 画面 | パス | 概要 |
|---|---|---|
| カレンダー | `/` | メイン。ヒートマップカレンダーから日/週/月/年を選択 |
| 検索 | `/search` | キーワード（`logs.content` 部分一致）＋ソース・日付範囲。結果の日時はカレンダー日ビュー（`?view=day&date=`）へリンク。Last.fm は行からソフト削除可（`POST /api/logs/<id>/soft-delete`、カレンダーと同 API） |
| サマリー一覧 | `/summaries` | 週次・月次サマリー一覧・公開管理 |
| 統計 | `/stats` | グラフ・集計ビュー |
| ソース管理 | `/sources` | データソースの追加・編集・有効/無効切り替え |

### カレンダー画面詳細

- ISO週番号つきカレンダー表示
- 日付ヒートマップ：投稿数に応じて色が変化（GitHubスタイル）
- 選択単位による表示切り替え：

| 選択単位 | 表示内容 |
|---|---|
| 日 | 全ソースタイムライン＋その日の簡易統計 |
| 週（週番号クリック）| 全投稿一覧＋週次サマリー＋統計 |
| 月 | 月次サマリー＋統計＋投稿一覧（遅延読み込み）|
| 年 | 年間統計＋月別サマリー一覧 |

- 月・年の投稿一覧は「一覧を表示する」ボタンで遅延読み込み

### ソース管理画面詳細

- 登録済みソース一覧（有効/無効トグル・削除ボタン）
- 新規追加フォーム：種別を選択 → 種別に応じてフィールドが切り替わる
- 接続テストボタン：追加前にAPIの疎通確認
- 対応種別：RSS / Misskey / Mastodon（追加が簡単なもの優先）

---

## 7. サマリー生成仕様

### 生成タイミング
- 週次：毎週月曜 AM 6:00（前週分）
- 月次：毎月1日 AM 6:30（前月分）
- 過去分：初回セットアップ時に一括生成（Ollamaで処理）

### サマリースタイル：分析調＋箇条書きレポートのハイブリッド

```
■ 今週のトピック
・〇〇について複数回投稿。〇〇（サイト名）のURLを共有。
・〇〇に反応している様子。

■ 音楽
・再生数: 〇曲 / 最多アーティスト: 〇〇（〇回）
・新しく聴いたアーティスト: 〇〇

■ 活動量
・平均歩数: 〇歩 / 平均カロリー: 〇kcal
・平均心拍数: 〇bpm / 運動時間合計: 〇分

■ 開発活動
・コミット数: 〇件（リポジトリ: 〇〇）

■ 総評
〇〇に関心が集中した一週間。活動量は先週比〇〇%。
```

- プロンプトはテンプレートファイルとして管理
- スタイルは設定変更で後から切り替え可能

### モデル設定
- 初期: `gemma3:12b`（Ollama）
- `config/settings.toml` の `model` を変更するだけで切り替え可能

---

## 8. 公開仕様（Neocities）

### 公開するもの
- **雑記**: 週次サマリーページ（新規分のみ。読み物としての HTML を Neocities にアップロード）
- **Planet ページ**: 全ソースの最新タイムライン（現行ページを DB ベースに移行。公開用データは別経路で配信し Neocities 側は主に静的 HTML。概要は `docs/planet_feed_setup.md`）

### 公開しないもの
- 過去サマリー（ダッシュボードのみ）
- ヘルスデータ
- 天気データ

### 更新頻度・タイミング
- 1日1回 AM 7:00（HTML生成 → Neocities APIアップロード）

### Neocities API
- エンドポイント: `POST https://neocities.org/api/upload`
- 認証: APIキー（`Authorization: Bearer <api_key>`）
- Pythonからは `requests` で直接叩く（外部ライブラリ不要）

---

## 9. iPhoneショートカット仕様

詳細・手順・curl 例は **`docs/iphone_shortcuts.md`** を正とする（以下は概要）。

### エンドポイント
`POST http://<tailscale-ip>:5000/api/ingest`（`dashboard` 経由。Blueprint `ingest_bp`）

### リクエスト形式（概要）

**ヘルス** — `source`: `health`, `date`（`YYYY-MM-DD` または ISO・サーバー側で JST 暦日に正規化）。指標は任意キー（`steps`, `active_calories`, `heart_rate_avg`, …）。**`health_segment`**: `movement` | `activity` で省略可（省略時は 1 日 1 `logs` 行、指定時は `original_id` が `日付#movement` 等で最大 2 行）。**`archive`**: 手動の過去日投入用。真相当なら `logs.timestamp` を当該 `date` の JST 23:49（movement）または 23:50（それ以外）に固定。

**写真** — 現行は `count`（ダミー可）+ **`photo_json`**（JSON 配列文字列、`t` / `loc`）が主。旧形式の `photos` 配列（`lat`/`lng`）も `ingest` 内で処理あり。

**スクリーンタイム** — `source`: `screen_time`, `screen_time_seconds`（Jomo）。

### 実行タイミング（目安・オートメーション）
- ヘルス：負荷分散のため **23:00 前後（movement）** と **数分後（activity）** の 2 本、または 1 本でまとめて送信
- 写真：ヘルスと重ならない **23:06 前後** など
- Jomo：その後のスロット（例: 23:10）

---

## 10. バックアップ仕様

```bash
# /planet/backup/backup.sh
# 毎週日曜 AM 3:00 に cron で実行

pg_dump planet | gzip > /backup/planet_$(date +%Y%m%d).sql.gz
rclone copy /backup/ pcloud:planet-backup/
find /backup/ -name "*.sql.gz" -mtime +28 -delete
```

---

## 11. 実装ロードマップ

### Phase 1：基盤構築
1. PostgreSQL セットアップ・pg_bigm導入
2. スキーマ作成（全テーブル）
3. data_sourcesテーブルへの初期データ投入
4. Flaskアプリ骨格・ルーティング作成
5. `settings.toml` の構造定義

### Phase 2：過去データのインポート
6. Misskey JSONインポートスクリプト
7. Twitter JSONインポートスクリプト

### Phase 3：自動収集
8. 収集スクリプト基底クラス（base.py）
9. Misskey収集スクリプト
10. Mastodon収集スクリプト
11. Last.fm収集スクリプト
12. OpenWeatherMap収集スクリプト
13. GitHub収集スクリプト
14. YouTube収集スクリプト
15. RSS収集スクリプト
16. URL OGPバックグラウンドワーカー
17. cron設定

### Phase 4：iPhone連携
18. Flask `/api/ingest` エンドポイント
19. iPhoneショートカット設定手順

### Phase 5：ダッシュボード
20. カレンダーUI（ヒートマップ付き）
21. タイムライン表示
22. 検索機能
23. 統計グラフ
24. サマリー一覧・手動公開機能
25. ソース管理画面（追加・テスト・有効/無効）

### Phase 6：AI生成・公開
26. Ollamaサマリー生成スクリプト
27. プロンプトテンプレート整備
28. 過去分サマリー一括生成
29. Neocities HTMLテンプレート作成
30. Neocitiesアップロードスクリプト
31. Planetページ HTML生成スクリプト

### Phase 7：自動化・バックアップ
32. 全cronジョブ統合・整理
33. バックアップスクリプト
34. エラーログ整備

---

## 12. ディレクトリ構成

```
planet/
├── config/
│   ├── settings.toml           # APIキー・DB接続・モデル名等（gitignore対象）
│   └── settings.toml.example   # ダミー値入りサンプル（git管理対象）
├── collectors/
│   ├── base.py                 # 共通基底クラス（差分取得・重複防止ロジック）
│   ├── misskey.py
│   ├── mastodon.py
│   ├── lastfm.py
│   ├── weather.py
│   ├── github.py
│   ├── youtube.py
│   ├── rss.py
│   └── ogp_worker.py
├── importers/
│   ├── misskey_json.py
│   └── twitter_json.py
├── summarizer/
│   ├── generate.py
│   └── prompts/
│       ├── weekly_hybrid.txt
│       └── monthly_hybrid.txt
├── publisher/
│   ├── neocities.py
│   ├── build.py
│   └── templates/
│       ├── planet.html
│       └── summary.html
├── dashboard/
│   ├── app.py
│   ├── templates/
│   └── static/
├── ingest/
│   └── api.py
├── backup/
│   └── backup.sh
├── docs/                       # このドキュメント群
└── cron/
    └── crontab.txt
```

---

## 13. 未決事項・今後の検討

| 項目 | 内容 |
|---|---|
| Twitter収集 | 対象外（API申請コストに見合わない）|
| サマリー品質 | gemma3:12bで試してから評価。不満なら qwen2.5:14b 等 |
| 過去サマリーの任意公開 | サマリー一覧画面から手動で公開できる機能を追加検討 |
| エラー通知 | ログファイル＋ダッシュボードでのエラー表示（最低限）|
| YouTube視聴履歴 | Google Takeoutで検討余地あり |
| マテリアライズドビュー | 年間統計など重いクエリが出てきたら導入検討 |
