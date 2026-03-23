"""収集スクリプト共通基底クラス"""

import sys
import json
import tomllib
import psycopg2
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


class BaseCollector:
    def __init__(self):
        self.config = load_config()
        db = self.config["database"]
        self.conn = psycopg2.connect(
            host=db["host"], port=db["port"], dbname=db["name"],
            user=db["user"], password=db["password"],
        )
        self.cur = self.conn.cursor()

    def close(self):
        self.cur.close()
        self.conn.close()

    def get_latest_original_id(self, source_id: int, note_only: bool = False) -> str | None:
        """logsから最新のoriginal_idを取得"""
        if note_only:
            self.cur.execute(
                "SELECT original_id FROM logs WHERE source_id = %s "
                "AND metadata->>'type' = 'note' ORDER BY timestamp DESC LIMIT 1",
                (source_id,)
            )
        else:
            self.cur.execute(
                "SELECT original_id FROM logs WHERE source_id = %s "
                "ORDER BY timestamp DESC LIMIT 1",
                (source_id,)
            )
        row = self.cur.fetchone()
        return row[0] if row else None

    def get_latest_timestamp(self, source_id: int) -> float | None:
        """logsから最新のtimestampをUNIX timestampで取得"""
        self.cur.execute(
            "SELECT EXTRACT(EPOCH FROM timestamp) FROM logs "
            "WHERE source_id = %s ORDER BY timestamp DESC LIMIT 1",
            (source_id,)
        )
        row = self.cur.fetchone()
        return float(row[0]) if row else None

    def insert_log(self, source_id, original_id, content, url, timestamp, metadata: dict) -> int | None:
        """logsに挿入。重複時はNoneを返す。"""
        self.cur.execute(
            """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (source_id, original_id) DO NOTHING
               RETURNING id""",
            (source_id, original_id, content, url, timestamp, json.dumps(metadata))
        )
        row = self.cur.fetchone()
        return row[0] if row else None

    def get_source_config(self, source_id: int) -> dict:
        """data_sources.configを取得"""
        self.cur.execute("SELECT config FROM data_sources WHERE id = %s", (source_id,))
        row = self.cur.fetchone()
        if row and row[0]:
            return row[0]
        return {}

    def update_source_config(self, source_id: int, updates: dict):
        """data_sources.configをマージ更新"""
        self.cur.execute(
            "UPDATE data_sources SET config = COALESCE(config, '{}'::jsonb) || %s::jsonb WHERE id = %s",
            (json.dumps(updates), source_id)
        )

    def commit(self):
        self.conn.commit()
