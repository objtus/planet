# Scrapbox (Cosense) API 仕様メモ

## 基本情報

- サービス名: Cosense（旧称 Scrapbox、2024年5月に改名。APIのURLはscrapbox.ioのまま）
- プロジェクト: `stall`（公開プロジェクト）
- ベースURL: `https://scrapbox.io/api/`
- 認証: **不要**（公開プロジェクトのため）
- レート制限: 明示的な制限なし。連続リクエストは1秒間隔推奨

---

## 使用するエンドポイント

### ページ一覧取得

```
GET https://scrapbox.io/api/pages/stall?limit=100&skip=0
```

**レスポンス例**
```json
{
  "projectName": "stall",
  "skip": 0,
  "limit": 100,
  "count": 1506,
  "pages": [
    {
      "id": "xxxx",
      "title": "2026/03/27",
      "updated": 1742947200,
      "created": 1742947200
    }
  ]
}
```

### 特定ページの取得

```
GET https://scrapbox.io/api/pages/stall/<encoded-title>
```

**レスポンスから使うフィールド**
```json
{
  "title": "2026/03/27",
  "updated": 1742947200,
  "created": 1742860800,
  "lines": [
    {"text": "2026/03/27", "created": 1742860800},
    {"text": "今日は..."},
    {"text": ""}
  ]
}
```

### ページ本文テキストの取得（推奨）

```
GET https://scrapbox.io/api/pages/stall/<encoded-title>/text
```

Scrapbox記法を含む生テキストがそのまま返る。`lines` を結合するより簡単。

---

## 日記ページの差分取得ロジック

### ポイント
- 日記のタイトル形式: `YYYY/MM/DD`（例: `2026/03/27`）スラッシュ区切り
- URLに使う際は `urllib.parse.quote(title, safe="")` でエンコードが必要（`2026%2F03%2F27` になる）
- 未エンコードのスラッシュはパス区切りと解釈され404になる（実証済み）
- 2〜3日まとめて書く・過去ページへの追記があるため、直近30日分を毎日チェックする
- `updated`（Unix timestamp）をDBに保存して前回取得からの変更を検知する

```python
import requests
import urllib.parse
from datetime import date, timedelta

def sync_diary_pages(project="stall", lookback_days=30):
    """直近30日分の日付ページを毎日チェックして差分を更新"""
    for i in range(lookback_days):
        d = date.today() - timedelta(days=i)
        title = d.strftime("%Y/%m/%d")  # スラッシュ区切り形式
        encoded_title = urllib.parse.quote(title, safe="")
        url = f"https://scrapbox.io/api/pages/{project}/{encoded_title}"

        res = requests.get(url)

        if res.status_code == 404:
            continue  # その日のページが存在しない

        page = res.json()
        updated = page.get("updated")

        # DBの前回取得タイムスタンプと比較
        last_updated = db.get_scrapbox_updated(project, title)

        if last_updated is None or updated > last_updated:
            # 変更あり → 本文を取得してupsert
            text_url = f"https://scrapbox.io/api/pages/{project}/{encoded_title}/text"
            text = requests.get(text_url).text
            db.upsert_scrapbox_page(project, title, text, updated, d)
```

---

## DBスキーマ

```sql
CREATE TABLE scrapbox_pages (
    id               BIGSERIAL PRIMARY KEY,
    log_id           BIGINT REFERENCES logs(id),
    source_id        INT REFERENCES data_sources(id),
    project          TEXT NOT NULL,
    page_title       TEXT NOT NULL,         -- '2026/03/25'（スラッシュ区切り、Scrapboxのタイトルそのまま）
    content          TEXT,                  -- ページ全文（Scrapbox記法含む）
    content_plain    TEXT,                  -- 記法を除去したプレーンテキスト
    page_date        DATE,                  -- タイトルから解析した日付
    scrapbox_updated BIGINT,               -- Scrapboxのupdatedタイムスタンプ
    fetched_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project, page_title)
);
```

---

## 自分の投稿のみ抽出（複数人プロジェクト対応）

stallプロジェクトは複数人が同じ日付ページに書く形式。
1ページに `[health.icon]`（自分）、`[C5H4N4.icon]`（他者）、`[t3.icon]`（他者）などが混在する。

**自分のアイコン**: `health.icon`

### アイコン記法の2つの使われ方

