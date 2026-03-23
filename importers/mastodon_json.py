"""Mastodon JSONエクスポートのインポーター

使用例:
  python importers/mastodon_json.py --instance mastodon.cloud --account @objtus \
      ~/planet-data/imports/@objtus@mastodon.cloud_user_170_1_note.json \
      ~/planet-data/imports/@objtus@mastodon.cloud_user_170_2_note.json \
      ~/planet-data/imports/@objtus@mastodon.cloud_user_170_3_note.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from importers.common import (
    load_config, get_db_conn, strip_html, parse_timestamp,
    classify_item, get_own_account_id, get_or_create_source,
    get_mastodon_visibility, extract_id_from_url,
)


def get_content(item: dict) -> str:
    if item.get("notag", "").strip():
        return item["notag"].strip()
    return strip_html(item.get("content", ""))


def import_mastodon(files: list[Path], instance: str, account: str, archived: bool, include_boosts: bool):
    config = load_config()
    conn = get_db_conn(config)
    cur = conn.cursor()

    base_url = f"https://{instance}"
    display_name = f"{instance} {account} (archived)" if archived else f"{instance} {account}"
    source_id = get_or_create_source(cur, display_name, "mastodon", base_url, account, not archived)
    conn.commit()
    print(f"source_id: {source_id}  ({display_name})")

    stats = {"own_note": 0, "boost": 0, "skip": 0, "dup": 0, "error": 0}

    for filepath in files:
        print(f"\n読み込み中: {filepath.name}")
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        own_account_id = get_own_account_id(data)
        print(f"アカウントID: {own_account_id}  件数: {len(data)}")

        for item in data:
            kind = classify_item(item, own_account_id)

            if kind == "own_note":
                try:
                    post_id = extract_id_from_url(item["id"])
                    content = get_content(item)
                    url = item.get("url") or item["id"]
                    timestamp = parse_timestamp(item["published"])
                    visibility = get_mastodon_visibility(item)
                    spoiler_text = item.get("summary") or None

                    cur.execute(
                        """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (source_id, original_id) DO NOTHING
                           RETURNING id""",
                        (source_id, post_id, content, url, timestamp,
                         json.dumps({"type": "note", "visibility": visibility}))
                    )
                    row = cur.fetchone()
                    if row is None:
                        stats["dup"] += 1
                        continue
                    log_id = row[0]

                    cur.execute(
                        """INSERT INTO mastodon_posts
                           (log_id, source_id, post_id, content, spoiler_text, url, visibility, posted_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (source_id, post_id) DO NOTHING""",
                        (log_id, source_id, post_id, content, spoiler_text, url, visibility, timestamp)
                    )
                    stats["own_note"] += 1

                except Exception as e:
                    stats["error"] += 1
                    print(f"  エラー: {e} / item id: {item.get('id', '?')}")

            elif kind == "boost" and include_boosts:
                try:
                    announce_url = item["announce"]
                    boost_id = "boost_" + extract_id_from_url(announce_url)
                    content = get_content(item)
                    timestamp = parse_timestamp(item["published"])

                    cur.execute(
                        """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (source_id, original_id) DO NOTHING""",
                        (source_id, boost_id, content, announce_url, timestamp,
                         json.dumps({"type": "boost", "original_url": announce_url}))
                    )
                    if cur.rowcount:
                        stats["boost"] += 1
                    else:
                        stats["dup"] += 1

                except Exception as e:
                    stats["error"] += 1
                    print(f"  エラー(boost): {e}")

            else:
                stats["skip"] += 1

            if (stats["own_note"] + stats["boost"]) % 500 == 0 and (stats["own_note"] + stats["boost"]) > 0:
                conn.commit()
                print(f"  コミット済み: 投稿={stats['own_note']} BT={stats['boost']}")

        conn.commit()

    cur.close()
    conn.close()

    print(f"\n=== 完了 ===")
    print(f"  投稿: {stats['own_note']}")
    print(f"  ブースト: {stats['boost']}")
    print(f"  スキップ: {stats['skip']}")
    print(f"  重複: {stats['dup']}")
    print(f"  エラー: {stats['error']}")


def main():
    parser = argparse.ArgumentParser(description="Mastodon JSONインポーター")
    parser.add_argument("files", nargs="+", type=Path, help="JSONファイル（複数可）")
    parser.add_argument("--instance", required=True, help="インスタンスホスト名 例: mastodon.cloud")
    parser.add_argument("--account", required=True, help="アカウント名 例: @objtus")
    parser.add_argument("--archived", action="store_true", help="閉鎖済みインスタンス（is_active=FALSE）")
    args = parser.parse_args()

    config = load_config()
    include_boosts = config.get("importer", {}).get("include_boosts", True)

    import_mastodon(args.files, args.instance, args.account, args.archived, include_boosts)


if __name__ == "__main__":
    main()
