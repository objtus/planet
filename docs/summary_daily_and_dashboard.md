# 日次要約の保存とダッシュボード表示

**最終更新**: 2026-03-26

週次を **階層パイプライン**（`--pipeline hierarchical`）で生成するときの日次要約を `summaries` に保存し、カレンダー日ビューとサマリー一覧から辿れるようにする設計。

**関連**: [`summary_integration_plan.md`](summary_integration_plan.md)、[`hierarchical_summary_plan.md`](hierarchical_summary_plan.md)、`summarizer/generate.py`

---

## 1. データ契約

| 項目 | 内容 |
|------|------|
| `period_type` | `'daily'` |
| `period_start` | 対象日（JST 暦日、`DATE`） |
| `period_end` | **同一日**（暦日の区切りを表す。実際の生成時刻は `created_at`） |
| `week_number` | `NULL` |
| `content` | 日次テンプレートに従った Markdown（`###` 見出しから始まる本文） |
| `prompt_style` | 例: `hybrid_hierarchical_daily` |
| UNIQUE | `(period_type, period_start)` — 1 日 1 行 |

**注意**: 「23:59 に生成したことにする」必要はない。**いつの日のサマリーか**は `period_start`、**いつ DB に書いたか**は `created_at`。

---

## 2. 生成（CLI）

- **`--period day --date YYYY-MM-DD`**: その暦日の日次要約だけを LLM で作り **`upsert_daily`**（週次でその日を再利用する際にヒットする）。
- 週次 hierarchical で、ログがある日は LLM のあと **`upsert_daily`**（未キャッシュ時）。
- プレースホルダのみ（生成失敗・空など）のときは **行を保存しない**（既存行は `ON CONFLICT` で上書きされないケースあり）。
- ログが無い日は **`delete_daily_summary`** で古い日次行を削除（週再生成で空になった場合の掃除）。
- **既定**: その日の `daily` 行が既にあれば **LLM をスキップして再利用**（週次マージのみ再実行）。
- **`--regenerate-daily`**: 7 日ともログがある日は毎回 LLM で作り直す。

---

## 3. ダッシュボード

### `/summaries`（一覧）

- クエリは **`period_type IN ('weekly', 'monthly')` のみ**（日次は件数が多くなるため一覧に出さない）。
- **週次行**の直下に、その週の **7 日分のリンク**（`M/D(曜)`）を表示。
- リンク先: **`/?view=day&date=YYYY-MM-DD`**（トップ＝カレンダー）。読み込み後クエリは `replaceState` で除去。

### カレンダー日ビュー

- `GET /api/summary?period=day&date=YYYY-MM-DD` で日次を取得。
- `#summary-panel` に **「日次サマリー」**として表示（週・月と同じ Markdown レンダリング）。
- **`この日の日次を生成` ボタン** → `POST /api/summaries/generate`（`period: "day"`, `date: "YYYY-MM-DD"`）。週次生成より軽く、先に日次を溜めてから週次を回す運用が可能。

### タイムアウト（ダッシュボード経由）

- 週次階層は LLM 呼び出しが多いため、子プロセスは **最大約 5 時間**（`subprocess.run`）、各 Ollama 呼び出しは **`--timeout 1800`（30 分）** を付与。
- ブラウザ側 `fetch` の中断も週・月は **5 時間**、日次は **2 時間**。

### API

- `GET /api/summary` の `period` に **`day`** を追加（`date` は `YYYY-MM-DD`）。

---

## 4. 将来の拡張（メモ）

- 日次の Neocities 公開は既定オフ想定（一覧に出さないため誤トグルしにくい）。
- ログ変更検知で日次だけ無効化するには `source_digest` 列などを後付け可能。
