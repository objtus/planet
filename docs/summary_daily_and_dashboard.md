# サマライザー設計・ダッシュボード連携

**最終更新**: 2026-04-18

トピック別パイプラインの設計、DB契約、ダッシュボード連携をまとめた仕様書。

**関連**: `docs/phase6_plan.md`（Phase 6 全体）、`docs/summarizer_quality_plan.md`（設計背景）、`summarizer/generate.py`

---

## 1. トピック別パイプライン概要

日次生成を **7トピック** に分割し、各々専用プロンプトで個別に LLM 呼び出しする。週次・月次ではこれらを統合する。

### 日次トピック一覧

| `summary_type` | 日本語ラベル | 入力ソース | プロンプト |
|---|---|---|---|
| `music` | 音楽 | `lastfm`（直接クエリ）＋ SNS 音楽関連 | `daily_music.txt` |
| `media` | メディア | `netflix`、`prime`、SNS 視聴/作品言及 | `daily_media.txt` |
| `health` | 健康 | `health`、`photo`、`screen_time` | `daily_health.txt` |
| `sns` | SNS | `misskey`、`mastodon` | `daily_sns.txt` |
| `dev` | 開発 | `github` | `daily_dev.txt` |
| `behavior` | 行動傾向 | （補助トピック、`full` 生成の文脈補完用） | `daily_behavior.txt` |
| `full` | 日記まとめ | 上記トピックの日次サマリーを統合 | `daily_full.txt` |
| `oneword` | 一言 | `full` サマリーをもとに生成 | `oneword.txt` |

週次専用:

| `summary_type` | 日本語ラベル | 入力 | プロンプト |
|---|---|---|---|
| `best_post` | ベスト投稿 | 週の生 SNS ログ | `best_post.txt` |

---

## 2. データ契約（`summaries` テーブル）

| 項目 | 内容 |
|---|---|
| `period_type` | `'daily'` / `'weekly'` / `'monthly'` |
| `period_start` | 日次: 対象日（JST 暦日）。週次: 月曜日。月次: 月初日 |
| `period_end` | 日次: 同日。週次: 日曜日。月次: 月末日 |
| `summary_type` | `'music'` / `'media'` / `'health'` / `'sns'` / `'dev'` / `'full'` / `'oneword'` / `'best_post'` |
| `week_number` | 週次: ISO 週番号。日次・月次: NULL |
| `content` | Markdown 本文 |
| `prompt_style` | 生成時のプロンプトスタイル識別子 |
| `model` | 使用 LLM モデル名 |
| UNIQUE | `(period_type, period_start, summary_type)` — CONSTRAINT `summaries_unique` |

**注意**: 「いつの日のサマリーか」は `period_start`、「いつ DB に書いたか」は `created_at`。

マイグレーション: `db/migrate_summary_type.sql`（テーブル所有者 `postgres` で実行）。

---

## 3. CLIオプション

```bash
# 日次生成（7トピック）
./venv/bin/python -m summarizer.generate --period day --date YYYY-MM-DD

# 週次生成（日次再利用 + best_post）
./venv/bin/python -m summarizer.generate --period week --date YYYY-Www

# 月次生成
./venv/bin/python -m summarizer.generate --period month --date YYYY-MM

# 既存日次を無視して再生成
./venv/bin/python -m summarizer.generate --period day --date YYYY-MM-DD --regenerate-daily

# 旧 hierarchical パイプライン（互換維持）
./venv/bin/python -m summarizer.generate --period week --date YYYY-Www --legacy

# 入力内容をプレビュー（LLM 呼び出しなし）
./venv/bin/python -m summarizer.generate --period day --date YYYY-MM-DD --dry-run
```

---

## 4. コンテキスト取得の実装（`summarizer/context.py`）

### `TOPIC_SOURCE_TYPES`

```python
TOPIC_SOURCE_TYPES = {
    "music":  ["lastfm", "misskey", "mastodon"],
    "media":  ["netflix", "prime", "misskey", "mastodon"],
    "health": ["health", "photo", "screen_time"],
    "sns":    ["misskey", "mastodon"],
    "dev":    ["github"],
}
```

### 主要関数

