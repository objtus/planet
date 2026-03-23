# GitHub API 仕様メモ

## 基本情報

- ベースURL: `https://api.github.com/`
- 認証: `Authorization: Bearer <token>` ヘッダー
- レート制限: 認証あり5000リクエスト/時間

## 使用するエンドポイント

### GET /users/:username/events — ユーザーのイベント一覧

```
GET https://api.github.com/users/<username>/events
```

**クエリパラメータ**
| パラメータ | 説明 |
|---|---|
| per_page | 件数（最大100）|
| page | ページ番号 |

**使用するイベントタイプ**
- `PushEvent`: コミット（`payload.commits` で件数取得）
- `CreateEvent`: ブランチ・タグ作成
- `ReleaseEvent`: リリース作成

**レスポンス例**
```json
[
  {
    "id": "12345678",
    "type": "PushEvent",
    "repo": {"name": "username/repo-name"},
    "payload": {
      "commits": [{"message": "コミットメッセージ"}],
      "size": 3
    },
    "created_at": "2026-03-22T10:00:00Z"
  }
]
```

## Personal Access Tokenの取得

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
権限: `public_repo` の読み取りのみ（最小権限）

## 注意事項

- イベントは最新300件のみ取得可能（1日1回取得していれば問題なし）
- `PushEvent` の `payload.size` がコミット件数
- リポジトリURLは `https://github.com/<repo.name>` で生成
