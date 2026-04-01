# インポーター仕様書

過去JSONデータの一括インポートに関する仕様。

---

## Netflix / Amazon Prime Video（CSV）

CLI: `importers/streaming_csv.py`（`python -m importers.streaming_csv`）。

**前提**: DB に `streaming_views` テーブルと `data_sources`（`type` = `netflix` / `prime`）を作成済みであること。

```bash
sudo -u postgres psql -d planet < db/migrate_streaming_views.sql
```

（ホーム配下のファイルを `postgres` が読めない場合は、リダイレクトで渡す。）

### コマンド例

```bash
cd /home/objtus/planet
source venv/bin/activate

# パースのみ（DB 不接続）
python -m importers.streaming_csv --dry-run ~/planet-data/exports/NetflixViewingHistory.csv
python -m importers.streaming_csv --dry-run ~/planet-data/exports/watch-history-export-1774956500013.csv

# 本番取り込み（ヘッダから netflix / prime を自動判定。明示する場合は --format）
python -m importers.streaming_csv ~/planet-data/exports/NetflixViewingHistory.csv
python -m importers.streaming_csv --netflix-profile ホ ~/planet-data/exports/NetflixViewingActivityFull.csv
python -m importers.streaming_csv --format prime ~/planet-data/exports/watch-history-export-*.csv
```

- `--strict`: パースエラーで即終了（終了コード 1）。
- `--netflix-profile NAME`: **netflix_activity のみ**。`Profile Name` が一致する行だけ取り込む（家族アカウントで自分のプロファイルだけ入れたいとき）。
- 500 件ごとにコミット。

### Netflix 公式 CSV

#### 視聴履歴（従来の短いエクスポート）

- ヘッダ: `Title`, `Date`
- 日付: `M/D/YY`（時刻なし）。DB ではその**暦日の JST 正午**を `logs.timestamp` に保存。
- `logs.original_id`: `SHA-256(タイトル + NUL + Date列そのまま)` の hex。

#### 視聴アクティビティ（完全版・詳細 CSV）

Netflix アカウントの「視聴アクティビティ」から取得する、列が多い形式（例: `Duration`, `Start Time`, `Profile Name`, …, `Title`）。ファイル名は `NetflixViewingActivityFull.csv` など。

- 自動判定キー: `Title` + `Start Time` + `Duration`
- `Start Time`: `YYYY-MM-DD HH:MM:SS`（タイムゾーン表記なし → **JST** として解釈し、その瞬間を `logs.timestamp` / `streaming_views.watched_at` に保存。従来の `Date` 列版より時刻が正確。
- `logs.original_id`: `SHA-256(タイトル + NUL + Start Time列そのまま)` の hex（同一エピソードの再視聴は行が分かれる）。
- メタデータ: `Duration`, `Profile Name`, `Device Type`, `Supplemental Video Type` 等を `logs.metadata` / `streaming_views.metadata` に格納。
- **Title が空の行**は Netflix 側データの欠損としてスキップされることがある（完全版でも数行）。

手動で `--format netflix_activity` を指定することもできる。

#### 既存データとの整合性（`source_id` = Netflix）

`logs` は `(source_id, original_id)` で upsert される。

| 過去に取り込んだもの | 「ホ」だけ netflix_activity を取り込んだとき |
|----------------------|---------------------------------------------|
| **何もない** | 「ホ」の行だけ新規 INSERT。他プロファイルは DB に載らない。 |
| **同じ netflix_activity を全プロファイル込みで取り済み** | 「ホ」の行は **同じ `original_id`** のため UPDATE（内容・メタデータが上書き）。**j / あ 等の行はそのまま残る**（CSV からは送らないだけで、自動削除はされない）。他プロファイル分を消したい場合は手動で `logs` / `streaming_views` から削除するか、条件付き DELETE が必要。 |
| **古い `Title`+`Date`（日付のみ）形式のみ** | `original_id` の作り方が **別**（`Date` 文字列 vs `Start Time` 文字列）のため、**同じ視聴でも別行として二重登録**になり得る。片方に寄せるなら、古い形式の行を消してから詳細版だけ入れる、または詳細版のみ運用する。 |

### Amazon Prime（ブラウザ等でエクスポートした CSV）

- ヘッダ例: `Date Watched`, `Type`, `Title`, `Episode Title`, `Global Title Identifier`, `Episode Global Title Identifier`, `Path`, `Episode Path`, `Image URL`
- `Date Watched`: `YYYY-MM-DD HH:MM:SS.mmm`（タイムゾーンなし → **JST** として解釈）。
- `logs.original_id`: `Episode Global Title Identifier` が空でなければその文字列。空ならタイトル・エピソード・日時から SHA-256。

