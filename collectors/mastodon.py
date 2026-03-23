"""Mastodon収集スクリプト"""

import time
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector


def strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text()


class MastodonCollector(BaseCollector):

    def collect_account(self, account_cfg: dict):
        instance = account_cfg["instance"]
        username = account_cfg["username"]
        token = account_cfg["token"]
        source_id = account_cfg["source_id"]
        headers = {"Authorization": f"Bearer {token}"}

        print(f"[Mastodon] {instance} @{username} (source_id={source_id})")

        # account_idをキャッシュから取得、なければAPIで取得
        cfg = self.get_source_config(source_id)
        account_id = cfg.get("account_id")

        if not account_id:
            resp = requests.get(
                f"{instance}/api/v1/accounts/lookup",
                params={"acct": username},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            if "application/json" not in resp.headers.get("content-type", ""):
                print(f"  ⚠ JSONレスポンスではありません（インスタンス不調の可能性）。スキップ")
                return 0
            account_id = resp.json()["id"]
            self.update_source_config(source_id, {"account_id": account_id})
            self.commit()
            print(f"  account_id取得: {account_id}")

        since_id = self.get_latest_original_id(source_id, note_only=True)
        print(f"  since_id: {since_id}")

        params = {"limit": 40}
        if since_id:
            params["since_id"] = since_id

        resp = requests.get(
            f"{instance}/api/v1/accounts/{account_id}/statuses",
            params=params,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("content-type", ""):
            print(f"  ⚠ JSONレスポンスではありません（インスタンス不調の可能性）。スキップ")
            return 0
        statuses = resp.json()

        if not statuses:
            print("  新着なし")
            return 0

        inserted = 0
        for status in statuses:
            is_boost = status.get("reblog") is not None
            if is_boost:
                original = status["reblog"]
                boost_url = original.get("url") or original["id"]
                content = strip_html(original.get("content", ""))
                log_id = self.insert_log(
                    source_id, "boost_" + status["id"],
                    content, boost_url,
                    status["created_at"],
                    {"type": "boost", "original_url": boost_url}
                )
            else:
                content = strip_html(status.get("content", ""))
                url = status.get("url") or status["id"]
                visibility = status.get("visibility", "public")
                spoiler_text = status.get("spoiler_text") or None

                # メディア添付を metadata に保存
                media = [
                    {
                        "url":   a["url"],
                        "type":  a.get("type", ""),
                        "thumb": a.get("preview_url") or a["url"],
                    }
                    for a in status.get("media_attachments", [])
                    if a.get("url")
                ]

                meta = {"type": "note", "visibility": visibility}
                if spoiler_text:
                    meta["cw"] = spoiler_text
                if media:
                    meta["media"] = media

                log_id = self.insert_log(
                    source_id, status["id"], content, url,
                    status["created_at"],
                    meta,
                )
                if log_id:
                    self.cur.execute(
                        """INSERT INTO mastodon_posts
                           (log_id, source_id, post_id, content, spoiler_text, url,
                            reply_count, reblog_count, favourite_count, visibility, posted_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (source_id, post_id) DO NOTHING""",
                        (log_id, source_id, status["id"], content, spoiler_text, url,
                         status.get("replies_count", 0), status.get("reblogs_count", 0),
                         status.get("favourites_count", 0), visibility, status["created_at"])
                    )

            if log_id:
                inserted += 1

        self.commit()
        print(f"  {inserted}件挿入")
        if len(statuses) == 40:
            print("  ⚠ 40件取得（上限）。次回実行で追加分が取得されます")
        return inserted

    def collect(self):
        accounts = self.config.get("mastodon_accounts", [])
        total = 0
        for account in accounts:
            try:
                total += self.collect_account(account)
                time.sleep(1)
            except Exception as e:
                print(f"  エラー: {e}")
        print(f"\n[Mastodon] 合計 {total}件挿入")


if __name__ == "__main__":
    c = MastodonCollector()
    try:
        c.collect()
    finally:
        c.close()
