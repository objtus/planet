# YouTube Data API v3 仕様メモ

## 基本情報

- ベースURL: `https://www.googleapis.com/youtube/v3/`
- 認証: APIキー（公開データの取得のみなのでOAuthは不要）
- クォータ: 10,000ユニット/日（無料）

## 使用するエンドポイント

### search.list + videos.list — 自分のチャンネルの動画一覧

```python
# Step 1: チャンネルの動画を検索
GET https://www.googleapis.com/youtube/v3/search
  ?key=<api_key>
  &channelId=<channel_id>
  &type=video
  &order=date
  &maxResults=50
  &pageToken=<次ページのトークン>

# Step 2: 詳細統計を取得（search.listでは統計が取れないため）
GET https://www.googleapis.com/youtube/v3/videos
  ?key=<api_key>
  &id=<video_id1>,<video_id2>,...
  &part=snippet,statistics,contentDetails
```

**videosレスポンスから使うフィールド**
```json
{
  "id": "dQw4w9WgXcQ",
  "snippet": {
    "publishedAt": "2026-03-01T10:00:00Z",
    "title": "動画タイトル",
    "description": "説明文"
  },
  "statistics": {
    "viewCount": "12345",
    "likeCount": "678",
    "commentCount": "90"
  },
  "contentDetails": {
    "duration": "PT3M33S"  // ISO 8601 duration形式
  }
}
```

## クォータ消費の目安

| 操作 | コスト |
|---|---|
| search.list 1回 | 100ユニット |
| videos.list 1回 | 1ユニット |

1日1回の差分取得なら問題なし。

## チャンネルIDの確認方法

YouTubeチャンネルページ → ソースを表示 → `channelId` を検索

## ISO 8601 duration のパース

```python
import re
def parse_duration(duration: str) -> int:
    """PT3M33S → 213秒"""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    h, m, s = (int(x or 0) for x in match.groups())
    return h * 3600 + m * 60 + s
```

## APIキーの取得

1. Google Cloud Console (https://console.cloud.google.com/)
2. プロジェクト作成 → YouTube Data API v3 を有効化
3. 認証情報 → APIキーを作成
4. キーの制限: IPアドレス制限（サーバーのIPを指定）を推奨
