# Last.fm API 仕様メモ

## 基本情報

- ベースURL: `https://ws.audioscrobbler.com/2.0/`
- 認証: APIキーをクエリパラメータに含める（ユーザー認証不要で読み取り可能）
- レート制限: 明示的な制限なし。連続リクエストは0.2〜0.5秒間隔を推奨
- 必須ヘッダー: `User-Agent: planet/<version> (contact@example.com)` （識別可能なものを設定）

## 使用するエンドポイント

### user.getRecentTracks — 再生履歴を取得

```
GET https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&...
```

**パラメータ**
| パラメータ | 型 | 説明 |
|---|---|---|
| method | string | `user.getrecenttracks`（固定）|
| user | string | Last.fmユーザー名（例: `objtus`）|
| api_key | string | APIキー（必須）|
| format | string | `json` を指定 |
| limit | int | 1ページの件数（最大200）|
| page | int | ページ番号（デフォルト1）|
| from | int | UNIX timestamp（この時刻以降を取得、差分取得に使用）|
| to | int | UNIX timestamp（この時刻以前を取得）|

**差分取得**: `from` に前回取得した最新の再生時刻のUNIX timestampを指定する。

**レスポンス例**
```json
{
  "recenttracks": {
    "@attr": {"page": "1", "total": "12345", "totalPages": "62"},
    "track": [
      {
        "artist": {"#text": "Tame Impala"},
        "name": "Feels Like We Only Go Backwards",
        "album": {"#text": "Lonerism"},
        "url": "https://www.last.fm/music/Tame+Impala/_/Feels+Like+We+Only+Go+Backwards",
        "date": {"uts": "1603188238", "#text": "20 Oct 2020, 10:03"}
      }
    ]
  }
}
```

## 注意事項

- `@attr: {nowplaying: "true"}` がある場合は再生中のトラック（日時なし）。スキップする。
- `track_id` は `"artist::track::uts"` の形式で生成して重複防止に使う
- APIキーの取得: https://www.last.fm/api/account/create
