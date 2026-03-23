"""既存 Misskey 投稿の metadata に media URL をバックフィルする。

has_files=TRUE なのに metadata に 'media' キーがないレコードを対象に、
Misskey API /api/notes/show を叩いて files を取得し logs.metadata を更新する。

使用例:
  cd /home/objtus/planet
  venv/bin/python db/backfill_media.py            # dry-run（件数確認のみ）
  venv/bin/python db/backfill_media.py --apply    # 実際に更新する
  venv/bin/python db/backfill_media.py --apply --source-id 3   # 特定ソースのみ
"""

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

import psycopg2
import requests

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply",     action="store_true", help="実際に DB を更新する（省略時は dry-run）")
    parser.add_argument("--source-id", type=int, default=None, help="対象 source_id を絞る")
    parser.add_argument("--limit",     type=int, default=500, help="1回の実行で更新する最大件数（default: 500）")
    args = parser.parse_args()

    config = load_config()
    db     = config["database"]
    conn   = psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )
    cur = conn.cursor()

    # 廃止サーバー（is_active=FALSE）は API を叩けないので has_files を直接クリア
    cur.execute("""
        UPDATE misskey_posts mp
           SET has_files = FALSE
          FROM data_sources ds
         WHERE mp.source_id = ds.id
           AND ds.is_active = FALSE
           AND mp.has_files = TRUE
    """)
    if cur.rowcount:
        print(f"廃止サーバー分クリア: {cur.rowcount} 件")
        conn.commit()

    # バックフィル対象: has_files=TRUE かつ metadata に media なし（アクティブなソースのみ）
    src_filter = "AND mp.source_id = %s" if args.source_id else ""

    cur.execute(f"""
        SELECT l.id, l.original_id, l.metadata, mp.source_id,
               ds.base_url, ds.name
          FROM misskey_posts mp
          JOIN logs l ON mp.log_id = l.id
          JOIN data_sources ds ON mp.source_id = ds.id
         WHERE mp.has_files = TRUE
           AND ds.is_active = TRUE
           AND (l.metadata IS NULL OR l.metadata->>'media' IS NULL)
           {src_filter}
         ORDER BY l.timestamp DESC
         LIMIT %s
    """, (args.source_id, args.limit) if args.source_id else (args.limit,))
    rows = cur.fetchall()
    print(f"対象: {len(rows)} 件{'（dry-run）' if not args.apply else ''}")

    if not rows or not args.apply:
        cur.close(); conn.close()
        return

    # source_id ごとにトークンを引く
    token_map: dict[int, tuple[str, str]] = {}  # source_id → (instance, token)
    for acc in config.get("misskey_accounts", []):
        token_map[acc["source_id"]] = (acc["instance"], acc["token"])

    updated = 0
    skipped = 0
    for log_id, post_id, metadata, source_id, base_url, src_name in rows:
        instance, token = token_map.get(source_id, (base_url, ""))
        if not instance:
            skipped += 1
            continue

        try:
            resp = requests.post(
                f"{instance}/api/notes/show",
                json={"i": token, "noteId": post_id},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 404:
                # 投稿が削除済み → has_files をクリアして 📎 が出ないようにする
                cur.execute(
                    "UPDATE misskey_posts SET has_files = FALSE WHERE log_id = %s",
                    (log_id,)
                )
                skipped += 1
                continue
            if resp.status_code != 200:
                print(f"  skip {post_id}: HTTP {resp.status_code}")
                skipped += 1
                continue

            note  = resp.json()
            files = note.get("files", [])
            if not files:
                # has_files が TRUE でもファイルが消えている場合がある
                cur.execute(
                    "UPDATE misskey_posts SET has_files = FALSE WHERE log_id = %s",
                    (log_id,)
                )
                skipped += 1
                continue

            media = [
                {
                    "url":   f["url"],
                    "type":  f.get("type", ""),
                    "thumb": f.get("thumbnailUrl") or f["url"],
                }
                for f in files if f.get("url")
            ]

            meta = metadata or {}
            meta["media"] = media
            cur.execute(
                "UPDATE logs SET metadata = %s WHERE id = %s",
                (json.dumps(meta), log_id)
            )
            updated += 1

            if updated % 50 == 0:
                conn.commit()
                print(f"  {updated} 件更新済み...")

            time.sleep(0.3)

        except Exception as e:
            print(f"  エラー log_id={log_id}: {e}")
            skipped += 1

    conn.commit()
    cur.close(); conn.close()
    print(f"\n完了: 更新 {updated} 件 / スキップ {skipped} 件")


if __name__ == "__main__":
    main()
