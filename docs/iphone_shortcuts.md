# iPhoneショートカット設定手順

**対象**: Phase 4 / iPhone連携（`ingest/api.py` → `dashboard` の Blueprint `ingest_bp`）  
**エンドポイント**: `POST http://<Tailscale-IP>:5000/api/ingest`（例の固定 IP は環境に合わせて読み替え）  
**ドキュメント更新**: 2026-04-07（`health_segment` / `archive` / 写真ログ枚数の整合）

---

## 前提

- iPhone と自宅サーバーが同じ Tailscale ネットワークに参加していること
- **ingest はダッシュボードに統合済み** — 通常は **`planet-dashboard.service`** が `5000` で `POST /api/ingest` を提供する。`ingest/api.py` を更新したあと **`sudo systemctl restart planet-dashboard.service`** しないと、iPhone からは古いコードが動いたままになる
- スタンドアロンで `python ingest/api.py` を使う場合のみ `planet-ingest.service`（後述）。運用でダッシュボードだけ起動しているなら ingest 用の別サービスは不要

---

## ショートカット 1a: ヘルス（歩数・心拍）— 毎日 23:00 など

オートメーション負荷を下げるため、**指標を2本のショートカットに分割**する想定です。ダッシュボードの日タイムラインでは **同じ日に health が2行**（実行時刻がずれて表示）になります。`health_daily` は日付キーで **1行にマージ**されます。

### アクション構成

| # | アクション | 設定 |
|---|---|---|
| 1 | **ヘルスケアサンプルを検索** | 種別: 歩数 / 期間: 今日 → 変数 `steps` |
| 2 | **ヘルスケアサンプルを検索** | 種別: 安静時心拍数 / 期間: 今日 → 変数 `hr_avg` |
| 3 | **日付を書式設定** | 現在の日付 / カスタム: `yyyy-MM-dd` → 変数 `today` |
| 4 | **辞書** | 下記参照 |
| 5 | **URLのコンテンツを取得** | POST / JSON / 辞書を指定 |

### 辞書の内容（アクション 4）

| キー | 種類 | 値 |
|---|---|---|
| `source` | テキスト | `health` |
| `health_segment` | テキスト | `movement`（固定） |
| `date` | テキスト | 変数 `today` |
| `steps` | 数字 | 変数 `steps` |
| `heart_rate_avg` | 数字 | 変数 `hr_avg` |

### 自動実行

「オートメーション」→ 時刻: **23:00 / 毎日**（例）→ 「実行前に確認」を**オフ**

---

## ショートカット 1b: ヘルス（カロリー・運動）— 毎日 23:05 や 23:20 など

1a の直後〜数分後に実行すると、タイムライン上で時刻が分かれて見やすくなります（API は新しい順に並ぶため、**遅い時刻の行が上**に来ます）。

### アクション構成

| # | アクション | 設定 |
|---|---|---|
| 1 | **ヘルスケアサンプルを検索** | 種別: アクティブエネルギー / 期間: 今日 → 変数 `calories` |
| 2 | **ヘルスケアサンプルを検索** | 種別: エクササイズ時間 / 期間: 今日 → 変数 `exercise` |
| 3 | **日付を書式設定** | 現在の日付 / カスタム: `yyyy-MM-dd` → 変数 `today` |
| 4 | **辞書** | 下記参照 |
| 5 | **URLのコンテンツを取得** | POST / JSON / 辞書を指定 |

### 辞書の内容（アクション 4）

| キー | 種類 | 値 |
|---|---|---|
| `source` | テキスト | `health` |
| `health_segment` | テキスト | `activity`（固定） |
| `date` | テキスト | 変数 `today` |
| `active_calories` | 数字 | 変数 `calories` |
| `exercise_minutes` | 数字 | 変数 `exercise` |

### 自動実行

「オートメーション」→ 時刻: **23:05 または 23:20 / 毎日**（例）→ 「実行前に確認」を**オフ**

---

### （任意）1本で全部送る従来方式

