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
| 5 | ダッシュボード | **完了**（コア機能。細部の UI は任意で継続改善） |
| 6 | AI生成・公開 | **計画策定済み** → `docs/phase6_plan.md` |
| 7 | 自動化・バックアップ | 未着手 |

---

## Phase 5: ダッシュボード（完了・要点）

- **カレンダー**: 月グリッド、前後月の薄表示、週番号、今日、右上から月/年タイムラインへ
- **ヒートマップ**: `GET /api/heatmap`（`posts` / `plays` / `steps` / `weather`）。月内 min–max の5段、指標ごとに色相
- **タイムライン**: 新着順、メディア・ライトボックス、フィルター、ソースバッジソロ
- **統計カード・統計ページ**: Chart.js ローカル、月別/年別切替、週は7日天気ストリップ
- **年ビュー**: 投稿一覧は取得しない。**月次サマリー一覧**は `#summary-panel` で表示（タイムラインはプレースホルダ）
- **サマリー連携（Phase 6 前提）**: `PATCH /api/summaries/<id>/publish`、`GET /api/summary`（`period=week|month|year`）、`/summaries` の公開トグル、カレンダー週/月/年でのパネル表示（`docs/summary_integration_plan.md`）
- **ソース管理**: 並べ替え、略称、`POST /api/collect/<stype>`

### Phase 5 で後回しにしたもの（優先度低・任意）

- `mockup/calender_v3.html` との完全一致、iPhone 幅でのレイアウト詰め → 必要になったときに着手でよい

### 参考ドキュメント

- **`docs/summary_integration_plan.md`** — サマリー連携（実装済みの契約・経緯）
- **`docs/dashboard_ui.md`** — UI 仕様
- **`docs/design.md`** Section 6–8 — 画面・サマリー生成・公開

---

## Phase 6: AI生成・公開（詳細は phase6_plan）

**マスタープラン: [`docs/phase6_plan.md`](phase6_plan.md)**（マイルストーン M1〜M6、データ契約、完了定義）

概要:

1. Ollama サマリー（`summarizer/generate.py`）— **週次 1 本から**
2. プロンプト（`summarizer/prompts/`）
3. 過去分一括生成（バッチ）
4. Neocities HTML テンプレート + アップロード（`publisher/`）
5. Planet ページ HTML 生成（`design.md` ロードマップ項 31）
6. cron は最小追記 → 本格整理は Phase 7

---

## Phase 7: 自動化・バックアップ

1. cron 整理
2. `backup/backup.sh` — `pg_dump` → gzip → rclone → pCloud（例: 毎週日曜 AM 3:00）
3. エラーログ整備

---

## バックログ（低優先・アイデア）

- **ソース管理: 新規追加フォーム**（種別でフィールド切替・接続テスト等）
- **年全体カレンダー一覧**: 12ヶ月同時表示や年単位スケールのヒート等
- **検索の高速化（任意）**: `pg_bigm` + GIN を活かす書き方へ切替（`EXPLAIN` や体感で判断）

---

## 運用メモ・優先度低（いずれも着手タイミングは任意）

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

**Phase 6 実装時:** **`docs/phase6_plan.md`** → `design.md` §7–8、`summary_integration_plan.md`

**必要に応じて:** `dashboard_ui.md`, `iphone_shortcuts.md`, `importers.md`, `docs/api/*.md`
