"""Planet MCP 用 DB クエリ（dashboard / summarizer と同等のロジック）。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from summarizer.context import (
    TOPIC_SOURCE_TYPES,
    fetch_activity_digest_for_day,
    fetch_topic_digest_for_day,
    get_source_name_map,
)
from summarizer.db import get_conn, load_config

JST = timezone(timedelta(hours=9))
JST_SQL = "AT TIME ZONE 'Asia/Tokyo'"
CONTENT_PREVIEW = 500
SEARCH_MAX = 200


def get_mcp_conn():
    """MCP 接続。`[database_mcp]` があればそちら、なければ `[database]`。"""
    cfg = load_config()
    db = cfg.get("database_mcp") or cfg["database"]
    import psycopg2

    return psycopg2.connect(
        host=db["host"],
        port=db["port"],
        dbname=db["name"],
        user=db["user"],
        password=db["password"],
    )


def _preview(text: str | None, limit: int = CONTENT_PREVIEW) -> str:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(raw) > limit:
        return raw[:limit] + "…"
    return raw


def _ts_jst_str(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def list_sources() -> list[dict[str, Any]]:
    conn = get_mcp_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, type, base_url, account, is_active, sort_order, short_name
                  FROM data_sources
                 ORDER BY sort_order, id
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "type": r[2],
                "base_url": r[3],
                "account": r[4],
                "is_active": r[5],
                "sort_order": r[6],
                "short_name": r[7],
            }
            for r in rows
        ]
    finally:
        conn.close()


def search_posts(
    query: str,
    *,
    source_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = SEARCH_MAX,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "query is required", "entries": [], "count": 0}
    limit = max(1, min(int(limit), SEARCH_MAX))

    conditions = ["l.is_deleted = FALSE", "l.content LIKE %s"]
    params: list[Any] = [f"%{q}%"]
    if source_id is not None:
        conditions.append("l.source_id = %s")
        params.append(int(source_id))
    if date_from:
        conditions.append("l.timestamp >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("l.timestamp < (%s::date + interval '1 day')")
        params.append(date_to)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT l.id, l.content, l.url,
               (l.timestamp {JST_SQL}) AS ts,
               ds.name, ds.type
          FROM logs l
          JOIN data_sources ds ON l.source_id = ds.id
         WHERE {where}
         ORDER BY l.timestamp DESC
         LIMIT %s
    """
    params.append(limit)

    conn = get_mcp_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        entries = [
            {
                "id": r[0],
                "content": _preview(r[1]),
                "url": r[2],
                "timestamp": _ts_jst_str(r[3]),
                "source_name": r[4],
                "source_type": r[5],
            }
            for r in rows
        ]
        return {"query": q, "entries": entries, "count": len(entries), "limit": limit}
    finally:
        conn.close()


def get_timeline(period: str, date_arg: str) -> dict[str, Any]:
    period = (period or "day").strip().lower()
    date_arg = (date_arg or "").strip()
    if not date_arg:
        return {"error": "date is required", "entries": [], "count": 0}

    select_cols = f"""
        SELECT l.id, l.source_id, l.content, l.url,
               (l.timestamp {JST_SQL}) AS ts,
               l.metadata
          FROM logs l
    """

    conn = get_mcp_conn()
    try:
        with conn.cursor() as cur:
            if period == "day":
                cur.execute(
                    select_cols
                    + """
                     WHERE l.is_deleted = FALSE
                       AND DATE(l.timestamp """
                    + JST_SQL
                    + """) = %s
                     ORDER BY l.timestamp DESC
                    """,
                    (date_arg,),
                )
            elif period == "week":
                year_part, week_part = date_arg.upper().split("-W")
                cur.execute(
                    select_cols
                    + """
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(isoyear FROM l.timestamp """
                    + JST_SQL
                    + """) = %s
                       AND EXTRACT(week FROM l.timestamp """
                    + JST_SQL
                    + """) = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 1000
                    """,
                    (int(year_part), int(week_part)),
                )
            elif period == "month":
                cur.execute(
                    select_cols
                    + """
                     WHERE l.is_deleted = FALSE
                       AND TO_CHAR(l.timestamp """
                    + JST_SQL
                    + """, 'YYYY-MM') = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 2000
                    """,
                    (date_arg,),
                )
            else:
                return {"error": "period must be day|week|month", "entries": [], "count": 0}

            rows = cur.fetchall()
        entries = []
        for r in rows:
            meta = r[5] or {}
            ts = r[4]
            entries.append(
                {
                    "id": r[0],
                    "source_id": r[1],
                    "content": _preview(r[2]),
                    "url": r[3],
                    "time": ts.strftime("%H:%M"),
                    "date": ts.strftime("%Y-%m-%d"),
                    "cw": meta.get("cw"),
                }
            )
        return {"period": period, "date": date_arg, "entries": entries, "count": len(entries)}
    finally:
        conn.close()


