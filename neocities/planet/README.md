# Neocities 用 Planet クライアント

`https://data.idoko.org/planet-meta.json` と `planet-data.json` を読み、カレンダー・ヒートマップ・タイムラインを描画する静的ページです。

## アップロードするファイル

Neocities のサイトルートから次のパスに配置してください（例: `yuinoid.neocities.org`）。

**よくある誤り**: `mockup/neocities_planet_mockup.html` や、ファイル末尾が巨大な `<script>…const DAYS_JA…</script>` で終わる HTML を `index.html` にすると、**ずっとモックデータのまま**になります。必ず **`planet/index.html`（行数はおおよそ 800 台・`</body>` 直前が `planet-app.js` 1行だけ）** を使ってください。

| パス | 説明 |
|------|------|
| `/planet/index.html` | 本番 HTML |
| `/planet/planet-app.js` | 描画ロジック（`ICON_BASE = '/planet/icons/'`） |
| `/planet/icons/*` | ソースアイコン（**手動**・`.webp` / `.svg` / `.png` 可） |

サイト共通の `/1column.css`、`/js/jquery-3.6.0.min.js`、`/js/main.js` は既存 Neocities サイト側のものをそのまま利用します。

## アイコン（手動アップロード）

`planet-meta.json` の `sources[]` を **`/planet/icons/`** のファイル名と突き合わせます。

**表示の優先度**（`planet-app.js`）: `icon_emoji` → `icon_url` → `favicon`（`/planet/icons/` + 拡張子フォールバック）→ 種別の既定絵文字。

- **`favicon`**: 既定は `build_feed` が `display_utils.favicon_filename` で付与。`config/settings.toml` の **`[planet_feed.source_display.<id>]`** で **`icon_file`** を書けばファイル名を直接指定できます。
- **`icon_emoji`**: 同じく `source_display` の **`icon_emoji`** → JSON に載り、**画像なしでその文字だけ**表示。
- **`icon_url`**: **`icon_url`** で任意の **絶対 URL** の画像を指定（Neocities 非配置でも可）。

拡張子: `favicon` が `.webp` でも Neocities に `.svg` だけある場合、同一ベース名で **`.svg` → `.webp` → `.png`** を試します。

### `publisher/display_utils.py` の `favicon_filename` と一致する名前（参考）

**ドメイン連動（アクティブ Misskey/Mastodon/RSS ホスト）**

- `misskeyio.webp`, `tanoshii.webp`, `sushi.webp`, `mistodon.webp`, `mastocloud.webp`, `ilnk.webp`, `pon.webp`, `groundpolis.webp`, `neocities.webp`

**種別固定**

- `lastfm.webp`, `github.webp`, `youtube.webp`, `scrapbox.webp`, `netflix.webp`, `prime.webp`, `health.webp`, `photo.webp`, `screen_time.webp`, `weather.webp`

**RSS（ドメインマップ外）**

- `rss_<source_id>.webp`（例: `rss_5.webp`）

**非アクティブソース**

- `src<source_id>.webp`（例: `src15.webp`）

新しいソースを DB に追加したあとは、`build_feed` 出力の `planet-meta.json` の `sources` を見て、列挙された `favicon` ファイルをすべて `icons/` に置くのが確実です。

```bash
curl -sS https://data.idoko.org/planet-meta.json | jq -r '.sources[].favicon' | sort -u
```

## ローカルでの動作確認

ブラウザで `file://` から開くと **別オリジンへの fetch は CORS で失敗**します。次のいずれかで確認してください。

- Neocities に仮アップロードして本番 URL で開く
- ローカルで HTTP サーバを立て、**ページのオリジン**から見て JSON が `data.idoko.org` に向かう（ページは `localhost`、JSON はクロスオリジンで CORS 許可済みなら可）

## タイムライン連続折りたたみ

`planet-meta.json` に `timeline_collapse` があるときのみ有効（`build_feed` が `config/settings.toml` の `timeline_collapse_types` 等から出力）。同一 `src_type` が `min_run` 件以上連続すると先頭 1 件を残し「ほか N 件（時刻範囲） 展開」で畳む。設定は **`docs/planet_feed_setup.md`** を参照。

## 関連ドキュメント

- `docs/planet_feed_setup.md` — JSON 生成・CORS・cron
- `mockup/neocities_planet_mockup.html` — 見た目のモック（本番は `index.html` + `planet-app.js`）
