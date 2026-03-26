# Phase 6: AI 生成・公開 — 実装プラン

**最終更新**: 2026-03-26（M2 計画・タスク分解を追記）

**前提**: Phase 5 のダッシュボードは機能完成扱い。`summaries` の閲覧・カレンダー連携・公開トグル・`GET /api/summary` は実装済み（契約は `docs/summary_integration_plan.md`）。本フェーズでは **行の自動生成** と **Neocities への反映** を追加する。

**階層要約（日→週→月→年）**: 週次の **1 本あたりプロンプト肥大**や将来の月次・年次を見据えたパイプラインは **`docs/hierarchical_summary_plan.md`** に集約。M1 の「生ログ一括」方式と併存・移行する想定。

---

## 1. ゴールと非ゴール

| ゴール | 非ゴール（バックログまたは Phase 7） |
|--------|--------------------------------------|
| 週次・月次サマリーを Ollama で生成し `summaries` に保存 | YouTube 収集有効化、mastodon.cloud 不調の調査 |
| プロンプトをファイル管理し、モデル名は設定で切替 | カレンダー mockup 完全一致・iPhone レイアウトの徹底調整 |
| `is_published=true` の週次（必要なら月次）を Neocities に HTML で公開 | ダッシュボードへのログイン認証 |
| 過去期間の一括生成（バッチ） | 画像のローカル保存パイプライン |
| （設計どおり）Planet ページの DB 駆動 HTML 生成 | Phase 7 の cron 統合・バックアップ本番化（Phase 6 で必要最小限の cron 案だけ書いてよい） |

---

## 2. データ契約（生成側は既存どおり厳守）

`summary_integration_plan.md` とダッシュボード API と一致させる。

- **`period_type`**: `'weekly'` / `'monthly'` のみ（まずはこの2種）。
- **週次**: `period_start` = その ISO 週の**月曜**（JST の日付）、`period_end` = **日曜**。`week_number` = ISO 週番号（表示・API の `YYYY-Www` と同じ週の解釈に揃える）。
- **月次**: `period_start` = 月の **1 日**、`period_end` = **月末**。
- **保存**: `INSERT ... ON CONFLICT (period_type, period_start) DO UPDATE` で再生成に対応。`model`・`prompt_style`（例: `hybrid`）を記録。
- **初回・空データ**: `content` は NOT NULL のため、生成失敗時はプレースホルダかスキップ方針をコードで明示（一覧・カレンダーは既に「まだありません」表示あり）。

公開ページ用のプロンプト素材は `design.md` §8 に沿う。**Fediverse は public 以外を Neocities 向けテキストに含めない**（`misskey_posts` / `mastodon_posts` の `visibility` を JOIN して除外するなど。ダッシュボード用の全文生成と URL 用を分けるか、1 本のプロンプトで「公開用段落のみ出力」にするかは実装時に選択）。

---

## 3. マイルストーン（推奨順）

### M1 — 週次 1 本のパイプライン（最優先）

目的: 手動コマンド 1 回で「指定期間の週」が DB に入り、カレンダー週ビューに表示される。

1. **ディレクトリ**（`design.md` §12 と整合）  
   - `summarizer/__init__.py`（空で可）  
   - `summarizer/generate.py` — CLI（例: `--period week --date 2026-W12` または ISO 年+週）  
   - `summarizer/prompts/weekly_hybrid.txt` — プレースホルダ付きテンプレ  
   - 共通処理は `summarizer/db.py` や `summarizer/context.py` に切り出してもよい（小さく始めて肥大時に分割）。

2. **入力（コンテキスト）**  
   - 指定期間の `logs`（`is_deleted=FALSE`）を時系列で取得。ソース種別に応じて `content`・`metadata`・関連テーブルから要約用の平文を組み立てる。  
   - 件数上限・トークン上限を見積もり、超える場合は直近優先やセクション別サンプリング（実装コメントで方針を残す）。  
   - **週次**: `--pipeline flat`（生ログ一括・日別均等サンプル）と **`--pipeline hierarchical`（既定）** の **日次7回→週マージ1回** を `summarizer/generate.py` で選択可能。詳細は **`docs/hierarchical_summary_plan.md`**。

3. **Ollama**  
   - HTTP: `POST http://<host>:11434/api/generate`（または chat API。モデルが chat 専用ならそちら）。  
   - 接続先・モデル名は `config/settings.toml` に追加（例: `[ollama] host`, `model`）。既存の `design.md` の「model で切替」と整合。  
   - 依存: リポジトリに `requests` 済みならそれを利用。

4. **出力**  
   - 生成テキストを `summaries` に UPSERT。`is_published` は既存行を尊重（`ON CONFLICT` 時に `is_published` を上書きしない）。

