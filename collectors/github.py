"""GitHub収集スクリプト"""

import requests
from collectors.base import BaseCollector

API_URL = "https://api.github.com"
USED_TYPES = {"PushEvent", "CreateEvent", "ReleaseEvent"}


class GithubCollector(BaseCollector):

    def collect(self):
        cfg = self.config["github"]
        source_id = cfg["source_id"]
        username = cfg["username"]
        headers = {
            "Authorization": f"Bearer {cfg['token']}",
            "Accept": "application/vnd.github+json",
        }

        print(f"[GitHub] @{username} (source_id={source_id})")

        latest_id = self.get_latest_original_id(source_id)

        inserted = 0
        for page in range(1, 4):  # 最大300件（3ページ）
            resp = requests.get(
                f"{API_URL}/users/{username}/events",
                params={"per_page": 100, "page": page},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            events = resp.json()
            if not events:
                break

            for event in events:
                event_id = event["id"]
                if event_id == latest_id:
                    break  # 前回取得済みに到達
                if event["type"] not in USED_TYPES:
                    continue

                repo_name = event["repo"]["name"]
                url = f"https://github.com/{repo_name}"
                occurred_at = event["created_at"]
                payload = event.get("payload", {})

                if event["type"] == "PushEvent":
                    commit_count = payload.get("size", 0)
                    msgs = [c["message"].split("\n")[0] for c in payload.get("commits", [])]
                    summary = f"Push {commit_count}件: " + " / ".join(msgs[:3])
                    content = f"{repo_name}: {summary}"
                elif event["type"] == "CreateEvent":
                    ref_type = payload.get("ref_type", "")
                    ref = payload.get("ref", "")
                    summary = f"{ref_type} {ref} を作成"
                    content = f"{repo_name}: {summary}"
                    commit_count = 0
                elif event["type"] == "ReleaseEvent":
                    tag = payload.get("release", {}).get("tag_name", "")
                    summary = f"リリース {tag}"
                    content = f"{repo_name}: {summary}"
                    commit_count = 0

                log_id = self.insert_log(
                    source_id, event_id, content, url, occurred_at,
                    {"type": "github", "event_type": event["type"], "repo": repo_name}
                )
                if log_id:
                    self.cur.execute(
                        """INSERT INTO github_activity
                           (log_id, event_id, event_type, repo_name, url, commit_count, summary, occurred_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (event_id) DO NOTHING""",
                        (log_id, event_id, event["type"], repo_name, url,
                         commit_count, summary, occurred_at)
                    )
                    inserted += 1
            else:
                continue
            break  # 前回済みに到達したのでループ終了

        self.commit()
        print(f"[GitHub] {inserted}件挿入")


if __name__ == "__main__":
    c = GithubCollector()
    try:
        c.collect()
    finally:
        c.close()
