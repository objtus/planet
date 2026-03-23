# セットアップ手順書

サーバーを移行・再構築した際の手順書。

---

## 前提条件

- Ubuntu（自宅サーバー）
- Tailscaleインストール・設定済み
- Ollama + Open WebUI インストール済み

---

## Step 1: 必要パッケージのインストール

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib git
```

## Step 2: PostgreSQLのセットアップ

```bash
# PostgreSQLの起動・自動起動設定
sudo systemctl start postgresql
sudo systemctl enable postgresql

# データベースとユーザーの作成
sudo -u postgres psql << 'SQL'
CREATE USER planet WITH PASSWORD 'your_password_here';
CREATE DATABASE planet OWNER planet;
GRANT ALL PRIVILEGES ON DATABASE planet TO planet;
SQL
```

## Step 3: pg_bigm拡張の導入（日本語全文検索）

```bash
# pg_bigmのインストール
sudo apt install -y postgresql-server-dev-all build-essential
git clone https://github.com/pgbigm/pg_bigm.git
cd pg_bigm
make USE_PGXS=1
sudo make USE_PGXS=1 install

# 拡張の有効化
sudo -u postgres psql planet -c "CREATE EXTENSION pg_bigm;"
```

## Step 4: リポジトリのクローン

```bash
cd ~
git clone <repository_url> planet
cd planet
```

## Step 5: Python仮想環境のセットアップ

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask psycopg2-binary requests feedparser beautifulsoup4 pylast tomllib
```

## Step 6: 設定ファイルの作成

```bash
cp config/settings.toml.example config/settings.toml
# settings.tomlを編集してAPIキー・DB接続情報を入力
```

## Step 7: DBスキーマの作成

```bash
psql -U planet -d planet -f docs/schema.sql
```

## Step 8: OllamaのModelダウンロード

```bash
ollama pull gemma3:12b
```

## Step 9: Flaskアプリの起動確認

```bash
source venv/bin/activate
cd dashboard
python app.py
# http://<tailscale-ip>:5000 でアクセス確認
```

## Step 10: cronの設定

```bash
crontab docs/cron/crontab.txt
```

## Step 11: バックアップの設定

```bash
# rcloneのインストール
sudo apt install rclone

# pCloudの設定
rclone config
# → pCloudを選択してOAuth認証

# バックアップスクリプトのテスト
bash backup/backup.sh
```

---

## settings.toml の構造

```toml
[database]
host = "localhost"
port = 5432
name = "planet"
user = "planet"
password = "your_password_here"

[ollama]
model = "gemma3:12b"
base_url = "http://localhost:11434"

[weather]
lat = 35.1815
lon = 136.9066

[neocities]
api_key = "your_neocities_api_key"

[lastfm]
api_key = "your_lastfm_api_key"
username = "objtus"

[github]
token = "your_github_pat"
username = "your_github_username"

[youtube]
api_key = "your_youtube_api_key"
channel_id = "your_channel_id"
```
