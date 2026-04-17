# サマライザー品質向上 — 設計計画

**作成日**: 2026-04-17  
**最終更新**: 2026-04-17  
**ステータス**: 設計確定  
**関連ドキュメント**: `docs/phase6_plan.md`, `docs/design.md` §7

---

## 1. 現状の問題

- 全ソースを1プロンプトに一括で渡しているため、各トピックへの「注意力」が分散する
- その日だけのデータを渡しているため、普段との比較ができず活発だったのか静かだったのか判断できない
- 結果として内容が薄く、どの週・月も似たような表現になりやすい

---

## 2. 改善方針

### 2-1. トピック別独立生成

全ソース一括生成をやめ、トピックごとに独立したプロンプトで生成する。  
各トピックに集中してデータを渡すことで、内容の深さが向上する。

Ollamaリクエスト数は増加するが許容する。

### 2-2. プロンプトへの基本情報（コンテキスト）埋め込み

各トピックのプロンプトファイル（txt）の冒頭に、そのトピックに関する固定の基本情報を記載する。

**目的**: モデルにユーザーの背景・傾向・アカウント用途を事前に伝えることで、  
「このアーティストは普段からよく聴く」「このアカウントはサブ垢」などの文脈を活かした生成が可能になる。

**基本情報の内容例**:

| トピック | 記載内容 |
|---|---|
| music | Last.fmアカウント名、よく聴くジャンル傾向、主なアーティスト |
| health | 記録している指標の一覧、生活スタイルのメモ |
| sns | 各アカウントの用途・キャラクター一覧 |
| dev | 主なリポジトリ・使用言語・開発スタイル |
| behavior | 生活の基本パターン（夜型など）、データ解釈のヒント |

**作成方法**:
1. DBから統計・サンプルデータを収集（上位アーティスト、アカウント投稿サンプル等）
2. Claudeに渡して基本情報テキストのドラフトを生成してもらう
3. 手動で確認・調整してプロンプトtxtの冒頭に貼り付ける

基本情報は原則として一度書いたら更新不要な内容を想定。  
変更が必要な場合はダッシュボードのプロンプト編集画面から手動で修正する。

### 2-3. 文字数制限はプロンプトtxtにベタ書き

各プロンプトファイル内に「〇〇字以内で」と直接記載する。  
トピックごとに適切な上限が異なるため、一括変更より個別チューニングの方が実態に合っている。  
変更が必要な場合は `/prompts` 画面から編集する。

| summary_type | 目安 |
|---|---|
| 各トピック（music等） | 200〜400字程度 |
| behavior | 200〜300字程度 |
| full | 600〜800字程度 |
| best_post | 100〜200字程度 |
| oneword | 30〜50字程度 |

### 2-4. ダッシュボードからのプロンプト編集

プロンプトtxtをダッシュボードから直接編集できる画面（`/prompts`）を追加する。  
基本情報の修正や、プロンプトのチューニングを手軽に行えるようにする。

---

## 3. 生成フロー

### 日次

```
① トピック別生成（並列可）
   - music    : Last.fm再生ログ → daily_music.txt
   - health   : 歩数・心拍・活動量 → daily_health.txt
   - sns      : Misskey / Mastodon投稿 → daily_sns.txt
   - dev      : GitHub活動 → daily_dev.txt

② トピック横断生成（①のうちデータがあるトピックの結果を入力）
   - behavior : その日の行動推測 → daily_behavior.txt

③ 全体統合（①②の結果を入力）
   - full     : 日次全体サマリー → daily_full.txt

④ 後処理生成（③の結果を入力）
   - oneword  : その日を一言で → oneword.txt（共通）
```

### 週次

