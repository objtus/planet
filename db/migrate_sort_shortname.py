"""
data_sources テーブルに sort_order・short_name 列を追加するマイグレーション。
実行: python db/migrate_sort_shortname.py
"""

import sys
import tomllib
from pathlib import Path

import psycopg2

ROOT = Path(__file__).parent.parent
with open(ROOT / "config" / "settings.toml", "rb") as f:
    db = tomllib.load(f)["database"]

conn = psycopg2.connect(
    host=db["host"], port=db["port"], dbname=db["name"],
    user=db["user"], password=db["password"],
)
cur = conn.cursor()

try:
    cur.execute("""
        ALTER TABLE data_sources
          ADD COLUMN IF NOT EXISTS sort_order integer,
          ADD COLUMN IF NOT EXISTS short_name  varchar(32)
    """)

    # sort_order が NULL の行だけ初期化（id 順の連番）
    cur.execute("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
          FROM data_sources
        )
        UPDATE data_sources
           SET sort_order = ranked.rn
          FROM ranked
         WHERE data_sources.id = ranked.id
           AND data_sources.sort_order IS NULL
    """)

    cur.execute("ALTER TABLE data_sources ALTER COLUMN sort_order SET NOT NULL")
    cur.execute("ALTER TABLE data_sources ALTER COLUMN sort_order SET DEFAULT 999")

    conn.commit()

    cur.execute("SELECT id, name, sort_order, short_name FROM data_sources ORDER BY sort_order")
    rows = cur.fetchall()
    print("マイグレーション完了:")
    for r in rows:
        print(f"  id={r[0]:2d}  sort={r[2]:2d}  short_name={r[3]!r:12}  {r[1]}")

except Exception as e:
    conn.rollback()
    print(f"エラー: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    cur.close()
    conn.close()
