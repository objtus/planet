"""Misskey収集スクリプト

settings.tomlの [[misskey_accounts]] を全て処理する。
"""

import time
import json
import requests
from bs4 import BeautifulSoup
from collectors.base import BaseCollector


def strip_mfm(text: str) -> str:
    """MFM記法を除去してプレーンテキストに"""
    if not text:
        return ""
    import re
    text = re.sub(r'\$\[[\w\.]+ ([^\]]*)\]', r'\1', text)
    return text.strip()


class MisskeyCollector(BaseCollector):

    def collect_account(self, account_cfg: dict):
        instance = account_cfg["instance"]
        username = account_cfg["username"]
        token = account_cfg["token"]
        source_id = account_cfg["source_id"]

        print(f"[Misskey] {instance} @{username} (source_id={source_id})")

        # user_idをキャッシュから取得、なければAPIで取得
        cfg = self.get_source_config(source_id)
        user_id = cfg.get("user_id")

        if not user_id:
            resp = requests.post(
                f"{instance}/api/users/show",
                json={"i": token, "username": username, "host": None},
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            user_id = resp.json()["id"]
            self.update_source_config(source_id, {"user_id": user_id})
            self.commit()
            print(f"  user_id取得: {user_id}")

        # 最新IDで差分取得
        since_id = self.get_latest_original_id(source_id, note_only=True)
        print(f"  sinceId: {since_id}")

        body = {
            "i": token,
            "userId": user_id,
            "limit": 100,
            "withRenotes": True,
            "withReplies": True,
        }
        if since_id:
            body["sinceId"] = since_id

        resp = requests.post(
            f"{instance}/api/users/notes",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        notes = resp.json()

        if not notes:
            print("  新着なし")
            return 0

        inserted = 0
        for note in notes:
            is_renote = note.get("renoteId") and not note.get("text")
            if is_renote:
                # 純粋なリノート
                renote_url = f"{instance}/notes/{note['renoteId']}"
                content = note.get("text") or ""
                log_id = self.insert_log(
                    source_id, "renote_" + note["id"],
                    content, renote_url,
                    note["createdAt"],
                    {"type": "renote", "original_url": renote_url}
                )
            else:
                text = strip_mfm(note.get("text") or "")
                url = f"{instance}/notes/{note['id']}"
                visibility = note.get("visibility", "public")
                cw = note.get("cw")
                has_files = bool(note.get("files"))

                log_id = self.insert_log(
                    source_id, note["id"], text, url,
                    note["createdAt"],
                    {"type": "note", "visibility": visibility}
                )
                if log_id:
                    self.cur.execute(
                        """INSERT INTO misskey_posts
                           (log_id, source_id, post_id, text, cw, url,
                            reply_count, renote_count, reaction_count, has_files, visibility, posted_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (source_id, post_id) DO NOTHING""",
                        (log_id, source_id, note["id"], text, cw, url,
                         note.get("repliesCount", 0), note.get("renoteCount", 0),
                         note.get("reactionCount") or len(note.get("reactions", {})),
                         has_files, visibility, note["createdAt"])
                    )

            if log_id:
                inserted += 1

            time.sleep(0.1)

        self.commit()
        print(f"  {inserted}件挿入")
        if len(notes) == 100:
            print("  ⚠ 100件取得（上限）。次回実行で追加分が取得されます")
        return inserted

    def collect(self):
        accounts = self.config.get("misskey_accounts", [])
        total = 0
        for account in accounts:
            try:
                total += self.collect_account(account)
                time.sleep(1)
            except Exception as e:
                print(f"  エラー: {e}")
        print(f"\n[Misskey] 合計 {total}件挿入")


if __name__ == "__main__":
    c = MisskeyCollector()
    try:
        c.collect()
    finally:
        c.close()
