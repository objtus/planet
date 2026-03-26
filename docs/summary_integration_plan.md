# サマリー連携計画（ダッシュボード ↔ `summaries` ↔ Phase 6）

**目的**: Phase 6（Ollama 生成・Neocities 公開）に向け、`summaries` テーブルをダッシュボードで**閲覧・公開フラグ管理**できる状態にし、カレンダーの週/月/年ビューと一貫した体験にする。

**実装状況（2026-03）**: フェーズ A・B（API・一覧トグル・カレンダーパネル・`GET /api/summary`）は**実装済み**。フェーズ C（`summarizer/generate.py`・Neocities）は **Phase 6** で着手。全体の工程は **`docs/phase6_plan.md`** を参照。

**前提**: 週次の自動投入は `./venv/bin/python -m summarizer.generate --period week --date YYYY-Www`（`summarizer/generate.py`。システム `python3` には `psycopg2` が無いことが多い）。月次・バッチ・Neocities は未実装。

---

## 1. 現状（コード・スキーマ）

| 項目 | 状態 |
|------|------|
| `summaries` テーブル | `period_type`, `period_start`/`period_end`, `week_number`, `content`, `is_published`, `published_at`, `UNIQUE(period_type, period_start)` 等（`db/schema.sql`） |
| `/summaries` | 全件一覧 + **Neocities 公開チェックボックス**（`PATCH /api/summaries/<id>/publish`） |
| カレンダー週/月 | `#summary-panel` で `GET /api/summary`（週・月） |
| 年ビュー | 投稿一覧は省略。パネルで**年内月次サマリー一覧** + 月ビューへ遷移 |

---

## 2. データ契約（生成側と共有）

Phase 6 の `generate.py` と揃えるため、**先に固定しておく値**。

- **`period_type`**: 当面は `'weekly'` / `'monthly'` のみ（年次 AI サマリーは設計外なら不要）。
- **週次**: `period_start` = その ISO 週の**月曜**（JST 日付）、`period_end` = **日曜**。`week_number` = ISO 週番号（その週の「ISO 年」とセットで解釈するなら API で `isoyear` も返すか、表示は `period_start` ベースに統一）。
- **月次**: `period_start` = その月 **1 日**、`period_end` = **月末**。表示ラベルは `YYYY-MM`。
- **`content`**: NOT NULL。プレースホルダ生成時は `'（生成待ち）'` 等でもよいが、一覧・カレンダーで空でない方が UI が単純。

将来 `yearly` を足す場合は UNIQUE 制約（`period_type`, `period_start`）のまま `period_start = YYYY-01-01` などで表現可能。

---

## 3. 実装フェーズ（推奨順）

### フェーズ A — API と一覧画面（基盤）

1. **`PATCH /api/summaries/<int:id>/publish`**（または `POST` + JSON）  
   - ボディ: `{ "is_published": true|false }`  
   - `is_published=true` のとき `published_at = now()`（初回または再公開の扱いは要件で決める。単純化なら「オンにしたら常に更新」でも可）  
   - `false` のとき `published_at = NULL`  
   - レスポンス: 更新後の行または `{ok: true}`

2. **`/summaries`（テンプレート）**  
   - 各行にトグル（またはボタン）＋ `fetch` で上記 API 呼び出し  
   - 失敗時はメッセージ表示  
   - CSRF: 現状ダッシュボードは同一オリジン・Tailscale 内想定。必要なら Flask のトークンや `SameSite` の整理は後続

3. **`GET /api/summary`**（実装済み）  
   - クエリ: `period=week|month|year`、`date` は週 `YYYY-Www`、月 `YYYY-MM`、年は西暦  
   - 週・月: 該当 1 件 or `summary: null`。年: `summaries` 配列（月次のみ）  
   - SQL は `dashboard/app.py` 内で共通化

### フェーズ B — カレンダー週・月ビュー

1. **レイアウト**: `stat-row`（と週天気帯）の**下**、タイムライン／プレースホルダの**上**に `.summary-panel` を置く案が自然（`design.md` の「週次サマリー」「月次サマリー」と同順序）。

2. **`loadWeek` / `loadMonth` 完了後**に `GET /api/summary` を追加フェッチ（または `Promise.all` で統計と並列）。  
   - 無い場合: 「この週／月のサマリーはまだありません」程度の1行  
   - ある場合: `content` をそのまま表示（長文は `max-height` + スクロールまたは `<details>`）

3. **年ビュー**はタイムラインがプレースホルダのため、**同じパネル位置**で「`YYYY` 年の月次サマリー」リスト（`period_type=monthly` かつ `period_start` がその年内）をテーブルまたはリンク列で表示。クリックで月ビューへ遷移するなど拡張可能。

### フェーズ C — Phase 6 との接続

- `summarizer/generate.py`: 上記データ契約で `INSERT ... ON CONFLICT (period_type, period_start) DO UPDATE`  
- Neocities: `is_published=true` の週次・月次だけアップロード（`docs/api/neocities.md` のパス規則と一致させる）  
- cron: `design.md` Section 7 のタイミング

---

## 4. 非機能・注意

- **認証**: 公開トグルは**誰でも叩ける**現状と同じ。将来ログインを入れるなら API を保護。
- **XSS**: `content` を HTML に埋め込む場合は**エスケープ必須**（現状 `summaries.html` は Jinja 自動エスケープ。カレンダーは `innerHTML` 禁止か `textContent` / 安全なエスケープ関数を使う）。
- **パフォーマンス**: サマリー1件はテキスト想定。年ビューは最大 12 行のメタデータ取得で十分軽い。

---

## 5. スコープ外（今回の計画に含めない）

- ソース管理の新規追加フォーム（別途バックログ）
- Ollama プロンプト本文・品質チューニング
- Neocities アップロード本体の実装（Phase 6 項目）

---

## 6. 参照ドキュメント

- `docs/design.md` — Section 6（画面・週/月/年の表示内容）、Section 7（生成タイミング）、Section 8（公開と `is_published` の意味合い）
- `docs/api/neocities.md` — アップロード先パス
- `db/schema.sql` — `summaries` 定義
- `dashboard/app.py` — `summaries()` ルート
- `dashboard/templates/summaries.html` — 一覧 UI
