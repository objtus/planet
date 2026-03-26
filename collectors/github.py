"""GitHub収集スクリプト"""

import requests
from collectors.base import BaseCollector

API_URL = "https://api.github.com"
USED_TYPES = {"PushEvent", "CreateEvent", "ReleaseEvent"}
# git の空ツリー（新規 ref など before がダミーのとき compare の片側に使う）
_GIT_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _before_is_dummy(before: str | None) -> bool:
    if not before:
        return True
    s = before.strip().lower()
    return len(s) < 7 or all(c == "0" for c in s)


def _fetch_push_commits_from_api(
    repo_name: str, payload: dict, headers: dict
) -> tuple[int, list[str]]:
    """Events の Push ペイロードに commits が無いとき、Compare / Commits API で件数と件名を取る。"""
    if "/" not in repo_name:
        return 0, []
    head = (payload.get("head") or "").strip()
    if not head or len(head) < 7:
        return 0, []
    owner, _, repo = repo_name.partition("/")
    if not owner or not repo:
        return 0, []
    before = (payload.get("before") or "").strip()

    def _compare(base: str) -> tuple[int, list[str]] | None:
        url = f"{API_URL}/repos/{owner}/{repo}/compare/{base}...{head}"
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if not r.ok:
                return None
            data = r.json()
            raw = data.get("commits") or []
            cc = int(data.get("total_commits") or len(raw) or 0)
            lines: list[str] = []
            for c in raw:
                msg = (c.get("commit") or {}).get("message") or ""
                first = msg.split("\n", 1)[0].strip()
                if first:
                    lines.append(first)
            return (cc or len(lines), lines)
        except requests.RequestException:
            return None

    if not _before_is_dummy(before):
        out = _compare(before)
        if out and (out[0] > 0 or out[1]):
            return out

    out = _compare(_GIT_EMPTY_TREE_SHA)
    if out and (out[0] > 0 or out[1]):
        return out

    try:
        r = requests.get(
            f"{API_URL}/repos/{owner}/{repo}/commits/{head}",
            headers=headers,
            timeout=30,
        )
        if r.ok:
            data = r.json()
            msg = (data.get("commit") or {}).get("message") or ""
            first = msg.split("\n", 1)[0].strip()
            if first:
                return 1, [first]
    except requests.RequestException:
        pass
    return 0, []


def build_push_summary(
    repo_name: str, payload: dict, headers: dict
) -> tuple[int, str, str]:
    """PushEvent 用の commit_count / summary / logs.content 用本文を組み立てる。"""
    commit_count = int(payload.get("size", 0) or 0)
    msgs = [
        (c.get("message") or "").split("\n", 1)[0].strip()
        for c in (payload.get("commits") or [])
        if (c.get("message") or "").strip()
    ]
    if commit_count == 0 and msgs:
        commit_count = len(msgs)
    if not msgs:
        api_n, api_msgs = _fetch_push_commits_from_api(repo_name, payload, headers)
        if api_msgs:
            msgs = api_msgs
        if api_n:
            commit_count = api_n
        elif msgs and commit_count == 0:
            commit_count = len(msgs)
    if msgs:
        summary = f"Push {commit_count}件: " + " / ".join(msgs[:5])
    elif commit_count > 0:
        summary = f"Push {commit_count}件（メッセージ未取得）"
    else:
        summary = "Push（Events API にコミット情報なし）"
    content = f"{repo_name}: {summary}"
    return commit_count, summary, content


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
                    commit_count, summary, content = build_push_summary(
                        repo_name, payload, headers
                    )
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