```
① トピック別週次まとめ（日次の各トピック×7を入力）
   - music / health / sns / dev → topic_summary.txt（共通）

② 行動まとめ（日次 behavior×7を入力）
   - behavior → topic_summary.txt（共通・behaviorラベルで）

③ 全体統合（①②の結果を入力）
   - full → period_full.txt（共通）

④ 後処理生成（③の結果を入力）
   - oneword   : 週を一言で → oneword.txt（共通）
   - best_post : 週のベスト投稿を1件選定・理由付き → best_post.txt
```

### 月次

週次と同じ構造（週次の各サマリーを入力として使用）。  
`best_post` は月次では生成しない（週次のみ）。

---

## 4. summary_type 一覧

| summary_type | 生成タイミング | 説明 |
|---|---|---|
| `music` | 日次・週次・月次 | 音楽トピック |
| `health` | 日次・週次・月次 | 健康・活動量トピック |
| `sns` | 日次・週次・月次 | SNS・発言トピック |
| `dev` | 日次・週次・月次 | 開発トピック |
| `behavior` | 日次・週次・月次 | 行動推測 |
| `full` | 日次・週次・月次 | 全体統合サマリー |
| `oneword` | 日次・週次・月次 | 一言まとめ |
| `best_post` | 週次のみ | ベスト投稿（1件）＋選定理由 |

---

## 5. DB設計

既存の `summaries` テーブルに `summary_type` 列を追加。  
UNIQUE制約を `(period_type, period_start, summary_type)` に変更する。

```sql
-- summary_type 列の追加
ALTER TABLE summaries
    ADD COLUMN summary_type TEXT NOT NULL DEFAULT 'full';

-- 既存のUNIQUE制約を張り替え
ALTER TABLE summaries
    DROP CONSTRAINT summaries_period_type_period_start_key;

ALTER TABLE summaries
    ADD CONSTRAINT summaries_unique
    UNIQUE (period_type, period_start, summary_type);
```

既存行は `summary_type = 'full'` として扱われるため、データ変更不要。

---

## 6. プロンプトファイル構成

共通化により21ファイル → 10ファイルに削減。

```
summarizer/prompts/
├── daily_music.txt       # 日次：音楽（生ログ入力）
├── daily_health.txt      # 日次：健康（生ログ入力）
├── daily_sns.txt         # 日次：SNS（生ログ入力）
├── daily_dev.txt         # 日次：開発（生ログ入力）
├── daily_behavior.txt    # 日次：行動推測（トピック結果入力）
├── daily_full.txt        # 日次：全体統合
├── topic_summary.txt     # 週次・月次 各トピックまとめ共通（{PERIOD_LABEL}等で切替）
├── period_full.txt       # 週次・月次 全体統合共通
├── oneword.txt           # 日次・週次・月次 一言共通
└── best_post.txt         # 週次：ベスト投稿選定
```

各ファイルの冒頭に `## 基本情報` セクションと文字数制限を記載する。

---

## 7. ダッシュボード画面追加

### `/prompts` — プロンプト編集画面

`summarizer/prompts/` 以下のファイルをダッシュボードから編集できる画面。

**UI方針**:
- ファイル一覧をリストで表示、クリックで選択
- 選択中ファイルの内容をテキストエリアで表示・編集
- 保存ボタンで上書き保存
- 未保存変更がある状態での離脱時は警告
- モバイルでは上下分割レイアウト

実装優先度は高め（基本情報を書いた直後から使いたいため）。

### `/settings` — 設定画面

`settings.toml` の中でよく変える項目だけをUIから変更できる補助画面。  
APIキー等の機密性が高い項目はブラウザ画面に出さず、`settings.toml` 直接編集のまま。

**掲載項目（案）**:
- Ollamaモデル名・ホスト
- サマリー生成のログ取得上限件数（日次・週次・月次）
- Ollamaタイムアウト秒数

---

## 8. 未決事項

### 確定済み

- `best_post` の保存形式：選定した投稿の `logs.id` を `metadata` に持たせ、選定理由を `content` に入れる
- SNSアカウントの基本情報：投稿サンプルからの自動生成ではなく手記入で作成する
- 既存パイプラインからの移行：新パイプラインへ完全移行する。移行期間中は `--legacy` フラグで旧パイプラインにフォールバックできるようにし、動作確認後に旧コードを削除する

