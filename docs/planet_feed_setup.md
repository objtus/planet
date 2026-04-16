# planet-feed セットアップ手順

Planetページ用のデータJSON（過去30日分）をCloudflare Pagesで配信するための設定手順。

**※対象外**: 雑記への週次・月次サマリー HTML の Neocities アップロードは別ルート（`docs/phase6_plan.md` の **M4**、`docs/design.md` §8）。

**配信URL**: `https://data.idoko.org/planet-data.json`  
**リポジトリ**: `github.com/objtus/planet-feed`  
**ローカルパス**: `~/planet-feed/`

---

## 構成概要

```
【自宅サーバー】
publisher/build_feed.py
    ↓ 過去30日分のJSON生成
    ↓ ~/planet-feed/ に書き出し
    ↓ git push

【GitHub】
planet-feed リポジトリ（objtus/planet-feed）
    ↓ push を検知して自動デプロイ

【Cloudflare Pages】
data.idoko.org/planet-data.json  ← タイムライン・日別集計
data.idoko.org/planet-meta.json  ← ソース一覧（軽量）

【Neocities】
yuinoid.neocities.org/planet/index.html + planet-app.js + planet/icons/*
    ↓ fetch("https://data.idoko.org/planet-meta.json" / planet-data.json)
    ↓ 描画（実装: 本リポジトリ neocities/planet/）
```

---

## セットアップ状況 ✅ 完了済み

| ステップ | 内容 | 状態 |
|---|---|---|
| 1 | GitHubリポジトリ作成（objtus/planet-feed）| ✅ |
| 2 | 自宅サーバーでクローン（~/planet-feed/）| ✅ |
| 3 | _headersファイル作成・push（CORS設定）| ✅ |
| 4 | Cloudflare Pagesプロジェクト作成・GitHub連携 | ✅ |
| 5 | カスタムドメイン設定（data.idoko.org）| ✅ |
| 6 | 動作確認（curl https://data.idoko.org/test.json）| ✅ |

---

## ディレクトリ構成（現在）

```
~/planet-feed/              ← Cloudflare Pages用リポジトリ
├── _headers                ← CORS設定（完了）
└── README.md
```

---

## _headersの内容（CORS設定）

```
/planet-data.json
  Access-Control-Allow-Origin: https://yuinoid.neocities.org
  Cache-Control: max-age=3600

/planet-meta.json
  Access-Control-Allow-Origin: https://yuinoid.neocities.org
  Cache-Control: max-age=3600
```

---

## publisher/build_feed.py（実装済み）

本リポジトリの `publisher/` で JSON を生成し、`planet-feed` クローンへ書き出して git で **1 コミット**にまとめて push する（`planet-data.json` と `planet-meta.json` を同時に add）。

### 実行例（planet リポジトリルート）

```bash
./venv/bin/python -m publisher.build_feed --dry-run    # 件数のみ確認
./venv/bin/python -m publisher.build_feed --no-push   # JSON のみ（git なし・初回検証向け）
./venv/bin/python -m publisher.build_feed            # 既定: 変更があれば commit + push
```

- **リポジトリパス**: 既定 `~/planet-feed`。`config/settings.toml` の `[planet_feed] repo_path` で上書き可。**`settings.toml.example` の `/home/you/...` はプレースホルダ**のままにすると、cron 実行時に `/home/you` への作成で `PermissionError` になり得ます（必ず実在するクローン先を書く）。
- **push**: 既定は有効。`[planet_feed] push = false` で commit のみ（または `./venv/bin/python -m publisher.build_feed --push` で強制 push）。
- **Fediverse 可視性**: planet-feed では Misskey を **`public` / `home`**、Mastodon を **`public` / `unlisted`** のみ含める（`followers` / `direct` / `specified` 等は除外）。`timeline` の各要素は **`visibility` キーは半公開（`home` / `unlisted`）の行にだけ付与**し、公開は省略する。
- **ヒートマップとの差**: ダッシュボード `/api/heatmap` の「投稿」は Misskey/Mastodon を **visibility 無差別**で数える。planet-feed の `days.posts` は Fediverse 部分が上記で絞られるため、**ダッシュボードの数値と一致しない**ことがある。
- **`days.posts`**: `misskey` / `mastodon` / `rss` / `youtube` を含む。タイムライン（GitHub・Scrapbox 等）の件数とは元より一致しない場合がある。
- **sources**: カレンダーと同様、**全 `data_sources` 行**（非アクティブ含む）を出力。

設定例は `config/settings.toml.example` の `[planet_feed]` を参照。アイコン・絵文字の直接指定は **`[planet_feed.source_display.<id>]`**、タイムライン連続折りたたみは **`timeline_collapse_types`** / **`timeline_collapse_min_run`**。

---

## JSONフォーマット仕様

### planet-meta.json（軽量・ソース一覧）

