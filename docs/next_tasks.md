# 次のタスク

**最終更新**: 2026-03-23

---

## 直近でやること（Phase 1から開始）

### 1. Ubuntuの現状確認
```bash
python3 --version
pip3 --version
psql --version
```

### 2. PostgreSQLのインストールとセットアップ
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo -u postgres psql -c "CREATE USER planet WITH PASSWORD 'password';"
sudo -u postgres psql -c "CREATE DATABASE planet OWNER planet;"
```

### 3. pg_bigm拡張の導入

### 4. スキーマ作成
docs/design.md Section 5 のSQLを実行

### 5. data_sourcesへの初期データ投入

### 6. Python仮想環境とパッケージインストール
```bash
python3 -m venv venv
source venv/bin/activate
pip install flask psycopg2-binary requests feedparser \
            beautifulsoup4 pylast tomllib python-dateutil
```

### 7. settings.toml作成
config/settings.toml.example をコピーして編集

---

## Phase 2（インポート）で必要なもの

- [ ] pon.icuのエクスポートJSONファイルのパス確認
- [ ] mastodon.cloudのエクスポートJSONファイルのパス確認
- [ ] groundpolis.appのエクスポートJSONファイルのパス確認（あれば）
- インポート仕様は docs/importers.md 参照

---

## APIキーの取得が必要なもの

### SNS系（認証あり・トークン取得が必要）

**Misskey（各インスタンスで手動発行）**
各インスタンスにログイン → 設定 → API → アクセストークンを発行
権限: `read:account` のみ

- [x] misskey.io @yuinoid
- [x] misskey.io @vknsq（同じインスタンス、別トークン）
- [x] tanoshii.site @health
- [x] msk.ilnk.info @google
- [x] sushi.ski @idoko

**Mastodon（OAuth 2.0フロー）**
手順は docs/api/mastodon.md 参照（アプリ登録→ブラウザ認証→トークン取得）

- [x] mistodon.cloud @healthcare
- [x] mastodon.cloud @objtus

### その他APIキー

- [x] Last.fm APIキー
- [x] OpenWeatherMap APIキー
- [x] GitHub Personal Access Token
- [ ] YouTube Data API v3 キー（Google Cloud Console）※後回し
- [x] Neocities APIキー

---

## Claude Codeへの渡し方

起動時に以下を読ませる：
1. docs/overview.md
2. docs/current_state.md
3. docs/next_tasks.md

詳細が必要なときに参照させる：
- docs/design.md（スキーマ・全体仕様）
- docs/importers.md（インポーター実装時）
- docs/api/misskey.md（Misskey収集スクリプト実装時）
- docs/api/mastodon.md（Mastodon収集スクリプト実装時）
- docs/api/*.md（各収集スクリプト実装時）
