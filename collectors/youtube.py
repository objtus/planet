"""YouTube収集スクリプト（APIキー取得後に使用可能）"""

import re
import requests
from collectors.base import BaseCollector

API_URL = "https://www.googleapis.com/youtube/v3"


def parse_duration(duration: str) -> int:
    """PT3M33S → 213秒"""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not match:
        return 0
    h, m, s = (int(x or 0) for x in match.groups())
    return h * 3600 + m * 60 + s


class YoutubeCollector(BaseCollector):

    def collect(self):
        cfg = self.config.get("youtube", {})
        api_key = cfg.get("api_key", "")
        channel_id = cfg.get("channel_id", "")
        source_id = cfg.get("source_id")

        if not api_key or api_key.startswith("YOUR_"):
            print("[YouTube] APIキー未設定。スキップ")
            return

        print(f"[YouTube] channel={channel_id} (source_id={source_id})")

        latest_id = self.get_latest_original_id(source_id)
        video_ids = []
        page_token = None

        while True:
            params = {
                "key": api_key,
                "channelId": channel_id,
                "type": "video",
                "order": "date",
                "maxResults": 50,
                "part": "id",
            }
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(f"{API_URL}/search", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                vid = item["id"]["videoId"]
                if vid == latest_id:
                    page_token = None
                    break
                video_ids.append(vid)
            else:
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                continue
            break

        if not video_ids:
            print("  新着なし")
            return

        # 詳細を取得（50件ずつ）
        inserted = 0
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            resp = requests.get(
                f"{API_URL}/videos",
                params={
                    "key": api_key,
                    "id": ",".join(chunk),
                    "part": "snippet,statistics,contentDetails",
                },
                timeout=30,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                vid = item["id"]
                snippet = item["snippet"]
                stats = item.get("statistics", {})
                details = item.get("contentDetails", {})

                title = snippet["title"]
                url = f"https://www.youtube.com/watch?v={vid}"
                published_at = snippet["publishedAt"]
                duration_sec = parse_duration(details.get("duration", "PT0S"))

                log_id = self.insert_log(
                    source_id, vid, title, url, published_at,
                    {"type": "youtube", "title": title}
                )
                if log_id:
                    self.cur.execute(
                        """INSERT INTO youtube_videos
                           (log_id, video_id, title, description, url, duration_sec,
                            view_count, like_count, comment_count, published_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (video_id) DO NOTHING""",
                        (log_id, vid, title, snippet.get("description", ""), url, duration_sec,
                         int(stats.get("viewCount", 0)), int(stats.get("likeCount", 0)),
                         int(stats.get("commentCount", 0)), published_at)
                    )
                    inserted += 1

        self.commit()
        print(f"[YouTube] {inserted}件挿入")


if __name__ == "__main__":
    c = YoutubeCollector()
    try:
        c.collect()
    finally:
        c.close()
