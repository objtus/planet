# 次のタスク

**最終更新**: 2026-03-23

---

## 現在の状況

- Phase 1（基盤構築）: **完了**
- Phase 2（過去データインポート）: **完了**
- Phase 3（自動収集）: **完了**
- Phase 4（iPhone連携）: **完了**
- Phase 5（ダッシュボード）: **実装中** ← 今ここ
- Phase 6（AI生成・公開）: 未着手
- Phase 7（自動化・バックアップ）: 未着手

---

## Phase 5: ダッシュボード（残タスク）

骨格・全画面・API は実装済み。以下が残っている。

### UI・デザイン調整

- [ ] `mockup/calender_v3.html` との差分を詰める（細部のスタイル修正）
- [ ] モバイル（iPhone）レイアウト確認・調整

### 機能追加

- [ ] 検索: `LIKE` → `pg_bigm` 全文検索（`gin_bigm_ops` インデックス使用）
- [ ] カレンダー: 週ビュー — 週次サマリー表示（`summaries` テーブルから取得）
- [ ] カレンダー: 月ビュー — 月次サマリー + 投稿一覧（遅延読み込み）
- [ ] カレンダー: 年ビュー — 年間統計 + 月別サマリー一覧
- [ ] サマリー: `is_published` 公開トグル API
- [ ] ソース管理: 新規追加フォーム（種別選択 → フィールド切り替え）

### 参考ドキュメント

- `docs/dashboard_ui.md` — UI仕様・色・インタラクション詳細
- `docs/design.md` Section 6 — 画面構成・カレンダー詳細仕様
- `mockup/calender_v3.html` — デザインモックアップ（忠実に再現すること）

---

## Phase 6: AI生成・公開

1. Ollama サマリー生成（`summarizer/generate.py`）
2. プロンプトテンプレート（`summarizer/prompts/`）
3. 過去分サマリー一括生成
4. Neocities HTML テンプレート作成
5. Neocities アップロードスクリプト（`publisher/`）

---

## Phase 7: 自動化・バックアップ

1. 全 cron ジョブ統合・整理
2. バックアップスクリプト（`backup/backup.sh`）
   - `pg_dump → gzip → rclone → pCloud`
   - 毎週日曜 AM 3:00
3. エラーログ整備

---

## 残っている小タスク

- [ ] YouTube Data API v3 キー取得（Google Cloud Console）→ `collectors/youtube.py` 有効化
- [ ] mastodon.cloud @objtus の収集が不調 → 原因調査

---

## LLMへの渡し方

起動時に以下を読ませる：
1. docs/overview.md
2. docs/current_state.md
3. docs/next_tasks.md

詳細が必要なときに参照させる：
- docs/design.md（スキーマ・全体仕様）
- docs/dashboard_ui.md（ダッシュボード UI仕様・モックアップの説明）
- docs/iphone_shortcuts.md（iPhone連携の詳細）
- docs/importers.md（インポーター実装時）
- docs/api/misskey.md（Misskey収集スクリプト実装時）
- docs/api/mastodon.md（Mastodon収集スクリプト実装時）
- docs/api/*.md（各収集スクリプト実装時）
