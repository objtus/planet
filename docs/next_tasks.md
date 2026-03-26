# 次のタスク

**最終更新**: 2026-03-26

---

## 現在の状況

| Phase | 内容 | 状態 |
|------|------|------|
| 1 | 基盤構築 | 完了 |
| 2 | 過去データインポート | 完了 |
| 3 | 自動収集 | 完了 |
| 4 | iPhone連携 | 完了 |
| 5 | ダッシュボード | **実装中**（細部・追加機能あり） |
| 6 | AI生成・公開 | 未着手 |
| 7 | 自動化・バックアップ | 未着手 |

---

## Phase 5: ダッシュボード

### 実装済み（要点）

- **カレンダー**: 月グリッド、前後月の薄表示、週番号、今日、右上から月/年タイムラインへ
- **ヒートマップ**: `GET /api/heatmap`（`posts` / `plays` / `steps` / `weather`）。**月内 min–max** の5段、指標ごとに色相。凡例付近の `<select>` で切替。投稿数・再生曲数は **0 の日は背景なし**
- **タイムライン**: 新着順、メディア・ライトボックス、フィルター、ソースバッジソロ
- **見出し**: `detail-title` は読み込んだ期間のみ（カレンダー `«‹›»` と独立）。日=年月日、週=年・週番号・日付範囲
- **統計カード・統計ページ**: Chart.js ローカル、月別/年別切替、週は7日天気ストリップ、天気絵文字
- **年ビュー**: 投稿一覧は取得しない（軽量化）。サマリー表示は今後
- **ソース管理**: 並べ替え、略称、`POST /api/collect/<stype>`
- **その他**: favicon、名古屋天気・過去バックフィル、iPhone ingest 時刻 等（詳細は `current_state.md`）

### 残タスク（優先順）

**次に進める: サマリー整備（Phase 5 → 6 の土台）**

手順・データ契約・API の詳細は **`docs/summary_integration_plan.md`** を参照。

1. **`is_published` 公開トグル API** + `/summaries` 一覧から操作できる UI
2. **`GET /api/summary`（任意だが推奨）** — 週・月単位で 1 件取得、カレンダーと SQL 共通化
3. **カレンダー**: 週/月ビューにサマリーパネル（`stat-row` 下〜タイムライン上）。年ビューは月次サマリーの一覧（投稿一覧は引き続き省略）

**UI・デザイン（並行でよい）**

- `mockup/calender_v3.html` との差分整理
- モバイル（iPhone）レイアウト確認

### 参考ドキュメント

- **`docs/summary_integration_plan.md`** — サマリー連携の実装計画
- `docs/dashboard_ui.md` — UI 仕様
- `docs/design.md` Section 6–8 — 画面・サマリー生成・公開
- `mockup/calender_v3.html` — モックアップ

---

## Phase 6: AI生成・公開

1. Ollama サマリー（`summarizer/generate.py`）
2. プロンプト（`summarizer/prompts/`）
3. 過去分一括生成
4. Neocities HTML テンプレート
5. Neocities アップロード（`publisher/`）

---

## Phase 7: 自動化・バックアップ

1. cron 整理
2. `backup/backup.sh` — `pg_dump` → gzip → rclone → pCloud（例: 毎週日曜 AM 3:00）
3. エラーログ整備

---

## バックログ（低優先・アイデア）

- **ソース管理: 新規追加フォーム**（種別でフィールド切替・接続テスト等）— 現状必要性低。ソース追加は DB / 設定直編集で十分な期間は後回し
- **年全体カレンダー一覧**: 12ヶ月同時表示や年単位スケールのヒート等。要件・パフォーマンスは未整理
- **検索の高速化（任意）**: 現状は `content LIKE '%…%'` で問題なし。ログがさらに増えて遅くなったときなど、`pg_bigm` + 既存 `gin_bigm_ops` GIN を活かす書き方へ切替を検討（着手タイミングは `EXPLAIN` や体感で判断）

---

## 運用メモ・小タスク

- YouTube Data API v3 取得 → `collectors/youtube.py` 有効化
- mastodon.cloud @objtus 収集不調の原因調査

---

## 将来タスク: 画像ローカル保存

外部 CDN URL 参照のまま。廃止インスタ分は対象外。**新規収集分**を想定。

- 収集側で非同期ダウンロード → `media/YYYY/MM/` + ハッシュ名
- DB: `metadata["media"][].local_path`
- ダッシュボード: `/media/<path>` で配信
- 自アクティブソースのみ・サムネ縮小・容量上限・ブースト元画像は保存しない 等

---

## LLM への渡し方

**最初に読む:** `overview.md` → `current_state.md` → **このファイル**

**必要に応じて:** `design.md`, `dashboard_ui.md`, `summary_integration_plan.md`, `iphone_shortcuts.md`, `importers.md`, `docs/api/*.md`