1. **セクション先頭に単独で置く**（行全体がアイコン記法のみ）→「ここから自分のセクション」
2. **行末に署名として添える**（`今日は楽しかった [health.icon]`）→ セクション開始とは見なさない

`stripped == f"[{icon}]"` の完全一致判定により、行末署名はセクション開始と見なされない。

### 実データ構造（2026/03/25）

```
2026/03/25
[C5H4N4.icon]
　雨ふり
 　左足が濡れた
[health.icon]
	[超寝た]
	[他人事ラジオ]の動画をyoutubeにアップした

[trotsuki.icon]
　トリッカルのイベスト...

[2026/03/24]←2026/03/25→[2026/03/26]
```

**インデントの特徴**
- タブ（`\t`）・全角スペース（`\u3000`）・半角スペース（` `）が混在
- インデントはリスト構造の表現であり、書き方は人・状況によって自由
- ページ末尾に `[前日]←日付→[翌日]` のナビゲーション行がある（除外対象）

### 抽出ロジック（確定版）

インデントの有無に関わらず、自分のアイコン行から次のアイコン行までの全行を取得する。

```python
import re

# ナビゲーション行のパターン: [2026/03/24]←2026/03/25→[2026/03/26]
NAV_PATTERN = re.compile(r'.*←\d{4}/\d{2}/\d{2}→.*')

def extract_my_entries(text: str, my_icons: list) -> str:
    """
    自分のアイコン行から次のアイコン行までの全行を抽出する。
    インデントの有無は問わない。
    """
    lines = text.split("\n")
    my_sections = []
    in_my_section = False
    icon_pattern = re.compile(r'^\[[\w\.]+\.icon\]$')

    for line in lines:
        stripped = line.strip()

        # 自分のアイコン行 → セクション開始
        if any(f"[{icon}]" == stripped for icon in my_icons):
            in_my_section = True
            continue

        # 他人のアイコン行 → セクション終了
        if icon_pattern.match(stripped) and in_my_section:
            in_my_section = False
            continue

        if in_my_section:
            if NAV_PATTERN.match(stripped):
                continue
            clean = strip_scrapbox_notation(stripped)
            if clean:
                my_sections.append(clean)

    return "\n".join(my_sections).strip()


def strip_scrapbox_notation(text: str) -> str:
    """Scrapbox記法を除去してプレーンテキストに変換"""
    # [* 見出し] → 見出し
    text = re.sub(r'\[\*+\s+(.*?)\]', r'\1', text)
    # [テキスト URL] → テキスト
    text = re.sub(r'\[([^\]]+?)\s+https?://[^\]]+\]', r'\1', text)
    # [URL] → 除去
    text = re.sub(r'\[https?://[^\]]+\]', '', text)
    # [リンク] → リンク
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)
    return text.strip()
```

**2026/03/25 の抽出結果**
```
超寝た
他人事ラジオの動画をyoutubeにアップした
```

---

## Scrapbox記法の除去

サマリー生成に渡す際はScrapbox記法を除去してプレーンテキストにする（上記 `strip_scrapbox_notation` を使用）。

---

## サマリーへの統合

日次サマリー生成時にその日のScrapbox日記を一緒に渡す。

```
日次サマリーの入力:
├── SNS投稿（Misskey・Mastodon）
├── 音楽再生履歴（Last.fm）
├── ヘルスデータ
├── 天気
└── Scrapbox日記（当日のページ）← 追加
```

SNS投稿は断片的だが、Scrapboxにまとめて書いた日記があれば
その日の文脈・気持ち・出来事が補完されてサマリーの質が大きく上がる。

---

## data_sourcesへの登録

```sql
INSERT INTO data_sources (name, type, base_url, account, is_active) VALUES
  ('Cosense stall', 'scrapbox', 'https://scrapbox.io/stall', NULL, TRUE);
```

---

## settings.tomlへの追加

```toml
[scrapbox]
project       = "stall"
my_icons      = ["health.icon"]
lookback_days = 30
```

---

## 収集頻度

- `cron`: 毎日 AM 6:00（サマリー生成前に実行）
- 直近30日分をチェック（追記対応）

---

## 注意事項

- ページタイトルはスラッシュ区切り（`YYYY/MM/DD`）。URLエンコード必須
- `updated` フィールドはUnix timestamp（秒）
- Scrapboxは2024年5月にCosenseに改名されたがAPIのURLは変わらない
- 公開プロジェクトのため認証不要。非公開に変更された場合は `connect.sid` が必要になる
