# 次のタスク

**最終更新**: 2026-03-23

---

## 現在の状況

- Phase 1（基盤構築）: **完了**
- Phase 2（過去データインポート）: **完了**
- Phase 3（自動収集）: **完了**
- Phase 4（iPhone連携）: **完了**
- Phase 5（ダッシュボード）: **未着手** ← 次はここ
- Phase 6（AI生成・公開）: 未着手
- Phase 7（自動化・バックアップ）: 未着手

---

## Phase 5: ダッシュボード

仕様は `docs/design.md` Section 6 参照。

### 実装順序

1. **Flask アプリ骨格**（`dashboard/app.py`）
   - `ingest_bp`（`ingest/api.py`）を統合してポート5000で一本化
   - `planet-ingest.service` は廃止
2. **カレンダー画面**（`/`）
   - ヒートマップカレンダー（GitHubスタイル、ISO週番号付き）
   - 日/週/月/年の選択による表示切り替え
3. **タイムライン表示**
   - 全ソース統合、ソースアイコン付き
   - CW付き投稿は折りたたみ
4. **検索機能**（`/search`）
   - pg_bigm 全文検索
   - ソース・日付範囲フィルター
5. **統計グラフ**（`/stats`）
6. **サマリー一覧**（`/summaries`）
7. **ソース管理画面**（`/sources`）

### デザイン方針（`docs/design.md` より）

- ダークテーマ・シンプル・クール・情報密度高め
- モバイル（iPhone）対応レスポンシブ
- Tailscale 経由のみアクセス（追加認証なし）

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
- docs/iphone_shortcuts.md（iPhone連携の詳細）
- docs/importers.md（インポーター実装時）
- docs/api/misskey.md（Misskey収集スクリプト実装時）
- docs/api/mastodon.md（Mastodon収集スクリプト実装時）
- docs/api/*.md（各収集スクリプト実装時）