| 関数 | 用途 |
|---|---|
| `fetch_topic_digest_for_day(conn, date, source_types, ...)` | 日次ログを `source_types` でフィルタして整形 |
| `fetch_topic_digest_for_week(conn, week_start, source_types, ...)` | 週次ログ取得 |
| `fetch_lastfm_digest_for_day(conn, date)` | `lastfm_plays` を直接クエリし `[HH:MM] Artist - Track (Album)` 形式で返す |
| `get_source_name_map(conn)` | `data_sources.id → name` の辞書を返す |
| `_format_digest_line(row, include_id, source_name_map)` | ログ行を `[HH:MM] (ソース名) content` に整形 |

### ソース名マッピング

LLM への入力行で数値 ID ではなく人間可読名を使用する。SNS・music・media トピック適用。

例: `[14:23] (tanoshii.site @health) 今日も電気グルーヴ聴いてる`

### Last.fm 直接クエリの背景

`logs.content` には YouTube スクロブルが「チャンネル名 - 動画タイトル」形式で混入し LLM が音楽と判別できない問題があった。`lastfm_plays` テーブルの `artist`/`track`/`album` カラムを直接使うことで解決。

---

## 5. `music` トピックの入力形式

音楽トピックは Last.fm と SNS を明示的にセクション分割して LLM に渡す：

```
--- Last.fm 再生ログ ---
[14:23] The Beatles - Let It Be (Let It Be)
[14:27] ジョン・レノン - Imagine (Imagine)
...

--- SNS 投稿ログ ---
[22:31] (tanoshii.site @health) 電気グルーヴのライブ映像みてる
...
```

---

## 6. `best_post` 生成の仕組み（週次専用）

1. 週の生 SNS ログ（`include_id=True` で `[id=数字 日時]` 形式）を LLM に渡す
2. LLM が `BEST_ID: <数値>` と `REASON: <理由>` を出力
3. コードが DB から `logs.content` を取得して最終出力を構成
4. `REASON` が省略された場合は第2回 LLM 呼び出しで理由を生成

プロンプト形式（`best_post.txt`）はハルシネーション防止のため ID と理由のみを要求し、実文取得はコードが担う。

---

## 7. ダッシュボード API

| エンドポイント | 説明 |
|---|---|
| `GET /api/summary/topics?period=day&date=YYYY-MM-DD` | 日次全トピック取得 |
| `GET /api/summary/topics?period=week&date=YYYY-Www` | 週次全トピック取得 |
| `GET /api/summary/topics?period=month&date=YYYY-MM` | 月次全トピック取得 |
| `GET /api/summary?period=day&date=YYYY-MM-DD` | 日次 `full` サマリー取得（旧互換） |
| `POST /api/summaries/generate` | サマリー生成（`period`, `date`, `regenerate: true` で強制再生成） |
| `GET /api/prompts` | プロンプトファイル一覧 |
| `GET /api/prompts/<name>` | プロンプトファイル取得 |
| `POST /api/prompts/<name>` | プロンプトファイル保存 |
| `GET /api/settings` | 設定取得 |
| `POST /api/settings` | 設定更新 |

---

## 8. ダッシュボード表示仕様

### 日次（カレンダー日ビュー）

- `oneword` を冒頭バッジで表示
- `full` を最上段に表示
- `music` / `media` / `health` / `sns` / `dev` をアコーディオンで折りたたみ表示
- 「この日の日次を生成」ボタン → サマリー未生成時に表示
- 「強制再生成」ボタン → サマリー生成済み時に表示（確認ダイアログ付き）

### 週次（カレンダー週ビュー）

- `oneword` バッジ
- `full` 本文
- `best_post` 専用カード（`.summary-best-post-card`）
- 各トピックをアコーディオンで折りたたみ

### `/summaries` 一覧

- `period_type IN ('weekly', 'monthly')` かつ `summary_type = 'full'` のみ表示
- 週次行の下に7日分リンク（`/?view=day&date=YYYY-MM-DD`）

---

## 9. タイムアウト設定

| 対象 | タイムアウト |
|---|---|
| 各 Ollama 呼び出し | `--timeout 1800`（30分） |
| 子プロセス全体（週次） | 最大約5時間 |
| ブラウザ `fetch`（週・月） | 5時間 |
| ブラウザ `fetch`（日次） | 2時間 |

---

## 10. キャッシュ・再生成ルール

- **既定**: その日・トピックの `daily` 行が既にあれば LLM スキップして再利用
- **`--regenerate-daily`**: 全トピックを強制再生成
- **ダッシュボードから強制再生成**: `POST /api/summaries/generate` に `regenerate: true`
- **旧スタイル検知**: `prompt_style = 'hybrid_hierarchical_daily'` の行は自動的に再生成対象