### 実装しながら決める

- データが存在しないトピックのスキップ処理
- `topic_summary.txt` / `period_full.txt` の共通プレースホルダの命名（`{PERIOD_LABEL}` 等）
- 各プロンプトの具体的な文字数上限値（実際に生成してみてから調整）

### スコープ外（後続で検討）

- ベースライン（過去平均との比較）

---

## 9. 実装順序（推奨）

1. DBマイグレーション（`summary_type` 列追加・UNIQUE制約張替え）
2. 各プロンプトtxtの作成（基本情報・文字数制限を含む）
3. `/prompts` 編集画面の実装
4. `generate.py` のトピック別生成対応
5. 日次フロー動作確認
6. 週次・月次フローへの展開
7. `/settings` 画面の実装

---

## 10. 基本情報ドラフト

各プロンプトtxtの冒頭に貼り付ける基本情報。  
DBから収集したデータをもとにClaudeが生成したドラフト。  
実際に貼り付ける前に内容を確認・調整すること。

※ SNSアカウントの用途・behaviorの生活パターンは投稿サンプル未取得のため要調整。  
　 取得後に `/prompts` 画面から修正する。

---

### `daily_music.txt`

```
## 基本情報
このユーザーのLast.fmアカウントは「objtus」。
音楽の趣味はエレクトロニック・ミュージックが中心で、IDM（Aphex Twin、Squarepusher、Clark）、
ハイパーポップ・クラウドラップ系（Bladee、Ecco2K、Yung Lean、Drain Gang）、
実験的エレクトロニカ（Oneohtrix Point Never、Arca、James Ferraro）を特によく聴く。
日本のアーティストも聴き、平沢進・サカナクション・宇多田ヒカル・パソコン音楽クラブ・tofubeats等が上位に入る。
再生数上位はJam City（713）、Bladee（599）、Oneohtrix Point Never（530）、Ecco2K（505）、Aphex Twin（458）。
```

---

### `daily_health.txt`

```
## 基本情報
iPhoneのHealthKitから1日1回自動送信で記録している。
記録している指標は歩数・消費カロリー・心拍数（平均・最大・最小）・運動時間・スタンド時間・写真枚数。
直近90日の平均歩数は約4100歩。最大歩数は13551歩。
平均心拍数は約73bpm。
```

---

### `daily_sns.txt`

※ 各アカウントの用途は手記入で作成する。以下はアカウント一覧のひな形。

```
## 基本情報
このユーザーは複数のFediverseアカウントを使い分けている。

- misskey.io @yuinoid : （用途を記入）
- misskey.io @vknsq : （用途を記入）
- sushi.ski @idoko : （用途を記入）
- tanoshii.site @health : 健康・体調記録用
- msk.ilnk.info @google : （用途を記入）
- mastodon.cloud @objtus : （用途を記入）
- mistodon.cloud @healthcare : （用途を記入）
- pon.icu @health（閉鎖済み）: 旧健康記録アカウント
- groundpolis.app @healthcare（閉鎖済み）: （用途を記入）
```

---

### `daily_dev.txt`

```
## 基本情報
GitHubアカウントはobjtus。主にPythonとJavaScriptで開発している。
主なリポジトリ：
- planet / planet-feed : 個人ライフログシステム（最も活発）
- gifvtbr : 用途不明（要調整）
- 100percent-health : 健康記録関連
- dsns-timeline-bot : SNSタイムラインBot
```

---

### `daily_behavior.txt`

```
## 基本情報
Fediverseへの投稿・音楽再生・GitHub活動・iPhoneヘルスデータから行動を推測する。
健康記録アカウント（tanoshii.site @health 等）への投稿は体調・行動メモである場合が多い。
生活パターン（夜型かどうか等）は投稿サンプル取得後に要調整。
```