### DB

- `logs` と `streaming_views` を同一トランザクションで upsert（`ON CONFLICT` で再実行可）。

**権限エラー**（`permission denied for table streaming_views`）: マイグレーションを `sudo -u postgres` で流すとテーブル所有者が `postgres` のままになることがある。次を一度実行する（DB ユーザー名が `planet` でない場合は置き換え）。

```bash
sudo -u postgres psql -d planet < db/fix_streaming_views_owner.sql
```

新規に `migrate_streaming_views.sql` から適用する場合は、ファイル末尾の `ALTER TABLE ... OWNER TO planet` が含まれる版を使う。

---

## アカウント・インスタンス一覧

| アカウント | 種別 | 状態 | インポート | 収集スクリプト |
|---|---|---|---|---|
| @google@msk.ilnk.info | Misskey | 運用中・非アクティブ | ○ | 登録するが収集頻度低め |
| @health@pon.icu | Misskey | **閉鎖済み** | ○ | なし（インポートのみ）|
| @health@tanoshii.site | Misskey | 運用中 | ○ | ○（通常収集）|
| @healthcare@groundpolis.app | Misskey | **閉鎖済み** | ○ | なし（インポートのみ）|
| @objtus@mastodon.cloud | Mastodon | 運用中・非アクティブ | ○ | 登録するが収集頻度低め |
| @vknsq@misskey.io | Misskey | 運用中・非アクティブ | ○ | 登録するが収集頻度低め |
| @healthcare@mistodon.cloud | Mastodon | 運用中 | ○ | ○（通常収集）|
| @idoko@sushi.ski | Misskey | 運用中 | ○ | ○（通常収集）|
| @yuinoid@misskey.io | Misskey | 運用中 | ○ | ○（通常収集）|

---

## data_sourcesテーブルへの登録方針

**閉鎖済みインスタンス**（pon.icu・groundpolis.app）は `data_sources` に登録しない。
インポート専用の archived ソースとして処理する。

**運用中（非アクティブ含む）**は全て `data_sources` に登録する。
非アクティブのものは `is_active = TRUE` のまま登録し、収集は通常通り行う
（投稿がなければ差分ゼロで終わるだけなので問題なし）。

```sql
INSERT INTO data_sources (name, type, base_url, account, is_active) VALUES
  -- 運用中（アクティブ）
  ('misskey.io @yuinoid',          'misskey',  'https://misskey.io',          '@yuinoid',    TRUE),
  ('tanoshii.site @health',        'misskey',  'https://tanoshii.site',        '@health',     TRUE),
  ('mistodon.cloud @healthcare',   'mastodon', 'https://mistodon.cloud',       '@healthcare', TRUE),
  ('sushi.ski @idoko',             'misskey',  'https://sushi.ski',            '@idoko',      TRUE),
  -- 運用中（非アクティブ）
  ('msk.ilnk.info @google',        'misskey',  'https://msk.ilnk.info',        '@google',     TRUE),
  ('mastodon.cloud @objtus',       'mastodon', 'https://mastodon.cloud',       '@objtus',     TRUE),
  ('misskey.io @vknsq',            'misskey',  'https://misskey.io',           '@vknsq',      TRUE),
  -- 閉鎖済み（インポート専用・data_sourcesには登録しない）
  -- pon.icu @health → archived_source_id で管理
  -- groundpolis.app @healthcare → archived_source_id で管理
  -- iPhone系
  ('iPhone ヘルス',                 'health',   NULL,                           NULL,          TRUE),
  ('iPhone 写真',                   'photo',    NULL,                           NULL,          TRUE);
```

### 閉鎖済みインスタンスの archived source

インポートスクリプト実行時に以下を自動作成する：

```sql
INSERT INTO data_sources (name, type, base_url, account, is_active) VALUES
  ('pon.icu @health (archived)',          'misskey',  'https://pon.icu',          '@health',     FALSE),
  ('groundpolis.app @healthcare (archived)', 'misskey', 'https://groundpolis.app', '@healthcare', FALSE)
ON CONFLICT DO NOTHING;
```

`is_active = FALSE` にすることで収集スクリプトがスキップする。

---

## JSONの共通構造

**全フォーマット（Misskey・Mastodon問わず）同一の混在パターン**を持つ。

```
JSONファイル（配列）
├── type: "Note" かつ attributedTo が自分   → 自分の通常投稿
├── type: "Note" かつ attributedTo が他者   → ブースト/リノート元の投稿
└── announce フィールドあり（typeなし）      → 自分のブースト/リノートアクション
```

