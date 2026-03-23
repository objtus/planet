# iPhoneショートカット設定手順

**対象**: Phase 4 / iPhone連携  
**エンドポイント**: `POST http://100.75.72.93:5000/api/ingest`  
**動作確認日**: 2026-03-23

---

## 前提

- iPhoneと自宅サーバーが同じ Tailscale ネットワークに参加していること
- `planet-ingest.service` が systemd で起動していること（後述）

---

## ショートカット 1: ヘルスデータ送信（毎日 23:00）

### アクション構成

| # | アクション | 設定 |
|---|---|---|
| 1 | **ヘルスケアサンプルを検索** | 種別: 歩数 / 期間: 今日 → 変数 `steps` |
| 2 | **ヘルスケアサンプルを検索** | 種別: アクティブエネルギー / 期間: 今日 → 変数 `calories` |
| 3 | **ヘルスケアサンプルを検索** | 種別: 心拍数 / 並び替え: 値（降順）/ 上限: 1 → 変数 `hr_max` |
| 4 | **ヘルスケアサンプルを検索** | 種別: 心拍数 / 並び替え: 値（昇順）/ 上限: 1 → 変数 `hr_min` |
| 5 | **ヘルスケアサンプルを検索** | 種別: 安静時心拍数 / 期間: 今日 → 変数 `hr_avg` |
| 6 | **ヘルスケアサンプルを検索** | 種別: エクササイズ時間 / 期間: 今日 → 変数 `exercise` |
| 7 | **ヘルスケアサンプルを検索** | 種別: スタンド時間 / 期間: 今日 → 変数 `stand` |
| 8 | **日付を書式設定** | 現在の日付 / カスタム: `yyyy-MM-dd` → 変数 `today` |
| 9 | **辞書** | 下記参照 |
| 10 | **URLのコンテンツを取得** | POST / JSON / 辞書を指定 |

### 辞書の内容（アクション 9）

| キー | 種類 | 値 |
|---|---|---|
| `source` | テキスト | `health` |
| `date` | テキスト | 変数 `today` |
| `steps` | 数字 | 変数 `steps` |
| `active_calories` | 数字 | 変数 `calories` |
| `heart_rate_avg` | 数字 | 変数 `hr_avg` |
| `heart_rate_max` | 数字 | 変数 `hr_max` |
| `heart_rate_min` | 数字 | 変数 `hr_min` |
| `exercise_minutes` | 数字 | 変数 `exercise` |
| `stand_hours` | 数字 | 変数 `stand` |

### URLのコンテンツを取得の設定

- URL: `http://100.75.72.93:5000/api/ingest`
- メソッド: `POST`
- 本文: `JSONを使用` → 上記辞書

### 自動実行

「オートメーション」→ `+` → 時刻: **23:00 / 毎日** → 「実行前に確認」を**オフ**

---

## ショートカット 2: 写真メタデータ送信（毎日 23:05）

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
- 位置情報がない写真は `"loc":""` になり、サーバー側でスキップ
- 位置情報がある写真は住所文字列（例: `愛知県 安城市 東端町...`）として保存
- 住所中の改行はサーバー側でスペースに変換して保存

### 自動実行

「オートメーション」→ `+` → 時刻: **23:05 / 毎日** → 「実行前に確認」を**オフ**

---

## API 仕様（実装済み）

### ヘルスデータ

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
- `date` の代わりに `dates` を送っても受け付ける（ショートカット設定の typo 対応）

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
- 実際の枚数は `photo_json` の要素数からサーバーが算出

---

## 動作確認（curl）

```bash
# ヘルスデータ
curl -X POST http://100.75.72.93:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"health","date":"2026-03-23","steps":8000,"active_calories":400,"heart_rate_avg":72,"heart_rate_max":130,"heart_rate_min":55,"exercise_minutes":30,"stand_hours":9}'

# DB確認
PGPASSWORD=password psql -U planet -h localhost -d planet \
  -c "SELECT date, steps, heart_rate_avg, photo_count FROM health_daily ORDER BY date DESC LIMIT 5;"
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

> Phase 5（ダッシュボード）実装後は `ingest_bp` を `dashboard/app.py` に統合し、`planet-ingest.service` は廃止予定。