**完了条件**: ローカルで 1 週分実行 → `/summaries` とカレンダー週ビューのパネルに表示。

#### M1 タスク分解（実装順）

以下は **上から順に着手しやすい** 並び。並列可能なものは注記する。

| ID | タスク | 内容・成果物 | 依存 |
|----|--------|----------------|------|
| **1.1** | 設定スキーマ | `config/settings.toml.example` に `[ollama]` を追加（例: `host = "http://127.0.0.1:11434"`、`model = "gemma3:12b"`）。実機の `settings.toml` には手動で同ブロックを追記（git に載せない）。 | なし |
| **1.2** | パッケージ配置 | `summarizer/__init__.py` を作成（空または短い docstring）。リポジトリルートから `python -m summarizer.generate ...` または `python summarizer/generate.py` のどちらか一方に統一し、**README または本ファイルに実行例 1 行**を残す。 | 1.1 |
| **1.3** | CLI 引数と ISO 週 | `argparse` で `--period week`（M1 では week のみ必須）と `--date YYYY-Www`（大文字小文字許容）を受け取る。`datetime.strptime(f"{y}-{w:02d}-1", "%G-%V-%u").date()` で **月曜**を得て `period_start` / **日曜**を `period_end` にし、`week_number` を ISO 週番号に設定（`app.py` の週キーと同一解釈）。無効な `--date` は終了コード非 0 でメッセージ。 | 1.2 |
| **1.4** | 時間窓（JST） | 集計用に「その週の月曜 00:00 JST」〜「翌週月曜 00:00 JST 未満」の `timestamptz` 範囲を決める（`logs.timestamp` は UTC 保存想定）。`zoneinfo` または既存コードと同じ `Asia/Tokyo` の扱いに揃える。 | 1.3 |
| **1.5** | DB 接続 | `tomllib` で `settings.toml` を読み、`psycopg2` で接続する薄いヘルパ（`summarizer/db.py` など）。ダッシュボードと **同一ファイル**を参照する前提を docstring に書く。 | 1.1 |
| **1.6** | コンテキスト取得 v1 | 上記 JST 範囲で `logs` を `is_deleted=FALSE`、`timestamp` 昇順で取得。各行を **1 行テキスト**に整形（例: `[YYYY-MM-DD HH:MM] (source_id) content の先頭 N 文字`）。件数が多い場合は **直近 K 件に制限**し、コメントで「M3/M4 で拡張」と明記。M1 では visibility フィルタは **未実装でも可**（Neocities 向けは M4 以降で厳密化）。 | 1.4, 1.5 |
| **1.7** | プロンプトテンプレ | `summarizer/prompts/weekly_hybrid.txt` を追加。プレースホルダ例: `{{ACTIVITY_DIGEST}}`（1.6 の平文）、`{{WEEK_LABEL}}`（人間可読の週ラベル）。`design.md` §7 の見出し構成に近づけるが、M1 は「動く」ことを優先。 | 1.2 |
| **1.8** | Ollama 呼び出し | `requests.post(f"{host}/api/generate", json={...})` で `model` と `prompt` を渡し、レスポンスから `response` フィールドを取り出す。タイムアウト・HTTP エラー・JSON 異常時は **stderr に理由**を出して非 0 終了。stream=false でよい。 | 1.1 |
| **1.9** | UPSERT | `INSERT INTO summaries (period_type, period_start, period_end, week_number, content, model, prompt_style) VALUES ('weekly', ...)` + `ON CONFLICT (period_type, period_start) DO UPDATE SET period_end=EXCLUDED.period_end, week_number=EXCLUDED.week_number, content=EXCLUDED.content, model=EXCLUDED.model, prompt_style=EXCLUDED.prompt_style`。**`is_published` / `published_at` は UPDATE 句に含めない**（既存値を保持）。 | 1.5, 1.3, 1.8 |
| **1.10** | 空データ方針 | 1.6 の結果が 0 件のとき: (A) Ollama を呼ばず終了コード 0 でスキップ、または (B) 固定短文を `content` に UPSERT、のどちらかをコードとコメントで固定。推奨は **(A) スキップ**（ダッシュボードは「まだありません」のまま）。 | 1.6, 1.9 |
| **1.11** | 結線と動作確認 | `generate.py` で 1.3→1.6→1.7→1.8→1.9 を直列実行。実 DB でデータがある週を 1 つ選び実行 → `psql` または `/summaries`・カレンダー週ビューで表示確認。再実行で本文だけ差し替わり、`is_published` が変わらないことを確認。 | 1.3–1.10 |

**並列作業の例**: 1.5（DB）と 1.7（プロンプト文言）は 1.2 後なら別担当が同時に進められる。1.8（Ollama）は 1.6 と並行可能（結線前まで）。