ブースト元投稿とブーストアクションはペアで連続して並んでいる。

---

## 各オブジェクトの判定ロジック

```python
def classify_item(item: dict, own_account_id: str) -> str:
    """
    'own_note'    : 自分の通常投稿 → インポート対象
    'boost'       : 自分のブースト/リノート → インポート対象（区別表示）
    'boosted_note': ブースト元の他者投稿 → スキップ
    'unknown'     : 不明 → スキップ
    """
    if "announce" in item:
        return "boost"

    if item.get("type") == "Note":
        attributed_to = item.get("attributedTo", "")
        if attributed_to == own_account_id:
            return "own_note"
        else:
            return "boosted_note"

    return "unknown"
```

---

## Misskey固有の処理

### フィールドマッピング（通常投稿）

| DBカラム | JSONフィールド | 備考 |
|---|---|---|
| original_id | `id` の末尾部分 | `https://misskey.io/notes/abc123` → `abc123` |
| content | `notag` フィールド | プレーンテキスト版。なければ `content` をHTML除去 |
| url | `id` フィールドそのまま | |
| timestamp | `published` | UTC or +09:00混在 → dateutil.parser でパース |
| visibility | `to` / `cc` から判定（下記）| |

### visibilityの判定（Misskey）

```python
def get_misskey_visibility(item: dict) -> str:
    to = item.get("to", [])
    cc = item.get("cc", [])
    PUBLIC = "https://www.w3.org/ns/activitystreams#Public"

    if PUBLIC in to:
        return "public"
    elif PUBLIC in cc:
        return "home"
    else:
        return "followers"
```

### ブーストアクション（announce）のマッピング

| DBカラム | 値 |
|---|---|
| original_id | `announce` URLの末尾 |
| content | `notag` フィールド（ブースト元テキスト）|
| url | `announce` フィールドのURL |
| metadata | `{"type": "renote", "original_url": "<announce_url>"}` |

ダッシュボード表示: `RN: <content>`

---

## Mastodon固有の処理

### フィールドマッピング（通常投稿）

| DBカラム | JSONフィールド | 備考 |
|---|---|---|
| original_id | `id` の末尾数字 | `.../statuses/100568890763831149` → `100568890763831149` |
| content | `notag` フィールド | プレーンテキスト版。なければ `content` をHTML除去 |
| url | `url` フィールドそのまま | |
| timestamp | `published` | UTC形式 |
| visibility | `to` / `cc` から判定（下記）| |

### visibilityの判定（Mastodon）

```python
def get_mastodon_visibility(item: dict) -> str:
    to = item.get("to", [])
    cc = item.get("cc", [])
    PUBLIC = "https://www.w3.org/ns/activitystreams#Public"

    if PUBLIC in to:
        return "public"
    elif PUBLIC in cc:
        return "unlisted"
    else:
        return "followers"
```

### ブーストアクション（announce）のマッピング

| DBカラム | 値 |
|---|---|
| original_id | `announce` URLの末尾 |
| content | `notag` フィールド（ブースト元テキスト）|
| url | `announce` フィールドのURL |
| metadata | `{"type": "boost", "original_url": "<announce_url>"}` |

ダッシュボード表示: `BT: <content>`

---

## インポート時の重複防止

```sql
INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source_id, original_id) DO NOTHING;
```

過去JSONインポート後に通常収集スクリプトを走らせても重複しない。

---

## 実行方法（予定）

```bash
# Misskeyインスタンス
python importers/misskey_json.py \
  --file /path/to/export.json \
  --instance misskey.io \
  --account @yuinoid

# Mastodonインスタンス
python importers/mastodon_json.py \
  --file /path/to/export.json \
  --instance mastodon.cloud \
  --account @objtus

# 閉鎖済みインスタンス（archived指定）
python importers/misskey_json.py \
  --file /path/to/pon_icu_export.json \
  --instance pon.icu \
  --account @health \
  --archived
```

`--archived` フラグを付けると `is_active = FALSE` でdata_sourcesに登録される。

---

## 設定項目

`config/settings.toml` に追加：

```toml
[importer]
include_boosts = true   # ブースト/リノートをインポートするか（確定: true）
```

---

## 注意事項

- `published` のタイムゾーンが混在（UTC と +09:00）→ `python-dateutil` でパースしてUTC変換
- `notag` フィールドがある場合はそちらをプレーンテキストとして優先使用
- `content` フィールドはHTML → `BeautifulSoup` でテキスト抽出
- Misskeyの `id` は英数字のID、Mastodonの `id` は数字のID（両者で形式が異なる）
