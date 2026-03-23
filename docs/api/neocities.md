# Neocities API 仕様メモ

## 基本情報

- ベースURL: `https://neocities.org/api/`
- 認証: APIキー（`Authorization: Bearer <api_key>`）または Basic認証（user:pass）
- **APIキーを推奨**（パスワードをスクリプトに書かなくて済む）

## APIキーの取得

```bash
curl -u "USERNAME:PASSWORD" "https://neocities.org/api/key"
# → {"result": "success", "api_key": "xxxxxxxxxxxxxxxx"}
```

## 使用するエンドポイント

### POST /api/upload — ファイルをアップロード

```python
import requests

def upload_to_neocities(api_key: str, files: dict):
    """
    files: {neocities上のパス: ローカルファイルパス}
    例: {"planet/index.html": "/home/user/planet/build/index.html"}
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    upload_files = {}
    for remote_path, local_path in files.items():
        upload_files[remote_path] = open(local_path, "rb")
    
    response = requests.post(
        "https://neocities.org/api/upload",
        headers=headers,
        files=upload_files
    )
    return response.json()
```

**注意**: 1リクエストで複数ファイルをアップロード可能。ディスク容量の上限内であれば制限なし。

### GET /api/list — ファイル一覧の取得

```bash
curl -H "Authorization: Bearer <api_key>" "https://neocities.org/api/list"
```

## Planetシステムでのアップロード先

| ファイル | Neocities上のパス |
|---|---|
| Planetページ | `planet/planet_main.html` |
| 週次サマリー | `planet/summaries/YYYY-WNN.html` |
| 月次サマリー | `planet/summaries/YYYY-MM.html` |

## 注意事項

- 既存ファイルへのアップロードは上書き
- 無料プランではアップロード可能なファイル形式に制限あり（html/css/js/画像等は問題なし）
- 1日1回（AM 7:00）の更新なのでレート制限は問題にならない
