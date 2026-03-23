"""RSS収集スクリプト"""

import feedparser
from dateutil import parser as dateutil_parser
import datetime
from collectors.base import BaseCollector


class RssCollector(BaseCollector):

    def collect(self):
        cfg = self.config["rss"]
        source_id = cfg["source_id"]
        url = cfg["url"]

        print(f"[RSS] {url} (source_id={source_id})")

        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"  フィードの取得に失敗: {feed.bozo_exception}")
            return

        inserted = 0
        for entry in feed.entries:
            entry_id = entry.get("id") or entry.get("link")
            if not entry_id:
                continue

            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            content = title

            published = None
            if entry.get("published"):
                try:
                    published = dateutil_parser.parse(entry.published)
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    pass
            if not published:
                published = datetime.datetime.now(tz=datetime.timezone.utc)

            log_id = self.insert_log(
                source_id, entry_id, content, link, published,
                {"type": "rss", "title": title}
            )
            if log_id:
                self.cur.execute(
                    """INSERT INTO rss_entries (log_id, entry_id, title, url, summary, published_at)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (entry_id) DO NOTHING""",
                    (log_id, entry_id, title, link, summary, published)
                )
                inserted += 1

        self.commit()
        print(f"[RSS] {inserted}件挿入")


if __name__ == "__main__":
    c = RssCollector()
    try:
        c.collect()
    finally:
        c.close()
