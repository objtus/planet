# Misskey API 仕様メモ

## 基本情報

- プロトコル: REST（**POSTリクエスト**、JSONボディ）※GETではない
- ベースURL: `https://<instance>/api/`
- 認証: **認証あり**（アクセストークンをボディの `i` パラメータに含める）
- Content-Type: `application/json`（必須）
- レート制限: インスタンスによる。連続リクエストは0.5〜1秒間隔推奨

## 取得できる投稿範囲

| 公開範囲 | 認証なし | 認証あり |
|---|---|---|
| public | ○ | ○ |
| home（ホームのみ）| ✗ | ○ |
| followers（フォロワー限定）| ✗ | ○（自分のアカウントのみ）|
| specified（ダイレクト）| ✗ | ✗ |

---

## アクセストークンの取得方法（手動発行・自分用）

1. 各インスタンスにログイン
2. **設定 → API**
3. 「アクセストークンを発行する」
4. 権限: **`read:account` のみ**（最小権限）
5. 表示されたトークンを `settings.toml` に保存（**再表示不可**）

取得したトークンは `settings.toml` の該当インスタンス設定に記載する（後述）。

---

## 使用するエンドポイント

### Step 1: users/show — ユーザーIDを取得

```
POST https://<instance>/api/users/show
```

**リクエストボディ**
```json
{
  "i": "<アクセストークン>",
  "username": "yuinoid",
  "host": null
}
```

リモートユーザー（別インスタンスのアカウントを自インスタンスから見る）の場合：
```json
{
  "i": "<アクセストークン>",
  "username": "health",
  "host": "tanoshii.site"
}
```

**レスポンスから使うフィールド**
```json
{
  "id": "8wm5exampleid",
  "username": "yuinoid",
  "notesCount": 9012
}
```

取得した `id` を `data_sources.config` に保存してキャッシュする：
```json
{"user_id": "8wm5exampleid"}
```

### Step 2: users/notes — ユーザーのノートを取得

```
POST https://<instance>/api/users/notes
```

**リクエストボディ**
```json
{
  "i": "<アクセストークン>",
  "userId": "<Step1で取得したID>",
  "limit": 100,
  "sinceId": "<前回取得した最新ID（差分取得）>",
  "withRenotes": true,
  "withReplies": true
}
```

**主要パラメータ**
| パラメータ | 型 | 説明 | デフォルト |
|---|---|---|---|
| i | string | アクセストークン（必須）| |
| userId | string | ユーザーID（必須）| |
| limit | int | 取得件数（最大100）| 10 |
| sinceId | string | このIDより新しいノートを取得（差分取得）| なし |
| untilId | string | このIDより古いノートを取得（ページネーション）| なし |
| withRenotes | bool | リノートを含める | true |
| withReplies | bool | リプライを含める | false |

**レスポンス例**
```json
[
  {
    "id": "abc123",
    "createdAt": "2026-03-22T10:00:00.000Z",
    "text": "投稿テキスト（MFM形式）",
    "cw": null,
    "visibility": "public",
    "renoteCount": 5,
    "repliesCount": 2,
    "reactionCount": 13,
    "replyId": null,
    "renoteId": null,
    "files": []
  }
]
```

**純粋なリノートの判定**
```python
# renoteId があり text が null → 純粋なリノート
is_pure_renote = note.get("renoteId") and not note.get("text")
```

---

## 差分取得の実装

```python
# DBから該当source_idの最新 original_id を取得
latest_id = db.query(
    "SELECT original_id FROM logs WHERE source_id = %s "
    "AND metadata->>'type' != 'renote' "
    "ORDER BY timestamp DESC LIMIT 1",
    [source_id]
)

body = {
    "i": access_token,
    "userId": user_id,
    "limit": 100,
    "sinceId": latest_id,  # Noneの場合はキーごと省略
    "withRenotes": True,
    "withReplies": True,
}
if latest_id is None:
    del body["sinceId"]
```

---

## visibilityの判定

APIレスポンスの `visibility` フィールドを直接使用：
```python
visibility = note.get("visibility")
# "public" / "home" / "followers" / "specified"
```

---

## URLの生成

```python
url = f"https://{instance}/notes/{note['id']}"
# 例: https://misskey.io/notes/abc123
```

---

## settings.tomlの設定例

```toml
[[misskey_accounts]]
name        = "misskey.io @yuinoid"
instance    = "https://misskey.io"
username    = "yuinoid"
token       = "your_token_here"
source_id   = 1   # data_sourcesテーブルのID（初回セットアップ後に設定）

[[misskey_accounts]]
name        = "tanoshii.site @health"
instance    = "https://tanoshii.site"
username    = "health"
token       = "your_token_here"
source_id   = 2

[[misskey_accounts]]
name        = "msk.ilnk.info @google"
instance    = "https://msk.ilnk.info"
username    = "google"
token       = "your_token_here"
source_id   = 5

[[misskey_accounts]]
name        = "misskey.io @vknsq"
instance    = "https://misskey.io"
username    = "vknsq"
token       = "your_token_here"
source_id   = 7

[[misskey_accounts]]
name        = "sushi.ski @idoko"
instance    = "https://sushi.ski"
username    = "idoko"
token       = "your_token_here"
source_id   = 4
```

---

## エラーハンドリング

| ステータス / コード | 内容 | 対処 |
|---|---|---|
| 400 / `INVALID_PARAM` | パラメータ不正 | リクエスト内容を確認 |
| 400 / `NO_SUCH_USER` | ユーザーが見つからない | ユーザー名・IDを確認 |
| 401 / `CREDENTIAL_REQUIRED` | 認証が必要 | トークンを確認 |
| 403 / `YOUR_ACCOUNT_SUSPENDED` | アカウント停止 | 対象アカウントの状態確認 |
| 429 | レート制限 | 待機してリトライ（指数バックオフ）|
| 503 | サーバー利用不可 | インスタンスの状態を確認 |

**エラーレスポンス形式**
```json
{
  "error": {
    "message": "No such user.",
    "code": "NO_SUCH_USER",
    "id": "1acefcb5-...",
    "kind": "client"
  }
}
```

---

## 注意事項

- `text` はMFM（Misskey Flavored Markdown）形式。MFM記法（`$[x2 ...]` 等）はテキスト保存時に除去する
- `cw` が null でない場合はCW投稿。ダッシュボードで折りたたみ表示
- `files` が空でない場合は `has_files = TRUE` として記録
- misskey.ioに複数アカウント（@yuinoid と @vknsq）があるが、インスタンスは同じなので `users/show` のホストは同一
- Misskeyのフォーク（Sharkey等）も基本的に同じAPIで動作