**M1 のスコープ外（明示的に後回し）**: 月次 CLI、バッチ、Neocities、visibility 厳密フィルタ、トークン数に基づく動的トリミング（コメント TODO でよい）。

**実行例（リポジトリルート）**:

```bash
# システムの python3 ではなく、プロジェクト venv を使う（psycopg2 が入っている）
./venv/bin/python -m summarizer.generate --period week --date 2026-W12
```

`config/settings.toml` に `[database]` と `[ollama]`（`base_url`, `model`）が必要。ログ 0 件の週は終了コード 0 でスキップ。

### M2 — 月次パイプライン

**実装済み（2026-03-26）**: `summarizer/month_bounds.py`、`prompts/monthly_hybrid.txt`、`generate.py` の `--period month`、`fetch_activity_digest(..., max_lines=8000)`（`context.MAX_LOG_LINES_MONTHLY`）。

目的: 手動コマンド 1 回で「指定した暦月」の `monthly` 行が `summaries` に入り、**カレンダー月ビュー**と **`GET /api/summary?period=month&date=YYYY-MM`**・`/summaries` と整合する。

#### M2 と M1 の関係（再利用）

| 部品 | 月次での扱い |
|------|----------------|
| `summarizer/db.py` / `load_config` / `get_conn` | そのまま |
| `summarizer/ollama_client.py` | そのまま |
| `summarizer/context.fetch_activity_digest` | キーワード `max_lines` を追加。月次は **`MAX_LOG_LINES_MONTHLY`（8000）**、週次は従来 **2000** |
| 件数上限 | 実装: 月は 8000 件・週は 2000 件（直近優先の偏りを緩和） |
| 週次の `finalize_weekly_markdown` / 先頭 `#`・`##` 剥がし | **月次用に同等の関数**を追加（例: `## 月次サマリー（…）` を機械付与。モデルに H2 を書かせない） |

#### M2 で新規に必要なもの

1. **月の日付境界**  
   - `period_start` = その月 **1 日**（`date`）、`period_end` = **月末**（`calendar.monthrange` 等）。  
   - **JST** で「当月 1 日 00:00」〜「翌月 1 日 00:00 未満」を UTC の aware `datetime` にし、`logs.timestamp` と比較（週次の `week_bounds.py` と同じ `Asia/Tokyo` 方針）。

2. **CLI**  
   - `argparse` で `--period month` と `--date YYYY-MM`（ゼロ埋め `2026-03` を正とするか、`2026-3` も許容するかは実装で固定）。  
   - `generate.py` を **week / month 分岐**に拡張（`run_week` / `run_month` への分割や `summarizer/month_bounds.py` の追加は任意）。

3. **プロンプト**  
   - `summarizer/prompts/monthly_hybrid.txt`  
   - プレースホルダ例: `{{MONTH_LABEL}}`（人間可読の月）、`{{ACTIVITY_DIGEST}}`  
   - 見出しは週次と揃え **`### 今月のトピック`** から始め、**先頭に `#` / `##` を書かない**（週次プロンプトと同方針）。本文は `design.md` §7 のトーンに寄せつつ「今月の〜」に言い換え。

4. **UPSERT**  
   - `period_type = 'monthly'`、`week_number = NULL`（スキーマ上 NULL 可）。  
   - `ON CONFLICT (period_type, period_start) DO UPDATE` の列は週次と同様。**`is_published` / `published_at` は UPDATE に含めない**。

5. **空データ**  
   - 週次と同じく **(A) ログ 0 件なら Ollama を呼ばず終了コード 0 でスキップ**を推奨。

#### M2 任意拡張（後回し可）

- その月の **`weekly` 行を DB から読み、プロンプトに「週次サマリーの要約」として付ける** → 生ログよりトークン削減・月次の一貫性向上。M2 必須ではない。  
- 月次だけ `--timeout` 既定を長めにする。

#### M2 タスク分解（実装順）