`health_segment` を**付けない**と、従来どおり `logs.original_id` は **日付のみ**（1日1行）です。心拍の最大・最小などもまとめて送れます。

| # | アクション | 設定 |
|---|---|---|
| 1〜7 | 上記の各種 **ヘルスケアサンプルを検索**（歩数・アクティブエネルギー・心拍最大1件・心拍最小1件・安静時心拍・エクササイズ・スタンド） | 変数は従来どおり |
| 8 | **日付を書式設定** | `yyyy-MM-dd` → `today` |
| 9 | **辞書** | `source`=`health`, `date`=`today`, 各数値キー（**`health_segment` は書かない**） |
| 10 | **URLのコンテンツを取得** | 同上 |

---

## ショートカット 2: 写真メタデータ送信（毎日 23:06 など）

### アクション構成

| # | アクション | 設定 |
|---|---|---|
| 1 | **写真を検索** | フィルター: 作成日が今日 → 結果はそのまま使う |
| 2 | **各項目を繰り返す** | 「写真を検索」の結果 |
| 3 | （ループ内）**日付を書式設定** | 繰り返し項目.作成日 / カスタム: `yyyy-MM-dd'T'HH:mm:ssxxx` → 変数 `ts` |
| 4 | （ループ内）**テキスト** | `{"t":"[ts]","loc":"[繰り返し項目.位置情報]"}` → **変数に追加** `items` |
| 5 | **繰り返しの終了** | |
| 6 | **テキストを結合** | 変数 `items` / セパレーター: `,`（カンマ）→ 変数 `joined` |
| 7 | **テキスト** | `[` + 変数 `joined` + `]` → 変数 `photos_json` |
| 8 | **日付を書式設定** | 現在の日付 / カスタム: `yyyy-MM-dd` → 変数 `today` |
| 9 | **辞書** | 下記参照 |
| 10 | **URLのコンテンツを取得** | POST / JSON / 辞書を指定 |

### 辞書の内容（アクション 9）

| キー | 種類 | 値 |
|---|---|---|
| `source` | テキスト | `photo` |
| `date` | テキスト | 変数 `today` |
| `count` | 数字 | `0`（ダミー。実際の枚数はサーバー側で photo_json から算出）|
| `photo_json` | テキスト | 変数 `photos_json` |

### 動作の詳細

- ループ内で写真ごとに JSON テキスト `{"t":"タイムスタンプ","loc":"位置情報"}` を作り、`変数に追加` で積み上げる
- 位置情報がない写真は `"loc":""` になり、サーバー側でスキップ（`photo_locations` の要素には載らない）
- 位置情報がある写真は住所文字列（例: `愛知県 安城市 東端町...`）として **`health_daily.photo_locations`**（JSONB）に保存
- 住所中の改行はサーバー側でスペースに変換して保存
- **`count` は `0` ダミーでよい**。サーバーは **`photo_json` をパースした要素数**を `health_daily.photo_count` と **`logs` の本文（`写真 N枚`）および `metadata.count`** に使う（2026-04 修正。以前は `logs` だけダミーのまま残る不整合があった）

### 自動実行

「オートメーション」→ `+` → 時刻: **23:06 / 毎日**（ヘルス 1a/1b と重ならない時刻）→ 「実行前に確認」を**オフ**

---

## ショートカット 3: Jomo スクリーンタイム（毎日 23:10 など）