```json
{
  "generated_at": "2026-04-03T07:00:00+09:00",
  "latest_date": "2026-04-02",
  "oldest_date": "2026-03-04",
  "sources": [
    {
      "id": 1,
      "name": "misskey.io @yuinoid",
      "short_name": "msk.io",
      "type": "misskey",
      "favicon": "misskeyio.webp"
    },
    {
      "id": 7,
      "name": "OpenWeatherMap",
      "short_name": "weather",
      "type": "weather",
      "icon_emoji": "🌤️"
    },
    {
      "id": 8,
      "name": "GitHub",
      "short_name": "github",
      "type": "github",
      "icon_url": "https://github.githubassets.com/favicons/favicon.svg"
    }
  ],
  "days": {
    "2026-04-02": {
      "posts": 12,
      "plays": 34,
      "steps": 7842,
      "weather": {
        "temp_max": 18,
        "icon": "☀️",
        "desc": "晴れ"
      }
    }
  }
}
```

`sources[]` の **任意キー**（`config/settings.toml` の `[planet_feed.source_display.<source_id>]` で付与）:

| キー | 意味 |
|------|------|
| `icon_emoji` | 画像を使わずこの文字だけ表示（`favicon` / `icon_url` は出力しない） |
| `icon_url` | 画像の絶対 URL（Neocities の `/planet/icons/` を経由しない） |
| `favicon` | 既定は自動。`icon_file` で上書きしたファイル名（`/planet/icons/` 相対） |

**任意トップレベル** `timeline_collapse`（`config/settings.toml` の **`[planet_feed]` 直下** の `timeline_collapse_types` / `timeline_collapse_min_run` から生成。誤って `source_display` 内に書いた場合は build_feed がフォールバックで読むが、ログに警告が出る）:

```json
"timeline_collapse": {
  "types": ["lastfm"],
  "min_run": 3
}
```

- `types`: 連続していればまとめる `src_type`（例: Last.fm のみ。Misskey/Mastodon は含めない想定）
- `min_run`: この件数以上の連続で折りたたみ（2 未満にはならない。既定 3）

未設定時はキー自体を出さず、Neocities クライアントは従来どおり 1 行 1 件。

### planet-data.json（タイムライン全件）

```json
{
  "generated_at": "2026-04-03T07:00:00+09:00",
  "timeline": [
    {
      "date": "2026-04-02",
      "time": "10:32",
      "src_id": 2,
      "src_type": "misskey",
      "text": "らくがきしたい",
      "url": "https://tanoshii.site/notes/abc123",
      "is_boost": false,
      "has_media": false,
      "visibility": "home"
    }
  ]
}
```

- `visibility`: **任意**。Misskey/Mastodon で **`home` または `unlisted` のときだけ**付く（公開投稿にはキーなし）。Neocities クライアントが半公開マーク表示に利用。

---

## cron（`cron/crontab.txt`）

### サーバのタイムゾーン（JST 推奨）

[cron/crontab.txt](cron/crontab.txt) の「時」は **OS のローカルタイムゾーン**に従う。`Etc/UTC` のままだと、コメントの「朝 6 時」「7 / 15 / 23 時」は **UTC の時刻**として解釈され、JST とずれる。

**ローカルを JST にする（Ubuntu / systemd）:**

```bash
sudo timedatectl set-timezone Asia/Tokyo
timedatectl   # Time zone: Asia/Tokyo (JST, +0900) になることを確認
```

変更後は **cron 行の数字はそのままで、発火が日本時間基準になる**（毎時収集・日次 6 時・`build_feed` の 7/15/23 が意図どおり揃う）。

### `build_feed` の登録

リポジトリに `PUBLISHER_LOG` と **1 日 3 回（7 / 15 / 23 時・上記 JST ローカル想定）**の `build_feed` 行を追加済み。実際の crontab へ反映するには `crontab -e` で該当行をマージするか、`crontab /home/objtus/planet/cron/crontab.txt` で全体を上書き（他ジョブと重複に注意）。

```cron
PUBLISHER_LOG=/home/objtus/planet/cron/publisher.log
0 7,15,23 * * * cd $PLANET && $PYTHON -m publisher.build_feed >> $PUBLISHER_LOG 2>&1
```

---

## Neocities 側の静的クライアント（Phase 6 M5）

実装は本リポジトリの **`neocities/planet/`**（`index.html` + `planet-app.js`）。Neocities へ手動アップロードするファイル構成・アイコン一覧は **`neocities/planet/README.md`** を参照。

- **`file://` で HTML を開いただけでは fetch できない**（null オリジン・CORS）。検証は Neocities 上、またはローカル HTTP サーバでページを配信して行う。
- アイコンは **`/planet/icons/`** に `planet-meta.json` の `sources[].favicon` と同名ファイルを配置（未配置時は JS が絵文字にフォールバック）。
- 半公開マーク: `planet-app.js` の **`SEMI_VISIBILITY_ICON_URL`** が空なら簡素なインライン SVG。`/planet/icons/...` などの **相対 URL を指定すると `<img>` で表示**（PNG/WebP/SVG ファイル可）。

---

## 注意事項

- `planet-feed` リポジトリはpublicのためJSONの内容も公開される
  （Planetページ自体が公開予定のため問題なし）
- git pushごとにCloudflare Pagesが自動デプロイ（通常1〜2分）
- Cloudflare PagesのCDNキャッシュにより更新反映に数分かかる場合がある
- `_headers` ファイルはリポジトリのルートに置くこと
- `_headers` 自体はURLとしてアクセスできない（404が返るのは正常）