"""
github_activity / logs の Push 行を、Compare API 補完ロジックで再計算して更新する。

前提:
  - GitHub の GET /users/{username}/events は直近のイベントに限られる（公式は最大 300 件程度）。
    それより古い event_id は API に無く、バックフィルできない。

実行例:
  python db/backfill_github_push.py
  python db/backfill_github_push.py --dry-run
  python db/backfill_github_push.py --all-in-window   # 取得窓内の Push をすべて再計算
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import psycopg2
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.github import API_URL, build_push_summary  # noqa: E402

with open(ROOT / "config" / "settings.toml", "rb") as f:
    config = tomllib.load(f)


def fetch_events_index(username: str, headers: dict, max_pages: int) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        r = requests.get(
            f"{API_URL}/users/{username}/events",
            params={"per_page": 100, "page": page},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for ev in batch:
            by_id[ev["id"]] = ev
        if len(batch) < 100:
            break
    return by_id


def main() -> None:
    ap = argparse.ArgumentParser(description="GitHub Push 行の summary / commit_count をバックフィル")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="更新せず差分だけ表示",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=15,
        metavar="N",
        help="events の取得ページ上限（1ページ100件）",
    )
    ap.add_argument(
        "--all-in-window",
        action="store_true",
        help="薄い行だけでなく、取得できたイベントに一致する Push 行はすべて再計算",
    )
    args = ap.parse_args()

    gh = config["github"]
    username = gh["username"]
    headers = {
        "Authorization": f"Bearer {gh['token']}",
        "Accept": "application/vnd.github+json",
    }

    db = config["database"]
    conn = psycopg2.connect(
        host=db["host"],
        port=db["port"],
        dbname=db["name"],
        user=db["user"],
        password=db["password"],
    )
    cur = conn.cursor()

    print(f"[backfill] @{username} の events を取得中（max_pages={args.max_pages}）…")
    events_by_id = fetch_events_index(username, headers, args.max_pages)
    print(f"[backfill] ユニーク event_id: {len(events_by_id)} 件")

    if args.all_in_window:
        cur.execute(
            """
            SELECT ga.event_id, ga.log_id, ga.repo_name, ga.commit_count, ga.summary
            FROM github_activity ga
            WHERE ga.event_type = 'PushEvent'
            """
        )
    else:
        cur.execute(
            """
            SELECT ga.event_id, ga.log_id, ga.repo_name, ga.commit_count, ga.summary
            FROM github_activity ga
            WHERE ga.event_type = 'PushEvent'
              AND (
                ga.commit_count = 0
                OR ga.summary LIKE %s
                OR ga.summary LIKE %s
                OR ga.summary LIKE %s
              )
            """,
            (
                "Push 0件%",
                "%Events API にコミット情報なし%",
                "%メッセージ未取得%",
            ),
        )

    rows = cur.fetchall()
    print(f"[backfill] 対象 DB 行: {len(rows)} 件")

    updated = 0
    skipped_no_event = 0
    skipped_unchanged = 0

    for event_id, log_id, repo_name, old_cc, old_summary in rows:
        ev = events_by_id.get(str(event_id))
        if not ev or ev.get("type") != "PushEvent":
            skipped_no_event += 1
            continue
        api_repo = (ev.get("repo") or {}).get("name") or repo_name
        payload = ev.get("payload") or {}
        new_cc, new_summary, new_content = build_push_summary(
            api_repo, payload, headers
        )
        if new_summary == old_summary and new_cc == old_cc:
            skipped_unchanged += 1
            continue
        if args.dry_run:
            print(f"  [dry-run] {event_id}: {old_summary!r} -> {new_summary!r}")
            updated += 1
            continue
        cur.execute(
            """
            UPDATE github_activity
            SET commit_count = %s, summary = %s
            WHERE event_id = %s
            """,
            (new_cc, new_summary, str(event_id)),
        )
        cur.execute(
            "UPDATE logs SET content = %s WHERE id = %s",
            (new_content, log_id),
        )
        updated += 1

    if not args.dry_run:
        conn.commit()
    cur.close()
    conn.close()

    print(
        f"[backfill] 更新: {updated} 件, "
        f"スキップ（API にイベントなし）: {skipped_no_event} 件, "
        f"スキップ（変更なし）: {skipped_unchanged} 件"
    )
    if args.dry_run:
        print("[backfill] --dry-run のためコミットしていません")


if __name__ == "__main__":
    main()