[Jomo](https://jomo.so/) の「Get today's screen time」アクションで取得した**秒数（整数）**を送信する。

### アクション構成（例）

| # | アクション | 設定 |
|---|---|---|
| 1 | **Get today's screen time**（Jomo） | → 変数 `seconds` |
| 2 | **日付を書式設定** | 現在の日付 / カスタム: `yyyy-MM-dd` → 変数 `today` |
| 3 | **辞書** | 下記参照 |
| 4 | **URLのコンテンツを取得** | POST / JSON / 辞書を指定 |

### 辞書の内容

| キー | 種類 | 値 |
|---|---|---|
| `source` | テキスト | `screen_time` |
| `date` | テキスト | 変数 `today`（`yyyy-MM-dd` 推奨） |
| `screen_time_seconds` | 数字 | 変数 `seconds`（Jomo の返り値） |

- `date` に ISO 日時（例: `2026-03-31T12:02:16+09:00`）を渡しても、サーバー側で **JST の暦日** に正規化して `logs.original_id` / `health_daily.date` に使う。
- エンドポイントはヘルス送信と同じ `POST .../api/ingest` でよい。
- 「Share Across Devices」をオフにしないと、複数デバイスの合算になる（Apple の挙動）。

### 自動実行

「オートメーション」→ 時刻: **23:10 / 毎日**（ヘルス・写真の直後など）→ 「実行前に確認」を**オフ**

---

## API 仕様（実装済み）

### ヘルスデータ

**分割送信（推奨）** — `health_segment` に `movement` または `activity` を付けると、その束専用の `logs` 行になります（`original_id` は `YYYY-MM-DD#movement` / `YYYY-MM-DD#activity`）。`health_daily` は日付で1行のまま、未送信の列は既存値を保持します。

```json
{
  "source": "health",
  "health_segment": "movement",
  "date": "2026-03-23",
  "steps": 8342,
  "heart_rate_avg": 72
}
```

```json
{
  "source": "health",
  "health_segment": "activity",
  "date": "2026-03-23",
  "active_calories": 420,
  "exercise_minutes": 35
}
```

**1本でまとめる（従来）** — `health_segment` を省略すると `original_id` は日付のみ（1日1行）。

```json
{
  "source": "health",
  "date": "2026-03-23",
  "steps": 8342,
  "active_calories": 420,
  "heart_rate_avg": 72,
  "heart_rate_max": 135,
  "heart_rate_min": 52,
  "exercise_minutes": 35,
  "stand_hours": 10
}
```

- `active_calories` は小数でも整数に丸めて保存
- `heart_rate_max` / `heart_rate_min` は **DB の `health_daily` にのみ**保存し、タイムライン本文には出しません（従来どおり）
- タイムライン用本文が空になるリクエスト（数値キーがすべて欠けている等）は **400**（`0` や `heart_rate_avg: 0` は有効）
- `date` の代わりに `dates` を送っても受け付ける（ショートカット設定の typo 対応）
- `date` は **`YYYY-MM-DD` または ISO 8601 日時** — サーバー側で **JST の暦日**に正規化してから `original_id` / `health_daily.date` に使う（手動バックフィルで日時を渡してもよい）

**過去分の手動送信（`archive`）** — 通常は `logs.timestamp` が**受信時刻**のため、過去の `date` を送ってもカレンダーの**その日**のタイムラインには載りません。手動バックフィル用に **`archive`** を真にすると、`logs.timestamp` を **`date` の JST 夜**に固定します（ダッシュボードの日ビューでその日に表示される）。

| `archive` の例 | 扱い |
|---|---|
| `true` / `"on"` / `"yes"` / `1` | アンカー有効 |
| 省略 / `false` / `"off"` / `0` | 従来どおり受信時刻 |

- **時刻**: `health_segment` が `movement` のとき **JST 23:49**、それ以外（`activity` または分割なし）は **JST 23:50**（同一日に2行並べるときの順序用）
- `metadata` に `archive_timeline: true` を付与（あとから識別可能）
- レスポンス JSON に `archive_timeline: true/false` を含む
- **注意**: 毎日のオートメーションでは **`archive` を付けない**こと（常に「あの日の23:50」扱いになり、実際の送信日時とずれる）
- 分割送信で過去日を埋める例: `health_segment` と `archive` を**両方**指定し、ヘルスケアの検索期間と JSON の `date` を**同じ暦日**にそろえる

```json
{
  "source": "health",
  "archive": "yes",
  "health_segment": "movement",
  "date": "2026-01-07",
  "steps": 8200,
  "heart_rate_avg": 65
}
```

### Jomo スクリーンタイム

```json
{
  "source": "screen_time",
  "date": "2026-03-30",
  "screen_time_seconds": 18000
}
```

- `screen_time_seconds` は 0〜172800（2日分まで）の整数
- `date` は `YYYY-MM-DD` 推奨。ISO 日時でも可（サーバーが JST の日付に正規化）
- DB: `data_sources.type = 'screen_time'` のソースに紐づく `logs` 1件／日と、`health_daily.screen_time_seconds` の更新（日付キーでマージ）

**DB マイグレーション**（初回のみ）: `sudo -u postgres psql -d planet < db/migrate_jomo_screen_time.sql`（リポジトリルートから。`-f` でホーム配下を渡すと `postgres` が読めず Permission denied になりやすい）

### 写真メタデータ

```json
{
  "source": "photo",
  "date": "2026-03-23",
  "count": 0,
  "photo_json": "[{\"t\":\"2026-03-23T16:49:48+09:00\",\"loc\":\"\"},{\"t\":\"2026-03-23T17:22:20+09:00\",\"loc\":\"愛知県 安城市...\"}]"
}
```

- `photo_json` / `photos_json` どちらのキー名でも受け付ける
- 実際の枚数は `photo_json` の要素数からサーバーが算出し、**`health_daily` と `logs` の表示を一致**させる（上記「写真メタデータ送信」参照）

---

## 動作確認（curl）

```bash
# ヘルス（分割・movement）
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","health_segment":"movement","date":"2026-03-23","steps":8000,"heart_rate_avg":72}'

# ヘルス（分割・activity）
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","health_segment":"activity","date":"2026-03-23","active_calories":400,"exercise_minutes":30}'

# ヘルス（1本・従来）
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","date":"2026-03-23","steps":8000,"active_calories":400,"heart_rate_avg":72,"heart_rate_max":130,"heart_rate_min":55,"exercise_minutes":30,"stand_hours":9}'

# ヘルス（過去日を手動送信 → その日のタイムラインに載せる）
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","archive":"on","date":"2026-03-20","steps":7000,"heart_rate_avg":70}'

# ヘルス（分割・過去日・タイムラインもその日に載せる）
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","archive":"yes","health_segment":"activity","date":"2026-03-20","active_calories":300,"exercise_minutes":25}'

# Jomo スクリーンタイム
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"screen_time","date":"2026-03-30","screen_time_seconds":18000}'

# DB確認
PGPASSWORD=password psql -U planet -h localhost -d planet \
  -c "SELECT date, steps, heart_rate_avg, screen_time_seconds, photo_count FROM health_daily ORDER BY date DESC LIMIT 5;"
```

---

## systemd による常時起動

```bash
sudo tee /etc/systemd/system/planet-ingest.service << 'EOF'
[Unit]
Description=Planet Ingest API
After=network.target postgresql.service

[Service]
User=objtus
WorkingDirectory=/home/objtus/planet
ExecStart=/home/objtus/planet/venv/bin/python ingest/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable planet-ingest
sudo systemctl start planet-ingest
sudo systemctl status planet-ingest
```

> Phase 5 以降は **`ingest_bp` は `dashboard/app.py` に統合済み**。運用の主経路は **`planet-dashboard.service`**。スタンドアロン `planet-ingest.service` は開発・検証用のオプション。

---

## 変更履歴（ingest まわり・要約）

| 時期 | 内容 |
|---|---|
| 2026-04 | **ヘルス** `health_segment`: `movement` / `activity` で同日に `logs` を最大2行（`original_id` に `#movement` / `#activity`）。`health_daily` は日付キーで COALESCE マージ |
| 2026-04 | **ヘルス** `archive`: 手動過去投入時に `logs.timestamp` を `date` の JST 23:49（movement）または 23:50（activity・非分割）に固定。応答に `archive_timeline`。`metadata.archive_timeline` |
| 2026-04 | **写真** `photo_json` 由来の枚数を **`logs` の「写真 N枚」および `metadata.count`** にも反映（`count: 0` ダミーと整合） |
| 2026-04 | **ヘルス** `date` を受信時に JST 暦日へ正規化（ISO 日時可） |