def get_stats(period: str, date_arg: str) -> dict[str, Any]:
    period = (period or "day").strip().lower()
    date_arg = (date_arg or "").strip()
    if not date_arg:
        return {"error": "date is required"}

    conn = get_mcp_conn()
    cur = conn.cursor()
    try:
        if period == "day":
            log_where = f"DATE(l.timestamp {JST_SQL}) = %s"
            log_params: tuple[Any, ...] = (date_arg,)
            hd_where = "date = %s"
            hd_params: tuple[Any, ...] = (date_arg,)
        elif period == "week":
            yr, wk = date_arg.upper().split("-W")
            log_where = (
                f"EXTRACT(isoyear FROM l.timestamp {JST_SQL}) = %s "
                f"AND EXTRACT(week FROM l.timestamp {JST_SQL}) = %s"
            )
            log_params = (int(yr), int(wk))
            hd_where = "EXTRACT(isoyear FROM date) = %s AND EXTRACT(week FROM date) = %s"
            hd_params = (int(yr), int(wk))
        elif period == "month":
            log_where = f"TO_CHAR(l.timestamp {JST_SQL}, 'YYYY-MM') = %s"
            log_params = (date_arg,)
            hd_where = "TO_CHAR(date, 'YYYY-MM') = %s"
            hd_params = (date_arg,)
        elif period == "year":
            log_where = f"EXTRACT(year FROM l.timestamp {JST_SQL}) = %s"
            log_params = (int(date_arg),)
            hd_where = "EXTRACT(year FROM date) = %s"
            hd_params = (int(date_arg),)
        else:
            return {"error": "period must be day|week|month|year"}

        cur.execute(
            f"""
            SELECT ds.type, COUNT(*)
              FROM logs l
              JOIN data_sources ds ON l.source_id = ds.id
             WHERE l.is_deleted = FALSE AND {log_where}
             GROUP BY ds.type
            """,
            log_params,
        )
        by_type = dict(cur.fetchall())
        misskey_cnt = by_type.get("misskey", 0)
        mastodon_cnt = by_type.get("mastodon", 0)
        play_cnt = by_type.get("lastfm", 0)
        post_cnt = (
            misskey_cnt
            + mastodon_cnt
            + by_type.get("rss", 0)
            + by_type.get("youtube", 0)
        )

        if period == "day":
            cur.execute(
                "SELECT steps, active_calories, heart_rate_avg FROM health_daily WHERE "
                + hd_where,
                hd_params,
            )
            health = cur.fetchone()
            steps = health[0] if health else None
        else:
            cur.execute(
                "SELECT SUM(steps) FROM health_daily WHERE " + hd_where,
                hd_params,
            )
            row = cur.fetchone()
            steps = int(row[0]) if row and row[0] else None

        if period == "day":
            cur.execute(
                "SELECT temp_max, weather_desc, location, weather_main "
                "FROM weather_daily WHERE "
                + hd_where,
                hd_params,
            )
            w = cur.fetchone()
            weather_obj = (
                {
                    "desc": w[1] if w else None,
                    "temp": float(w[0]) if w and w[0] else None,
                    "location": w[2] if w else None,
                    "main": w[3] if w else None,
                }
                if w
                else None
            )
        else:
            cur.execute(
                """
                SELECT ROUND(AVG(temp_avg)::numeric, 1),
                       MIN(temp_min),
                       MAX(temp_max),
                       MAX(location)
                  FROM weather_daily WHERE """
                + hd_where,
                hd_params,
            )
            w = cur.fetchone()
            if w and w[0] is not None:
                weather_obj = {
                    "avg_temp": float(w[0]),
                    "min_temp": float(w[1]) if w[1] else None,
                    "max_temp": float(w[2]) if w[2] else None,
                    "location": w[3],
                }
            else:
                weather_obj = None

        return {
            "period": period,
            "date": date_arg,
            "posts": post_cnt,
            "posts_breakdown": f"Misskey {misskey_cnt} / Mastodon {mastodon_cnt}",
            "plays": play_cnt,
            "steps": steps,
            "weather": weather_obj,
            "by_type": by_type,
        }
    finally:
        cur.close()
        conn.close()


