"""Last.fm収集スクリプト"""

import time
import requests
from collectors.base import BaseCollector

API_URL = "https://ws.audioscrobbler.com/2.0/"
HEADERS = {"User-Agent": "planet/1.0 (yuinoid.neocities.org)"}


class LastfmCollector(BaseCollector):

    def collect(self):
        cfg = self.config["lastfm"]
        api_key = cfg["api_key"]
        username = cfg["username"]
        source_id = cfg["source_id"]

        print(f"[Last.fm] {username} (source_id={source_id})")

        from_ts = self.get_latest_timestamp(source_id)
        if from_ts:
            from_ts = int(from_ts) + 1  # 最新の次から取得
        print(f"  from: {from_ts}")

        total_inserted = 0
        page = 1

        while True:
            params = {
                "method": "user.getrecenttracks",
                "user": username,
                "api_key": api_key,
                "format": "json",
                "limit": 200,
                "page": page,
            }
            if from_ts:
                params["from"] = from_ts

            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 500:
                print(f"  page {page}: 500エラー（Last.fm APIの終端）。終了")
                break
            resp.raise_for_status()
            data = resp.json()

            tracks = data.get("recenttracks", {}).get("track", [])
            if not tracks:
                break

            inserted = 0
            for track in tracks:
                # 再生中スキップ
                if track.get("@attr", {}).get("nowplaying"):
                    continue

                date_info = track.get("date")
                if not date_info:
                    continue

                uts = date_info["uts"]
                artist = track["artist"]["#text"]
                name = track["name"]
                album = track.get("album", {}).get("#text") or None
                url = track.get("url")
                track_id = f"{artist}::{name}::{uts}"
                content = f"{artist} - {name}"
                import datetime
                played_at = datetime.datetime.fromtimestamp(
                    int(uts), tz=datetime.timezone.utc
                )

                log_id = self.insert_log(
                    source_id, track_id, content, url, played_at,
                    {"type": "track", "artist": artist, "track": name, "album": album}
                )
                if log_id:
                    self.cur.execute(
                        """INSERT INTO lastfm_plays (log_id, track_id, artist, track, album, url, played_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (track_id) DO NOTHING""",
                        (log_id, track_id, artist, name, album, url, played_at)
                    )
                    inserted += 1

            self.commit()
            total_inserted += inserted
            print(f"  page {page}: {inserted}件挿入")

            attr = data["recenttracks"].get("@attr", {})
            total_pages = int(attr.get("totalPages", 1))
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.3)

        print(f"[Last.fm] 合計 {total_inserted}件挿入")


if __name__ == "__main__":
    c = LastfmCollector()
    try:
        c.collect()
    finally:
        c.close()
