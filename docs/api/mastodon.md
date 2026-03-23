# Mastodon API 仕様メモ

## 基本情報

- プロトコル: REST（**GETリクエスト**）※MisskeyはPOSTだが、MastodonはGET
- ベースURL: `https://<instance>/api/v1/`
- 認証: **認証あり**（`Authorization: Bearer <token>` ヘッダー）
- レート制限: 通常300リクエスト/5分。`Retry-After` ヘッダーを尊重する

## 取得できる投稿範囲

| 公開範囲 | 認証なし | 認証あり |
|---|---|---|
| public | ○ | ○ |
| unlisted（未収載）| ✗ | ○（自分のアカウントのみ）|
| private（フォロワー限定）| ✗ | ○（自分のアカウント・ホームTL経由）|
| direct | ✗ | ✗ |

---

## アクセストークンの取得方法

MastodonはOAuth 2.0フローが必要。自分用なので一度だけやれば永続的に使える。

### Step 1: アプリ登録

```bash
curl -X POST "https://<instance>/api/v1/apps" \
  -F "client_name=planet" \
  -F "redirect_uris=urn:ietf:wg:oauth:2.0:oob" \
  -F "scopes=read:accounts read:statuses" \
  -F "website=https://yuinoid.neocities.org"
```

→ `client_id` と `client_secret` が返ってくる。保存しておく。

### Step 2: ブラウザで認証URLを開く

```
https://<instance>/oauth/authorize?response_type=code&client_id=<client_id>&redirect_uri=urn:ietf:wg:oauth:2.0:oob&scope=read:accounts+read:statuses
```

ブラウザで開いてログイン・認証すると **認証コード** が表示される。

### Step 3: 認証コードをトークンに交換

```bash
curl -X POST "https://<instance>/oauth/token" \
  -F "grant_type=authorization_code" \
  -F "code=<認証コード>" \
  -F "client_id=<client_id>" \
  -F "client_secret=<client_secret>" \
  -F "redirect_uri=urn:ietf:wg:oauth:2.0:oob"
```

→ `access_token` が返ってくる。これを `settings.toml` に保存する。

**取得が必要なインスタンス**
- mastodon.cloud（@objtus）
- mistodon.cloud（@healthcare）

---

## 使用するエンドポイント

### Step 1: accounts/lookup — アカウントIDを取得

```
GET https://<instance>/api/v1/accounts/lookup?acct=<username>
```

**認証ヘッダーあり**
```bash
curl -H "Authorization: Bearer <token>" \
  "https://mistodon.cloud/api/v1/accounts/lookup?acct=healthcare"
```

**レスポンスから使うフィールド**
```json
{
  "id": "123456789",
  "username": "healthcare",
  "statuses_count": 1234
}
```

取得した `id` を `data_sources.config` に保存してキャッシュする：
```json
{"account_id": "123456789"}
```

### Step 2: accounts/:id/statuses — 投稿を取得

```
GET https://<instance>/api/v1/accounts/<account_id>/statuses
```

**クエリパラメータ**
| パラメータ | 型 | 説明 | デフォルト |
|---|---|---|---|
| limit | int | 取得件数（**最大40**）| 20 |
| since_id | string | このIDより新しい投稿を取得（差分取得）| なし |
| max_id | string | このIDより古い投稿を取得（ページネーション）| なし |
| exclude_replies | bool | リプライを除外 | false |
| exclude_reblogs | bool | ブーストを除外 | false |

⚠️ **MisskeyはlimitMax=100、MastodonはlimitMax=40** — ページネーション頻度が違う

**リクエスト例（差分取得）**
```bash
curl -H "Authorization: Bearer <token>" \
  "https://mistodon.cloud/api/v1/accounts/123456789/statuses?since_id=<前回の最新ID>&limit=40"
```

**レスポンス例**
```json
[
  {
    "id": "100568890763831149",
    "created_at": "2018-08-18T02:31:30.000Z",
    "content": "<p>投稿テキスト（HTML形式）</p>",
    "spoiler_text": "",
    "visibility": "public",
    "url": "https://mistodon.cloud/@healthcare/100568890763831149",
    "replies_count": 0,
    "reblogs_count": 0,
    "favourites_count": 3,
    "reblog": null,
    "in_reply_to_id": null,
    "media_attachments": []
  }
]
```

**ブーストの判定**
```python
is_boost = status.get("reblog") is not None
# reblog フィールドにブースト元の投稿オブジェクトが入っている
```

---

## 差分取得の実装

```python
headers = {"Authorization": f"Bearer {access_token}"}

# DBから該当source_idの最新 original_id を取得
latest_id = db.query(
    "SELECT original_id FROM logs WHERE source_id = %s "
    "ORDER BY timestamp DESC LIMIT 1",
    [source_id]
)

params = {"limit": 40}
if latest_id:
    params["since_id"] = latest_id

response = requests.get(
    f"{instance}/api/v1/accounts/{account_id}/statuses",
    headers=headers,
    params=params
)
```

---

## content フィールドの処理

MastodonのcontentはHTML形式。保存前にBeautifulSoupでテキスト抽出：

```python
from bs4 import BeautifulSoup

def strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text()
```

---

## settings.tomlの設定例

```toml
[[mastodon_accounts]]
name        = "mistodon.cloud @healthcare"
instance    = "https://mistodon.cloud"
username    = "healthcare"
token       = "your_token_here"
source_id   = 3   # data_sourcesテーブルのID

[[mastodon_accounts]]
name        = "mastodon.cloud @objtus"
instance    = "https://mastodon.cloud"
username    = "objtus"
token       = "your_token_here"
source_id   = 6
```

---

## エラーハンドリング

| ステータス | 内容 | 対処 |
|---|---|---|
| 401 | 認証失敗 | トークンを確認 |
| 404 | アカウントが見つからない | IDを確認 |
| 410 | アカウント停止 | 対象アカウントの状態確認 |
| 422 | バリデーションエラー | パラメータを確認 |
| 429 | レート制限 | `Retry-After` ヘッダーの秒数だけ待機 |
| 503 | サーバー利用不可 | インスタンスの状態を確認 |

---

## 注意事項

- `content` はHTML形式（MisskeyのMFMとは異なる）→ BeautifulSoupでテキスト抽出
- `spoiler_text` が空でない場合はCW投稿。ダッシュボードで折りたたみ表示
- `reblog` フィールドが null でない場合はブースト（元投稿の内容が `reblog` オブジェクトに入っている）
- `visibility` フィールドで公開範囲を直接確認できる（`public` / `unlisted` / `private` / `direct`）
- **MisskeyはPOST、MastodonはGET** — リクエスト方式が違うので注意
- **MisskeyはlimitMax=100、MastodonはlimitMax=40** — ページネーション頻度が違う
- Mastodon v4.3.0以降はPKCEサポートあり。今回は自分用なので従来のAuthorization Codeフローで十分