def get_activity_digest(date_str: str, topic: str | None = None) -> dict[str, Any]:
    try:
        day = date.fromisoformat(date_str.strip())
    except ValueError:
        return {"error": "date must be YYYY-MM-DD", "digest": ""}

    conn = get_mcp_conn()
    try:
        if topic:
            topic = topic.strip().lower()
            if topic not in TOPIC_SOURCE_TYPES:
                return {
                    "error": f"topic must be one of: {', '.join(sorted(TOPIC_SOURCE_TYPES))}",
                    "digest": "",
                }
            name_map = get_source_name_map(conn)
            digest = fetch_topic_digest_for_day(
                conn,
                day,
                TOPIC_SOURCE_TYPES[topic],
                source_name_map=name_map,
            )
        else:
            digest = fetch_activity_digest_for_day(conn, day)
        return {"date": day.isoformat(), "topic": topic, "digest": digest}
    finally:
        conn.close()


def get_summaries(period: str, date_arg: str) -> dict[str, Any]:
    period = (period or "day").strip().lower()
    date_arg = (date_arg or "").strip()
    if not date_arg:
        return {"error": "date is required", "topics": {}}

    conn = get_mcp_conn()
    cur = conn.cursor()
    try:
        if period == "day":
            try:
                period_start = date.fromisoformat(date_arg)
            except ValueError:
                return {"error": "date must be YYYY-MM-DD for day", "topics": {}}
            period_type = "daily"
        elif period == "week":
            s = date_arg.upper()
            if "-W" not in s:
                return {"error": "date must be YYYY-Www for week", "topics": {}}
            y_str, w_str = s.split("-W", 1)
            try:
                period_start = datetime.strptime(
                    f"{int(y_str)}-{int(w_str):02d}-1", "%G-%V-%u"
                ).date()
            except (ValueError, TypeError):
                return {"error": "invalid week date", "topics": {}}
            period_type = "weekly"
        elif period == "month":
            try:
                y, m = map(int, date_arg.split("-", 1))
                period_start = date(y, m, 1)
            except (ValueError, TypeError):
                return {"error": "date must be YYYY-MM for month", "topics": {}}
            period_type = "monthly"
        else:
            return {"error": "period must be day|week|month", "topics": {}}

        cur.execute(
            """
            SELECT summary_type, content, model, prompt_style, created_at
              FROM summaries
             WHERE period_type = %s
               AND period_start = %s
             ORDER BY summary_type
            """,
            (period_type, period_start),
        )
        topics: dict[str, Any] = {}
        for stype, content, model_name, style, created in cur.fetchall():
            topics[stype] = {
                "content": content,
                "model": model_name,
                "prompt_style": style,
                "created_at": _ts_jst_str(created) if created else None,
            }
        return {"period": period, "date": date_arg, "topics": topics}
    finally:
        cur.close()
        conn.close()


def dumps_result(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
