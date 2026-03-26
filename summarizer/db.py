"""PostgreSQL 接続。`config/settings.toml` はダッシュボード (`dashboard/app.py`) と同一。"""

from pathlib import Path

import tomllib

try:
    import psycopg2
except ImportError as e:
    raise ImportError(
        "psycopg2 がインストールされていません。リポジトリの venv で実行してください: "
        "`./venv/bin/python -m summarizer.generate ...` "
        "または `source venv/bin/activate` のあと同コマンド。"
    ) from e

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.toml"


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_conn():
    db = load_config()["database"]
    return psycopg2.connect(
        host=db["host"],
        port=db["port"],
        dbname=db["name"],
        user=db["user"],
        password=db["password"],
    )