| ID | タスク | 内容・成果物 | 依存 |
|----|--------|----------------|------|
| **2.1** | 月境界モジュール | `summarizer/month_bounds.py`（または `week_bounds` 拡張）: `parse_year_month(s) -> (year, month)`、`month_utc_range(year, month) -> (start_utc, end_utc)`、月末日の算出、`month_label(...)` 文字列 | なし |
| **2.2** | CLI 拡張 | `generate.py`: `--period` に `month` を追加。`month` のとき `--date` は `YYYY-MM`。`week` 時は従来どおり `YYYY-Www` | 2.1 |
| **2.3** | 月次プロンプト | `summarizer/prompts/monthly_hybrid.txt`（プレースホルダ・見出し方針は週次と整合） | なし |
| **2.4** | finalize 月次 | `finalize_monthly_markdown(body, month_label_text)`（週次と同じく先頭 H1/H2 を剥がしてから機械 H2 を付与） | 2.1 |
| **2.5** | コンテキスト | `fetch_activity_digest` をそのまま呼ぶ。必要なら月用 `MAX_LOG_LINES` 定数を分ける（`context.py`） | 2.1, 既存 context |
| **2.6** | upsert_monthly | `INSERT ... monthly ... week_number NULL` + `ON CONFLICT`（`is_published` 不更新） | 既存 db |
| **2.7** | main 結線 | ログ取得 → 空ならスキップ → テンプレ読み込み → Ollama → finalize → upsert | 2.2–2.6, 2.3 |
| **2.8** | 動作確認 | データがある月で実行 → `/summaries`・カレンダー**月**ビューで表示。再実行で本文のみ更新・公開フラグ維持 | 2.7 |

**実行例（リポジトリルート）**:

```bash
./venv/bin/python -m summarizer.generate --period month --date 2026-01
```

#### M2 と M3 の境界

- M2 は **1 ヶ月・1 コマンド**まで。  
- **複数月のループ**・`--force`・再開可能バッチは **M3** に任せる。

**完了条件**: 上記実行例が成功し、ダッシュボードの月次サマリーパネルと API が `monthly` 行を表示する。

### M3 — 過去分一括生成

- `summarizer/batch_backfill.py`（名前は任意）: 開始日〜終了日を週または月でループ。既に行がある場合は `--force` で上書きなど。  
- 長時間運用はログ出力と途中再開の有無をドキュメント化。

### M4 — Neocities: 週次（＋方針次第で月次）HTML

- `publisher/templates/summary.html`（または週専用）で静的 HTML を生成。  
- `publisher/neocities.py`: `POST https://neocities.org/api/upload`（`docs/api/neocities.md` のパス規則と一致）。  
- **アップロード対象**: `is_published=TRUE` の行のみ（ダッシュボードのトグルと連動）。  
- `design.md` の「週次新規のみ」などと矛盾しないよう、**既存 Neocities ページの更新ポリシー**（上書き / 新規ファイル名のみ）を本ドキュメントか `neocities.md` に 1 行追記する。

### M5 — Planet ページ（DB ベース）

- `design.md` ロードマップ項 31。`publisher/build.py` + `templates/planet.html`。  
- M4 の後か並行でもよいが、サマリー単体よりスコープが広いため **M4 完了後**を推奨。

### M6 — 自動実行（最小）

- `design.md` §7: 週次（前週・月曜朝）、月次（前月・1 日朝）、Neocities（1 日 1 回など）。  
- 完全な cron 整理は Phase 7 に任せ、Phase 6 では **推奨 crontab 断片**を `docs/phase6_plan.md` 末尾または `cron/crontab.txt` に追記する程度でよい。

---

## 4. 設定・シークレット

| 項目 | 置き場所 |
|------|-----------|
| PostgreSQL | 既存どおり `settings.toml`（ダッシュボードと共有） |
| Ollama host / model | `settings.toml` に `[ollama]` 等を追加（`settings.toml.example` にダミー） |
| Neocities API キー | 既存キー設定があれば流用。なければ同ファイルにキー名を定義 |

---

## 5. テスト観点（手動で可）

- データなしの**週・月**: スキップ (A) なら終了コード 0 と stderr メッセージが仕様どおりか。  
- Ollama 停止時: 非ゼロ終了コード・メッセージ明確化。  
- 再実行: 同一 `(period_type, period_start)` で内容だけ差し替わり、公開フラグは意図どおり保持。  
- Neocities: ドラフト HTML をローカル保存してからアップロードするデバッグモードがあると安全。

---

## 6. 参照ドキュメント

| 文書 | 用途 |
|------|------|
| `docs/design.md` §7–8 | 生成タイミング・スタイル・公開範囲 |
| `docs/summary_integration_plan.md` | DB・API・カレンダーとの契約 |
| `docs/api/neocities.md` | アップロード API |
| `db/schema.sql` | `summaries` 定義 |
| `docs/next_tasks.md` | フェーズ全体の位置づけ |

---

## 7. Phase 6 完了の定義（提案）

- [x] 週次・月次の CLI 生成が動作し、ダッシュボードに反映される  
- [ ] 過去分をまとめて回せるバッチがある（オプション引数で上書き制御）  
- [ ] `is_published` が ON のサマリーが Neocities にアップロードされる  
- [ ] Planet ページ生成が設計どおり動く（または「後続タスク」として明示的に切り出し）  
- [ ] `settings.toml.example` と本ファイルが実装と矛盾しない
