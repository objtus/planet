"""planet-feed 用の DB 読み取り（公開タイムライン・日別集計）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2.extensions

from publisher.display_utils import source_row_to_feed_meta, weather_emoji

JST = ZoneInfo("Asia/Tokyo")

# Fediverse: 公開＋半公開のみ（planet-feed は public リポジトリ経由で配信）
FEDI_FEED_VISIBILITY_CLAUSE = """
  AND (
    ds.type NOT IN ('misskey', 'mastodon')
    OR (ds.type = 'misskey' AND mp.visibility IN ('public', 'home'))
    OR (ds.type = 'mastodon' AND mpost.visibility IN ('public', 'unlisted'))
  )
"""


def jst_window(days: int) -> tuple[date, date, datetime, datetime]:
    """直近 days 日（JST 暦日、今日を含む）の oldest, latest と UTC の [start, end)。"""
    if days < 1:
        raise ValueError("days は 1 以上")
    now_jst = datetime.now(JST)
    latest = now_jst.date()
    oldest = latest - timedelta(days=days - 1)
    start_local = datetime.combine(oldest, datetime.min.time(), tzinfo=JST)
    end_local = datetime.combine(latest + timedelta(days=1), datetime.min.time(), tzinfo=JST)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return oldest, latest, start_utc, end_utc


def fetch_sources(cur: psycopg2.extensions.cursor) -> list[dict]:
    """全 data_sources（非アクティブ含む）。カレンダー画面と同じ並び。"""
    cur.execute(
        """
        SELECT id, name, type, base_url, account, is_active, sort_order, short_name
          FROM data_sources
         ORDER BY sort_order, id
        """
    )
    return [source_row_to_feed_meta(r) for r in cur.fetchall()]


def fetch_timeline(
    cur: psycopg2.extensions.cursor,
    ts_start: datetime,
    ts_end: datetime,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT l.source_id, l.content, l.url,
               (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
               l.metadata,
               ds.type,
               COALESCE(mp.has_files, FALSE) AS msk_has_files,
               COALESCE(mp.visibility, mpost.visibility, l.metadata->>'visibility') AS fedi_visibility
          FROM logs l
          JOIN data_sources ds ON ds.id = l.source_id
          LEFT JOIN misskey_posts mp ON mp.log_id = l.id
          LEFT JOIN mastodon_posts mpost ON mpost.log_id = l.id
         WHERE l.is_deleted = FALSE
           AND l.timestamp >= %s AND l.timestamp < %s
        """
        + FEDI_FEED_VISIBILITY_CLAUSE
        + """
         ORDER BY l.timestamp DESC
        """,
        (ts_start, ts_end),
    )
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r[4] or {}
        ts = r[3]
        stype = r[5]
        msk_has_files = r[6]
        fedi_vis = r[7]
        is_boost = bool(
            meta.get("renote_id")
            or meta.get("reblog_id")
            or meta.get("type") in ("renote", "boost")
        )
        media = meta.get("media") or []
        has_media = bool(media) or bool(msk_has_files)
        entry: dict[str, Any] = {
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M"),
            "src_id": r[0],
            "src_type": stype,
            "text": r[1] or "",
            "is_boost": is_boost,
            "has_media": has_media,
        }
        if r[2]:
            entry["url"] = r[2]
        if stype in ("misskey", "mastodon") and fedi_vis in ("home", "unlisted"):
            entry["visibility"] = fedi_vis
        if media:
            media_out: list[dict[str, str]] = []
            for m in media:
                if not isinstance(m, dict):
                    continue
                u = m.get("url")
                if not u:
                    continue
                thumb = m.get("thumb") or m.get("thumbnailUrl") or u
                media_out.append(
                    {
                        "url": u,
                        "thumb": thumb,
                        "type": str(m.get("type") or ""),
                    }
                )
            if media_out:
                entry["media"] = media_out
        out.append(entry)
    return out


def _counts_by_jst_date(
    cur: psycopg2.extensions.cursor,
    ts_start: datetime,
    ts_end: datetime,
    sql: str,
) -> dict[str, int]:
    cur.execute(sql, (ts_start, ts_end))
    return {str(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}


def fetch_posts_by_jst_date(
    cur: psycopg2.extensions.cursor,
    ts_start: datetime,
    ts_end: datetime,
) -> dict[str, int]:
    """日別投稿数。RSS/YouTube を含む + Fediverse は公開・半公開のみ。"""
    sql = """
        SELECT DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') AS d, COUNT(*)::bigint
          FROM logs l
          JOIN data_sources ds ON ds.id = l.source_id
          LEFT JOIN misskey_posts mp ON mp.log_id = l.id
          LEFT JOIN mastodon_posts mpost ON mpost.log_id = l.id
         WHERE l.is_deleted = FALSE
           AND l.timestamp >= %s AND l.timestamp < %s
           AND ds.type IN ('misskey', 'mastodon', 'rss', 'youtube')
    """ + FEDI_FEED_VISIBILITY_CLAUSE + """
         GROUP BY 1
    """
    return _counts_by_jst_date(cur, ts_start, ts_end, sql)


def fetch_plays_by_jst_date(
    cur: psycopg2.extensions.cursor,
    ts_start: datetime,
    ts_end: datetime,
) -> dict[str, int]:
    sql = """
        SELECT DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') AS d, COUNT(*)::bigint
          FROM logs l
          JOIN data_sources ds ON ds.id = l.source_id
         WHERE l.is_deleted = FALSE
           AND ds.type = 'lastfm'
           AND l.timestamp >= %s AND l.timestamp < %s
         GROUP BY 1
    """
    return _counts_by_jst_date(cur, ts_start, ts_end, sql)


def fetch_steps_by_date(
    cur: psycopg2.extensions.cursor,
    oldest: date,
    latest: date,
) -> dict[str, int]:
    cur.execute(
        """
        SELECT date, steps FROM health_daily
         WHERE date >= %s AND date <= %s AND steps IS NOT NULL
        """,
        (oldest, latest),
    )
    return {str(r[0]): int(r[1]) for r in cur.fetchall()}


def fetch_weather_by_date(
    cur: psycopg2.extensions.cursor,
    oldest: date,
    latest: date,
) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT date, temp_max, weather_main, weather_desc
          FROM weather_daily
         WHERE date >= %s AND date <= %s
        """,
        (oldest, latest),
    )
    out: dict[str, dict[str, Any]] = {}
    for r in cur.fetchall():
        dkey = str(r[0])
        temp_max = r[1]
        main = r[2]
        desc = r[3] or ""
        w: dict[str, Any] = {
            "icon": weather_emoji(main, desc),
            "desc": desc or "—",
        }
        if temp_max is not None:
            v = float(temp_max)
            w["temp_max"] = int(v) if v == int(v) else round(v, 1)
        out[dkey] = w
    return out


def build_days_payload(
    oldest: date,
    latest: date,
    posts: dict[str, int],
    plays: dict[str, int],
    steps: dict[str, int],
    weather: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    days: dict[str, dict[str, Any]] = {}
    d = oldest
    while d <= latest:
        key = d.isoformat()
        block: dict[str, Any] = {
            "posts": int(posts.get(key, 0)),
            "plays": int(plays.get(key, 0)),
        }
        if key in steps:
            block["steps"] = steps[key]
        if key in weather:
            block["weather"] = weather[key]
        days[key] = block
        d += timedelta(days=1)
    return days
