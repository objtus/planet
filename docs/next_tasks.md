# 次のタスク

**最終更新**: 2026-03-27

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

基本機能は実装済み。以下が残っている。

### 実装済みの主要機能（確認用）

- カレンダー月グリッド + ヒートマップ、前後月の日付を薄く表示
- カレンダー右上「○月」「○年」で月/年タイムラインへ（表示中カレンダー月を維持）
- タイムライン見出しは**読み込んだ期間**のみ表示（カレンダー `«‹›»` ナビと独立）
- view-tabs `[‹][日][週][月][年][›]` — 前後ナビ・双方向連動
- タイムライン新着順・メディア添付・画像ライトボックス
- ソースバッジクリックでソロフィルタリング
- フィルターバー折りたたみ式・メディアフィルター
- 統計カード（週/月/年は合計・平均気温表示）
- 統計ページ: Chart.js ローカル配信、月別（12ヶ月）/ 年別（全期間）切替
- ソース管理: `sort_order`・`short_name`、↑↓並べ替え、略称編集、`POST /api/collect/<stype>` で手動収集
- favicon 表示（lastfm/github/youtube 対応・廃止サーバー絵文字）
- 天気: 名古屋座標、`db/backfill_weather.py` で Open-Meteo 過去バックフィル可
- iPhone ingest タイムスタンプ実際の受信時刻化

### UI・デザイン調整

- `mockup/calender_v3.html` との差分を詰める（細部のスタイル修正）
- モバイル（iPhone）レイアウト確認・調整

### 機能追加

- カレンダー: **ヒートマップ指標の切替**（投稿数 / Last.fm 再生数 / 歩数 / 天気）
  - 正規化は**表示中の月のみ**（その月の min–max）。欠損日は色なし（0 段）でよい
  - **色相はモードごとに変える**（投稿・再生・歩数・天気でパレット分離）
  - データはページ埋め込みではなく、**月変更・指標変更時に JSON API で取得**（方式 B）
  - UI は凡例「投稿数 少→多」の**近く**にセレクトまたはトグル＋凡例ラベル連動
  - 天気: まずは **`temp_max` を強さの指標**にしつつ、見た目は後から調整しやすい実装にする

#### ヒートマップ指標切替 — 実装の考察（作業メモ）

1. **API（案）**  
   - `GET /api/heatmap?year=<int>&month=<int>&metric=posts|plays|steps|weather`  
   - レスポンス例: `{ "metric": "plays", "by_date": { "2026-03-01": 12, ... }, "min": 0, "max": 48 }`  
     - `by_date` は**当該暦月の1日〜末日**について、データがある日のみキーを返す（欠損日はキーなし）でも、毎日キーで `null` でもよい。フロントは「当月セル」かつ値ありで段階化。  
     - `min` / `max` は**その月・その指標について実際に存在する値だけ**で算出（全日欠損なら min/max は null、ヒートはすべて無色）。  
   - バリデーション: `month` 1–12、`metric` は列挙のみ。認証は他 API と同様（現状どおり）。

2. **サーバー SQL の対応関係（JST の日付キーで統一）**  
   - **posts**: 既存カレンダーと同様 `logs` で `DATE(timestamp AT TIME ZONE 'Asia/Tokyo')` を月で絞り `COUNT`，`is_deleted = FALSE`。  
   - **plays**: `logs` で `data_sources.type = 'lastfm'`（または同等）に限定して日別 `COUNT`。`lastfm_plays` 直参照より、表示とログの整合が取りやすい。  
   - **steps**: `health_daily` の `date` が月内の行の `steps`。  
   - **weather**: `weather_daily` の `date` が月内の `temp_max`（NULL は返さない／フロントで無色）。

3. **フロント（`calendar.js`）**  
   - グローバル `HEATMAP` の固定埋め込みをやめ、**メモリ上のオブジェクト**（例: `heatValues`）に置き換え。初回表示・`shiftMonth` / `onSelChange` / 指標変更で `fetch` → 成功後に `buildCal()`。  
   - `heatLevel(n, min, max)` を数値正規化＋5段階に変更（現状の閾値は投稿数向けなので、**線形分割** `(n - min) / (max - min)` を段にマップする形が汎用）。`max === min` かつ値ありのときは中段1つにまとめるなどエッジを決める。  
   - 凡例のラベル（「投稿数」「再生曲数」…）と **CSS 変数（`--heat-1`〜`--heat-5`）** を指標ごとにセット。`document.documentElement` またはカレンダー `.card` に `data-heat-metric="plays"` を付与してスタイル切替でも可。

4. **テンプレート・初期表示（`calendar.html` / `calendar()`）**  
   - 初回 HTML に巨大な辞書を載せない方針なら、`HEATMAP = {}` でよい。ロード中はグリッドを描画した直後に薄い「読み込み中」でも、**空のままフェッチ完了で再描画**でもよい（ちらつき防止で前者が無難）。  
   - `app.py` の `/` での全期間投稿集計クエリは**削除またはヒート用に不要**になり、トップの DB 負荷は下がる。

5. **UI 配置**  
   - `.legend` 内または直下に `<select id="heat-metric">` 等。モバイル幅では凡例と同一行で折り返し（既存 `flex-wrap` 前提）。

6. **ドキュメント**  
   - 実装後に `docs/dashboard_ui.md` のカレンダー節に指標切替・API 一言を追記。

7. **テストの目安**  
   - 月をまたぐナビで `year/month` が API と一致するか、他月セルが常に無ヒートか、plays/steps/weather が無い月でエラーにならないか。
- 検索: `LIKE` → `pg_bigm` 全文検索（`gin_bigm_ops` インデックス使用）
- カレンダー: 週/月/年ビューにサマリー表示（`summaries` テーブルから取得）
- サマリー: `is_published` 公開トグル API
- ソース管理: 新規追加フォーム（種別選択 → フィールド切り替え）

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

## アイデア・後で設計（低優先）

- **年全体のカレンダー一覧**: 1年分を一覧で眺める UI（例: 12ヶ月のミニグリッド、年単位のヒートスケールなど）。現状は月表示のみで月内スケールで十分なため、要件・スケール（年通し vs 月ごと）・パフォーマンスは後から検討する

---

## 残っている小タスク

- YouTube Data API v3 キー取得（Google Cloud Console）→ `collectors/youtube.py` 有効化
- mastodon.cloud @objtus の収集が不調 → 原因調査

---

## 将来タスク: 画像ローカル保存

現在、メディア画像は外部 CDN の URL をそのまま参照している。
廃止済みサーバー（pon.icu 等）分はすでに閲覧不可のため諦め、以下は新規収集分を対象とする。

### 方針
- 収集スクリプト（`collectors/misskey.py` / `collectors/mastodon.py`）内で画像を非同期ダウンロード
- 保存先: `media/` ディレクトリ（`YYYY/MM/` 階層 + ファイル名はハッシュ）
- DB の `metadata["media"][].local_path` に保存パスを記録
- ダッシュボードから `/media/<path>` で配信（Flask の `send_from_directory`）
- 対象: 自分のアカウント（is_active=True のソース）の画像のみ・動画は除外も検討
- ストレージ上限を設けてサムネイルサイズ（幅 800px 程度）に縮小して保存
- ブースト/リノートの元投稿画像は保存しない（他人のコンテンツ）

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

