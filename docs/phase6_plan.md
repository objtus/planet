# Phase 6: AI 生成・公開 — 実装プラン

**最終更新**: 2026-03-26

**前提**: Phase 5 のダッシュボードは機能完成扱い。`summaries` の閲覧・カレンダー連携・公開トグル・`GET /api/summary` は実装済み（契約は `docs/summary_integration_plan.md`）。本フェーズでは **行の自動生成** と **Neocities への反映** を追加する。

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

3. **Ollama**  
   - HTTP: `POST http://<host>:11434/api/generate`（または chat API。モデルが chat 専用ならそちら）。  
   - 接続先・モデル名は `config/settings.toml` に追加（例: `[ollama] host`, `model`）。既存の `design.md` の「model で切替」と整合。  
   - 依存: リポジトリに `requests` 済みならそれを利用。

4. **出力**  
   - 生成テキストを `summaries` に UPSERT。`is_published` は既存行を尊重（`ON CONFLICT` 時に `is_published` を上書きしない）。

**完了条件**: ローカルで 1 週分実行 → `/summaries` とカレンダー週ビューのパネルに表示。

### M2 — 月次パイプライン

- `summarizer/prompts/monthly_hybrid.txt`  
- CLI `--period month --date 2026-03`  
- 月の `[start, end]` で同じ集約ロジックを再利用。

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

- データなしの週: エラーで終了か、短い「データ不足」サマリーかを仕様として固定。  
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

- [ ] 週次・月次の CLI 生成が動作し、ダッシュボードに反映される  
- [ ] 過去分をまとめて回せるバッチがある（オプション引数で上書き制御）  
- [ ] `is_published` が ON のサマリーが Neocities にアップロードされる  
- [ ] Planet ページ生成が設計どおり動く（または「後続タスク」として明示的に切り出し）  
- [ ] `settings.toml.example` と本ファイルが実装と矛盾しない
