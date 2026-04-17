"""Planet ダッシュボード Flask アプリ (Phase 5)"""

import csv
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from calendar import monthrange
import tomllib
import psycopg2
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from werkzeug.exceptions import RequestEntityTooLarge

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ingest.api import ingest_bp  # noqa: E402
from importers.streaming_csv import detect_format, import_streaming_csv  # noqa: E402

CONFIG_PATH = ROOT / "config" / "settings.toml"
JST = timezone(timedelta(hours=9))

# ソース表示名のドメイン→短縮名マッピング
SHORT_NAME_MAP = {
    "misskey.io":            "msk.io",
    "tanoshii.site":         "tanoshii",
    "sushi.ski":             "sushi.ski",
    "mistodon.cloud":        "mistodon",
    "mastodon.cloud":        "masto.cloud",
    "msk.ilnk.info":         "ilnk",
    "pon.icu":               "pon.icu",
    "groundpolis.app":       "g.app",
    "yuinoid.neocities.org": "100%health",
}

# ソース種別ごとの CSS クラス・絵文字・既知 favicon URL
TYPE_INFO = {
    "misskey":  {"cls": "msk",  "emoji": "🍣", "favicon": None},  # base_url から生成
    "mastodon": {"cls": "mst",  "emoji": "🐘", "favicon": None},  # base_url から生成
    "lastfm":   {"cls": "lfm",  "emoji": "🎵", "favicon": "https://www.last.fm/favicon.ico"},
    "health":      {"cls": "hlth", "emoji": "🍎", "favicon": None},
    "photo":       {"cls": "hlth", "emoji": "📷", "favicon": None},
    "screen_time": {"cls": "hlth", "emoji": "📱", "favicon": None},
    "rss":      {"cls": "rss",  "emoji": "🌐", "favicon": None},  # base_url から生成
    "weather":  {"cls": "rss",  "emoji": "☁️", "favicon": None},
    "github":   {"cls": "rss",  "emoji": "🐱", "favicon": "https://github.com/favicon.ico"},
    "youtube":  {"cls": "rss",  "emoji": "▶️", "favicon": "https://www.youtube.com/favicon.ico"},
    "scrapbox": {"cls": "rss",  "emoji": "📓", "favicon": "https://scrapbox.io/favicon.ico"},
    "netflix":  {"cls": "rss",  "emoji": "🎬", "favicon": "https://www.netflix.com/favicon.ico"},
    "prime":    {"cls": "rss",  "emoji": "📺", "favicon": None},
}


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_db_conn():
    db = load_config()["database"]
    return psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )


def _auto_short_name(stype, base_url, name):
    """種別・URL から短縮名を自動生成する"""
    domain = (base_url or "").replace("https://", "").replace("http://", "").rstrip("/")
    fixed  = {"lastfm": "last.fm", "health": "health", "photo": "photo",
              "screen_time": "jomo", "weather": "weather", "github": "github",
              "youtube": "youtube", "scrapbox": "scrapbox",
              "netflix": "netflix", "prime": "prime"}
    return fixed.get(stype) or SHORT_NAME_MAP.get(domain) or domain or name


def make_source_info(row):
    """data_sources の行から表示用の dict を返す。
    row は (id, name, type, base_url, account, is_active[, sort_order, short_name]) の形式。
    short_name が DB に保存されていればそれを優先し、なければ自動生成。
    """
    sid       = row[0]
    name      = row[1]
    stype     = row[2]
    base_url  = row[3]
    account   = row[4]
    is_active = row[5] if len(row) > 5 else True
    db_short  = row[7] if len(row) > 7 else None  # row[6]=sort_order, row[7]=short_name

    domain = (base_url or "").replace("https://", "").replace("http://", "").rstrip("/")
    info   = TYPE_INFO.get(stype, {"cls": "rss", "emoji": "🌐", "favicon": None})

    short_name = db_short or _auto_short_name(stype, base_url, name)

    # 廃止サーバー（is_active=False）はドメインが死んでいる可能性が高いので None
    if not is_active:
        favicon = None
    elif base_url:
        favicon = f"{base_url}/favicon.ico"
    else:
        favicon = info.get("favicon")

    return {
        "id":          sid,
        "name":        name,
        "type":        stype,
        "short_name":  short_name,
        "cls":         info["cls"],
        "emoji":       info["emoji"],
        "favicon_url": favicon,
        "is_active":   is_active,
    }


def create_app():
    app = Flask(__name__)
    config = load_config()
    app.secret_key = config["flask"]["secret_key"]
    # Netflix / Prime 詳細 CSV 等（既定 40MB）
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("PLANET_MAX_UPLOAD_MB", "40")
    ) * 1024 * 1024

    app.register_blueprint(ingest_bp)

    @app.errorhandler(RequestEntityTooLarge)
    def _upload_too_large(_e):
        return jsonify({"error": "ファイルが大きすぎます（上限は PLANET_MAX_UPLOAD_MB または 40MB）"}), 413

    # ------------------------------------------------------------------ #
    # カレンダー（メイン画面）
    # ------------------------------------------------------------------ #
    @app.route("/")
    def calendar():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            # 全ソース（廃止含む）— タイムライン中の過去エントリのバッジ表示に必要
            cur.execute("""
                SELECT id, name, type, base_url, account, is_active, sort_order, short_name
                  FROM data_sources
                 ORDER BY sort_order, id
            """)
            sources = [make_source_info(r) for r in cur.fetchall()]

            today = datetime.now(JST).date()
            return render_template("calendar.html", sources=sources, today=str(today))
        finally:
            cur.close(); conn.close()

    # ------------------------------------------------------------------ #
    # API: カレンダー・ヒートマップ（月内スケール・指標別）
    # ------------------------------------------------------------------ #
    @app.route("/api/heatmap")
    def api_heatmap():
        try:
            y = int(request.args.get("year", 0))
            m = int(request.args.get("month", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid year/month"}), 400
        metric = (request.args.get("metric") or "posts").lower()
        if m < 1 or m > 12 or y < 1990 or y > 2100:
            return jsonify({"error": "invalid year/month"}), 400
        if metric not in ("posts", "plays", "steps", "weather"):
            return jsonify({"error": "invalid metric"}), 400

        month_start = date(y, m, 1)
        last_d      = monthrange(y, m)[1]
        month_end   = date(y, m, last_d)
        jst         = "AT TIME ZONE 'Asia/Tokyo'"

        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            if metric == "posts":
                cur.execute(
                    f"""
                    SELECT DATE(l.timestamp {jst}) AS d, COUNT(*)::bigint
                      FROM logs l
                      JOIN data_sources ds ON ds.id = l.source_id
                     WHERE l.is_deleted = FALSE
                       AND ds.type IN ('misskey', 'mastodon', 'rss', 'youtube')
                       AND DATE(l.timestamp {jst}) >= %s
                       AND DATE(l.timestamp {jst}) <= %s
                     GROUP BY 1
                    """,
                    (month_start, month_end),
                )
                raw = {str(r[0]): int(r[1]) for r in cur.fetchall()}
                by_date = {}
                for dom in range(1, last_d + 1):
                    ds = str(date(y, m, dom))
                    by_date[ds] = float(raw.get(ds, 0))

            elif metric == "plays":
                cur.execute(
                    f"""
                    SELECT DATE(l.timestamp {jst}) AS d, COUNT(*)::bigint
                      FROM logs l
                      JOIN data_sources ds ON ds.id = l.source_id
                     WHERE l.is_deleted = FALSE
                       AND ds.type = 'lastfm'
                       AND DATE(l.timestamp {jst}) >= %s
                       AND DATE(l.timestamp {jst}) <= %s
                     GROUP BY 1
                    """,
                    (month_start, month_end),
                )
                raw = {str(r[0]): int(r[1]) for r in cur.fetchall()}
                by_date = {}
                for dom in range(1, last_d + 1):
                    ds = str(date(y, m, dom))
                    by_date[ds] = float(raw.get(ds, 0))

            elif metric == "steps":
                cur.execute(
                    """
                    SELECT date, steps
                      FROM health_daily
                     WHERE date >= %s AND date <= %s
                    """,
                    (month_start, month_end),
                )
                by_date = {}
                for r in cur.fetchall():
                    if r[1] is not None:
                        by_date[str(r[0])] = float(int(r[1]))

            else:  # weather
                cur.execute(
                    """
                    SELECT date, temp_max
                      FROM weather_daily
                     WHERE date >= %s AND date <= %s
                       AND temp_max IS NOT NULL
                    """,
                    (month_start, month_end),
                )
                by_date = {}
                for r in cur.fetchall():
                    by_date[str(r[0])] = float(r[1])

            vals = list(by_date.values())
            if not vals:
                hmin, hmax = None, None
            else:
                hmin = min(vals)
                hmax = max(vals)

            return jsonify(
                {
                    "metric":   metric,
                    "year":     y,
                    "month":    m,
                    "by_date":  by_date,
                    "min":      hmin,
                    "max":      hmax,
                }
            )
        finally:
            cur.close(); conn.close()

    # ------------------------------------------------------------------ #
    # API: タイムライン（JSON）
    # ------------------------------------------------------------------ #
    @app.route("/api/timeline")
    def api_timeline():
        period   = request.args.get("period", "day")
        date_arg = request.args.get("date", str(datetime.now(JST).date()))

        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            # misskey_posts を LEFT JOIN して has_files（歴史データ分）も取得
            SELECT_COLS = """
                SELECT l.id, l.source_id, l.content, l.url,
                       (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                       l.metadata,
                       COALESCE(mp.has_files, FALSE) AS msk_has_files
                  FROM logs l
                  LEFT JOIN misskey_posts mp ON mp.log_id = l.id
            """

            if period == "day":
                cur.execute(SELECT_COLS + """
                     WHERE l.is_deleted = FALSE
                       AND DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp DESC
                """, (date_arg,))

            elif period == "week":
                year_part, week_part = date_arg.split("-W")
                cur.execute(SELECT_COLS + """
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(isoyear FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                       AND EXTRACT(week    FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 1000
                """, (int(year_part), int(week_part)))

            elif period == "month":
                cur.execute(SELECT_COLS + """
                     WHERE l.is_deleted = FALSE
                       AND TO_CHAR(l.timestamp AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 2000
                """, (date_arg,))

            elif period == "year":
                cur.execute(SELECT_COLS + """
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(year FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 5000
                """, (int(date_arg),))

            else:
                return jsonify({"error": "invalid period"}), 400

            rows    = cur.fetchall()
            entries = []
            for r in rows:
                meta       = r[5] or {}
                ts         = r[4]
                is_boost   = bool(meta.get("renote_id") or meta.get("reblog_id")
                                  or meta.get("type") in ("renote", "boost"))
                media      = meta.get("media") or []
                # 旧データ（media 未保存）は has_files フラグだけ持っている
                has_media  = bool(media) or bool(r[6])
                entries.append({
                    "id":        r[0],
                    "source_id": r[1],
                    "content":   r[2] or "",
                    "url":       r[3],
                    "time":      ts.strftime("%H:%M"),
                    "date":      ts.strftime("%Y-%m-%d"),
                    "cw":        meta.get("cw"),
                    "is_boost":  is_boost,
                    "media":     media,
                    "has_media": has_media,
                })
            return jsonify({"entries": entries, "count": len(entries)})
        finally:
            cur.close(); conn.close()

    @app.route("/api/logs/<int:log_id>/soft-delete", methods=["POST"])
    def api_log_soft_delete(log_id):
        """Last.fm の1件のみソフト削除（is_deleted）。データソース自体は変更しない。"""
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT l.is_deleted, ds.type
                  FROM logs l
                  JOIN data_sources ds ON ds.id = l.source_id
                 WHERE l.id = %s
                """,
                (log_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "ログが見つかりません"}), 404
            if row[1] != "lastfm":
                return jsonify({"error": "Last.fm 以外のログは削除できません"}), 400
            if row[0]:
                return jsonify({"error": "すでに非表示です"}), 400
            cur.execute(
                "UPDATE logs SET is_deleted = TRUE WHERE id = %s",
                (log_id,),
            )
            conn.commit()
            return jsonify({"ok": True})
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------ #
    # API: 統計（JSON）
    # ------------------------------------------------------------------ #
    @app.route("/api/stats")
    def api_stats():
        period   = request.args.get("period", "day")
        date_arg = request.args.get("date", str(datetime.now(JST).date()))

        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            jst = "AT TIME ZONE 'Asia/Tokyo'"

            # ---- 期間に応じた WHERE 句を生成 -------------------------
            if period == "day":
                log_where  = f"DATE(l.timestamp {jst}) = %s"
                log_params = (date_arg,)
                hd_where   = "date = %s"
                hd_params  = (date_arg,)

            elif period == "week":
                yr, wk    = date_arg.split("-W")
                log_where  = (f"EXTRACT(isoyear FROM l.timestamp {jst}) = %s "
                              f"AND EXTRACT(week FROM l.timestamp {jst}) = %s")
                log_params = (int(yr), int(wk))
                hd_where   = ("EXTRACT(isoyear FROM date) = %s "
                              "AND EXTRACT(week FROM date) = %s")
                hd_params  = (int(yr), int(wk))

            elif period == "month":
                log_where  = f"TO_CHAR(l.timestamp {jst}, 'YYYY-MM') = %s"
                log_params = (date_arg,)
                hd_where   = "TO_CHAR(date, 'YYYY-MM') = %s"
                hd_params  = (date_arg,)

            elif period == "year":
                log_where  = f"EXTRACT(year FROM l.timestamp {jst}) = %s"
                log_params = (int(date_arg),)
                hd_where   = "EXTRACT(year FROM date) = %s"
                hd_params  = (int(date_arg),)

            else:
                return jsonify({"error": "invalid period"}), 400

            # ---- 投稿数集計 ------------------------------------------
            cur.execute(f"""
                SELECT ds.type, COUNT(*)
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE AND {log_where}
                 GROUP BY ds.type
            """, log_params)
            by_type      = dict(cur.fetchall())
            misskey_cnt  = by_type.get("misskey",  0)
            mastodon_cnt = by_type.get("mastodon", 0)
            play_cnt     = by_type.get("lastfm",   0)
            post_cnt     = misskey_cnt + mastodon_cnt \
                         + by_type.get("rss", 0) + by_type.get("youtube", 0)
            breakdown    = f"Misskey {misskey_cnt} / Mastodon {mastodon_cnt}"

            # ---- ヘルスデータ ----------------------------------------
            if period == "day":
                cur.execute(
                    "SELECT steps, active_calories, heart_rate_avg FROM health_daily WHERE " + hd_where,
                    hd_params,
                )
                health = cur.fetchone()
                steps  = health[0] if health else None
            else:
                cur.execute(
                    "SELECT SUM(steps) FROM health_daily WHERE " + hd_where,
                    hd_params,
                )
                row   = cur.fetchone()
                steps = int(row[0]) if row and row[0] else None

            # ---- 天気 ------------------------------------------------
            if period == "day":
                cur.execute(
                    "SELECT temp_max, weather_desc, location, weather_main "
                    "FROM weather_daily WHERE " + hd_where,
                    hd_params,
                )
                w = cur.fetchone()
                weather_obj = {
                    "desc":     w[1] if w else None,
                    "temp":     float(w[0]) if w and w[0] else None,
                    "location": w[2] if w else None,
                    "main":     w[3] if w else None,
                } if w else None
            else:
                cur.execute(
                    """SELECT ROUND(AVG(temp_avg)::numeric, 1),
                              MIN(temp_min),
                              MAX(temp_max),
                              MAX(location)
                         FROM weather_daily WHERE """ + hd_where,
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

            # ---- 週ビュー: ISO 週の月〜日ごとの天気（stat 付近ストリップ用）----
            weather_days = None
            if period == "week":
                try:
                    yr_s, wk_s = date_arg.upper().split("-W", 1)
                    iso_y, iso_w = int(yr_s), int(wk_s)
                    monday = datetime.strptime(
                        f"{iso_y}-{iso_w:02d}-1", "%G-%V-%u"
                    ).date()
                    sunday = monday + timedelta(days=6)
                    cur.execute(
                        """
                        SELECT date, temp_max, temp_min, weather_desc, weather_main, location
                          FROM weather_daily
                         WHERE date >= %s AND date <= %s
                         ORDER BY date
                        """,
                        (monday, sunday),
                    )
                    by_date = {row[0]: row for row in cur.fetchall()}
                    weather_days = []
                    for i in range(7):
                        d = monday + timedelta(days=i)
                        row = by_date.get(d)
                        weather_days.append(
                            {
                                "date": d.isoformat(),
                                "temp_max": float(row[1])
                                if row and row[1] is not None
                                else None,
                                "temp_min": float(row[2])
                                if row and row[2] is not None
                                else None,
                                "desc": row[3] if row else None,
                                "main": row[4] if row else None,
                                "location": row[5] if row else None,
                            }
                        )
                except (ValueError, TypeError):
                    weather_days = []

            payload = {
                "period":           period,
                "posts":            post_cnt,
                "posts_breakdown":  breakdown,
                "plays":            play_cnt,
                "steps":            steps,
                "weather":          weather_obj,
            }
            if weather_days is not None:
                payload["weather_days"] = weather_days
            return jsonify(payload)
        finally:
            cur.close(); conn.close()

    # ------------------------------------------------------------------ #
    # 検索
    # ------------------------------------------------------------------ #
    @app.route("/search")
    def search():
        q         = request.args.get("q", "").strip()
        source_id = request.args.get("source_id", "")
        date_from = request.args.get("date_from", "")
        date_to   = request.args.get("date_to", "")
        entries   = []
        total     = 0

        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("SELECT id, name, type FROM data_sources WHERE is_active ORDER BY id")
            sources = cur.fetchall()

            if q:
                conditions = ["l.is_deleted = FALSE", "l.content LIKE %s"]
                params: list = [f"%{q}%"]
                if source_id:
                    conditions.append("l.source_id = %s")
                    params.append(int(source_id))
                if date_from:
                    conditions.append("l.timestamp >= %s")
                    params.append(date_from)
                if date_to:
                    conditions.append("l.timestamp < (%s::date + interval '1 day')")
                    params.append(date_to)

                where = " AND ".join(conditions)
                cur.execute(f"""
                    SELECT l.id, l.content, l.url,
                           (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                           l.metadata, ds.name, ds.type
                      FROM logs l
                      JOIN data_sources ds ON l.source_id = ds.id
                     WHERE {where}
                     ORDER BY l.timestamp DESC
                     LIMIT 200
                """, params)
                rows = cur.fetchall()
                entries = []
                for r in rows:
                    bi = TYPE_INFO.get(r[6], {"cls": "rss", "emoji": "🌐"})
                    entries.append(
                        {
                            "id": r[0],
                            "content": r[1],
                            "url": r[2],
                            "timestamp": r[3].strftime("%Y-%m-%d %H:%M"),
                            "date_jst": r[3].strftime("%Y-%m-%d"),
                            "metadata": r[4] or {},
                            "source_name": r[5],
                            "source_type": r[6],
                            "badge_cls": bi["cls"],
                            "badge_emoji": bi["emoji"],
                        }
                    )
                total = len(entries)
        finally:
            cur.close(); conn.close()

        return render_template("search.html",
            q=q, entries=entries, total=total,
            sources=sources, source_id=source_id,
            date_from=date_from, date_to=date_to)

    # ------------------------------------------------------------------ #
    # サマリー一覧
    # ------------------------------------------------------------------ #
    @app.route("/summaries")
    def summaries():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT id, period_type, period_start, period_end,
                       week_number, content, model, is_published, created_at
                  FROM summaries
                 WHERE period_type IN ('weekly', 'monthly')
                   AND summary_type = 'full'
                 ORDER BY period_start DESC
            """)
            rows  = cur.fetchall()
            dow_jp = ["月", "火", "水", "木", "金", "土", "日"]
            items = []
            for r in rows:
                it = {
                    "id": r[0],
                    "period_type": r[1],
                    "period_start": str(r[2]),
                    "period_end": str(r[3]),
                    "week_number": r[4],
                    "content": r[5],
                    "model": r[6],
                    "is_published": r[7],
                    "created_at": r[8].astimezone(JST).strftime("%Y-%m-%d %H:%M")
                    if r[8]
                    else "",
                    "day_links": None,
                }
                if r[1] == "weekly" and r[2]:
                    monday = r[2]
                    links = []
                    for i in range(7):
                        d = monday + timedelta(days=i)
                        wd = dow_jp[d.weekday()]
                        links.append(
                            {
                                "date": str(d),
                                "label": f"{d.month}/{d.day}({wd})",
                            }
                        )
                    it["day_links"] = links
                items.append(it)
        finally:
            cur.close(); conn.close()

        return render_template("summaries.html", items=items)

    def _summary_row_to_api_dict(r):
        """DB 行 → GET /api/summary 用 JSON（published_at は ISO 文字列）"""
        pub = r[8]
        if pub is not None and hasattr(pub, "isoformat"):
            pub = pub.isoformat()
        return {
            "id": r[0],
            "period_type": r[1],
            "period_start": str(r[2]),
            "period_end": str(r[3]),
            "week_number": r[4],
            "content": r[5],
            "model": r[6],
            "is_published": r[7],
            "published_at": pub,
        }

    @app.route("/api/summary")
    def api_summary():
        period = (request.args.get("period") or "").strip().lower()
        date_arg = (request.args.get("date") or "").strip()
        if period not in ("day", "week", "month", "year") or not date_arg:
            return jsonify(
                {"error": "period (day|week|month|year) and date required"}
            ), 400

        conn = get_db_conn()
        cur = conn.cursor()
        try:
            if period == "day":
                try:
                    day = date.fromisoformat(date_arg)
                except ValueError:
                    return jsonify({"error": "date must be YYYY-MM-DD for day"}), 400
                cur.execute(
                    """
                    SELECT id, period_type, period_start, period_end, week_number,
                           content, model, is_published, published_at
                      FROM summaries
                     WHERE period_type = 'daily'
                       AND period_start = %s
                       AND summary_type = 'full'
                    """,
                    (day,),
                )
                row = cur.fetchone()
                return jsonify(
                    {"summary": _summary_row_to_api_dict(row) if row else None}
                )

            if period == "week":
                s = date_arg.upper()
                if "-W" not in s:
                    return jsonify({"error": "date must be YYYY-Www for week"}), 400
                y_str, w_str = s.split("-W", 1)
                y, w = int(y_str), int(w_str)
                monday = datetime.strptime(f"{y}-{w:02d}-1", "%G-%V-%u").date()
                cur.execute(
                    """
                    SELECT id, period_type, period_start, period_end, week_number,
                           content, model, is_published, published_at
                      FROM summaries
                     WHERE period_type = 'weekly'
                       AND period_start = %s
                       AND summary_type = 'full'
                    """,
                    (monday,),
                )
                row = cur.fetchone()
                return jsonify(
                    {"summary": _summary_row_to_api_dict(row) if row else None}
                )

            if period == "month":
                try:
                    y, m = map(int, date_arg.split("-", 1))
                    first = date(y, m, 1)
                except (ValueError, TypeError):
                    return jsonify({"error": "date must be YYYY-MM for month"}), 400
                cur.execute(
                    """
                    SELECT id, period_type, period_start, period_end, week_number,
                           content, model, is_published, published_at
                      FROM summaries
                     WHERE period_type = 'monthly'
                       AND period_start = %s
                       AND summary_type = 'full'
                    """,
                    (first,),
                )
                row = cur.fetchone()
                return jsonify(
                    {"summary": _summary_row_to_api_dict(row) if row else None}
                )

            # year
            try:
                y = int(date_arg)
            except ValueError:
                return jsonify({"error": "date must be a year (e.g. 2026)"}), 400
            start = date(y, 1, 1)
            end = date(y, 12, 31)
            cur.execute(
                """
                SELECT id, period_type, period_start, period_end, week_number,
                       content, model, is_published, published_at
                  FROM summaries
                 WHERE period_type = 'monthly'
                   AND summary_type = 'full'
                   AND period_start >= %s AND period_start <= %s
                 ORDER BY period_start ASC
                """,
                (start, end),
            )
            rows = cur.fetchall()
            return jsonify(
                {"summaries": [_summary_row_to_api_dict(r) for r in rows]}
            )
        finally:
            cur.close()
            conn.close()

    @app.route("/api/summary/topics")
    def api_summary_topics():
        """period の全 summary_type を返す。日次・週次・月次トピックパネル用。
        period=day   date=YYYY-MM-DD
        period=week  date=YYYY-Www
        period=month date=YYYY-MM
        """
        period = (request.args.get("period") or "day").strip().lower()
        date_arg = (request.args.get("date") or "").strip()
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            if period == "day":
                try:
                    target_day = date.fromisoformat(date_arg)
                except ValueError:
                    return jsonify({"error": "date must be YYYY-MM-DD"}), 400
                period_type = "daily"
                period_start = target_day
            elif period == "week":
                s = date_arg.upper()
                if "-W" not in s:
                    return jsonify({"error": "date must be YYYY-Www for week"}), 400
                y_str, w_str = s.split("-W", 1)
                try:
                    period_start = datetime.strptime(
                        f"{int(y_str)}-{int(w_str):02d}-1", "%G-%V-%u"
                    ).date()
                except (ValueError, TypeError):
                    return jsonify({"error": "invalid week date"}), 400
                period_type = "weekly"
            elif period == "month":
                try:
                    y, m = map(int, date_arg.split("-", 1))
                    period_start = date(y, m, 1)
                except (ValueError, TypeError):
                    return jsonify({"error": "date must be YYYY-MM for month"}), 400
                period_type = "monthly"
            else:
                return jsonify({"error": "period must be day|week|month"}), 400

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
            rows = cur.fetchall()
            topics = {}
            for row in rows:
                stype, content, model_name, style, created = row
                topics[stype] = {
                    "content": content,
                    "model": model_name,
                    "prompt_style": style,
                    "created_at": created.astimezone(JST).strftime("%Y-%m-%d %H:%M")
                    if created else None,
                }
            return jsonify({"topics": topics, "period": period, "date": date_arg})
        finally:
            cur.close()
            conn.close()

    @app.route("/api/summaries/<int:sid>/publish", methods=["PATCH"])
    def api_summaries_publish(sid):
        data = request.get_json(silent=True) or {}
        if "is_published" not in data:
            return jsonify({"error": "is_published required"}), 400
        val = data["is_published"]
        if not isinstance(val, bool):
            return jsonify({"error": "is_published must be boolean"}), 400

        conn = get_db_conn()
        cur = conn.cursor()
        try:
            if val:
                cur.execute(
                    """
                    UPDATE summaries
                       SET is_published = TRUE, published_at = NOW()
                     WHERE id = %s
                    """,
                    (sid,),
                )
            else:
                cur.execute(
                    """
                    UPDATE summaries
                       SET is_published = FALSE, published_at = NULL
                     WHERE id = %s
                    """,
                    (sid,),
                )
            if cur.rowcount == 0:
                return jsonify({"error": "not found"}), 404
            conn.commit()
            return jsonify({"ok": True, "is_published": val})
        finally:
            cur.close()
            conn.close()

    @app.route("/api/summaries/generate", methods=["POST"])
    def api_summaries_generate():
        """Ollama 週次・月次・日次サマリーを subprocess で生成（カレンダー UI 用）。"""
        data = request.get_json(silent=True) or {}
        period = (data.get("period") or "").strip().lower()
        date_arg = (data.get("date") or "").strip()
        want_stream = bool(data.get("stream"))
        if period not in ("week", "month", "day") or not date_arg:
            return jsonify(
                {"error": "period (week|month|day) と date が必要です"}
            ), 400

        if period == "week":
            try:
                from summarizer.week_bounds import parse_iso_week_date

                y, w, _m, _s = parse_iso_week_date(date_arg)
                norm_date = f"{y}-W{w:02d}"
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        elif period == "month":
            try:
                from summarizer.month_bounds import parse_year_month

                y, mo = parse_year_month(date_arg)
                norm_date = f"{y}-{mo:02d}"
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            try:
                norm_date = date.fromisoformat(date_arg).isoformat()
            except ValueError:
                return jsonify({"error": "day の date は YYYY-MM-DD 形式です"}), 400

        py_exe = ROOT / "venv" / "bin" / "python"
        if not py_exe.is_file():
            return jsonify({"error": "venv/bin/python が見つかりません"}), 500

        # 1 リクエストあたりの Ollama 待ち。新パイプラインは週次で最大 ~8 回呼ぶため長めに設定。
        ollama_timeout = "1800"
        cmd = [
            str(py_exe),
            "-m",
            "summarizer.generate",
            "--period",
            period,
            "--date",
            norm_date,
            "--timeout",
            ollama_timeout,
        ]
        # 新パイプライン（既定）では --pipeline 不要。--legacy 指定時のみ hierarchical を渡す。
        use_legacy = bool(data.get("legacy"))
        if use_legacy:
            cmd.extend(["--legacy", "--pipeline", "hierarchical"])
        env_base = {**os.environ, "PYTHONPATH": str(ROOT)}
        # subprocess.run の上限。週次は複数トピック×7日分になり得るため長めに。
        gen_timeout = 7200 if period == "day" else 18000

        if want_stream:
            env_stream = {
                **env_base,
                "PLANET_SUMMARY_PROGRESS_MACHINE": "1",
            }

            @stream_with_context
            def ndjson_stream():
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    cwd=str(ROOT),
                    env=env_stream,
                )
                q: queue.Queue[str | None] = queue.Queue()
                stderr_buf: list[str] = []

                def pump_stderr() -> None:
                    try:
                        for line in iter(proc.stderr.readline, ""):
                            stderr_buf.append(line)
                            q.put(line.rstrip("\n"))
                    finally:
                        q.put(None)

                threading.Thread(target=pump_stderr, daemon=True).start()
                while True:
                    line = q.get()
                    if line is None:
                        break
                    prefix = "__PLANET_PROGRESS__ "
                    if line.startswith(prefix):
                        try:
                            payload = json.loads(line[len(prefix) :])
                            payload["type"] = "progress"
                            yield json.dumps(payload, ensure_ascii=False) + "\n"
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                rc = proc.wait()
                stdout = (proc.stdout.read() or "").strip()
                stderr_full = "".join(stderr_buf)
                if rc == 0:
                    if (
                        "ログが 0 件のためスキップ" in stderr_full
                        or "スキップします" in stderr_full
                    ):
                        msg = (
                            stderr_full[-500:]
                            if stderr_full
                            else "この期間のログがありません。"
                        )
                        yield json.dumps(
                            {
                                "type": "done",
                                "ok": True,
                                "skipped": True,
                                "message": msg,
                            },
                            ensure_ascii=False,
                        ) + "\n"
                    elif "保存しました" in stdout:
                        yield json.dumps(
                            {"type": "done", "ok": True, "skipped": False},
                            ensure_ascii=False,
                        ) + "\n"
                    else:
                        yield json.dumps(
                            {
                                "type": "done",
                                "ok": True,
                                "skipped": False,
                                "output": stdout[-400:] if stdout else "",
                            },
                            ensure_ascii=False,
                        ) + "\n"
                else:
                    err_tail = (
                        (stderr_full or stdout or "生成に失敗しました")[-1200:]
                    )
                    status_code = 400 if rc == 2 else 500
                    yield json.dumps(
                        {
                            "type": "done",
                            "ok": False,
                            "error": err_tail,
                            "code": rc,
                            "http_status": status_code,
                        },
                        ensure_ascii=False,
                    ) + "\n"

            return Response(
                ndjson_stream(),
                mimetype="application/x-ndjson; charset=utf-8",
            )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=gen_timeout,
                cwd=str(ROOT),
                env=env_base,
            )
        except subprocess.TimeoutExpired:
            return (
                jsonify(
                    {
                        "error": f"タイムアウト（{gen_timeout}秒）。Ollama の応答を確認してください。",
                    }
                ),
                504,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()

        if result.returncode == 0:
            if "ログが 0 件のためスキップ" in stderr or "スキップします" in stderr:
                msg = stderr[-500:] if stderr else "この期間のログがありません。"
                return jsonify({"ok": True, "skipped": True, "message": msg})
            if "保存しました" in stdout or not stderr:
                return jsonify({"ok": True, "skipped": False})
            return jsonify(
                {
                    "ok": True,
                    "skipped": False,
                    "output": stdout[-400:] if stdout else "",
                }
            )

        err_text = (stderr or stdout or "生成に失敗しました")[-1200:]
        status = 400 if result.returncode == 2 else 500
        return jsonify({"error": err_text}), status

    # ------------------------------------------------------------------ #
    # 統計
    # ------------------------------------------------------------------ #
    @app.route("/stats")
    def stats():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT TO_CHAR(timestamp AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS month,
                       ds.type, COUNT(*)
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                   AND l.timestamp >= NOW() - INTERVAL '12 months'
                 GROUP BY month, ds.type
                 ORDER BY month, ds.type
            """)
            monthly_raw = cur.fetchall()

            cur.execute("""
                SELECT EXTRACT(year FROM timestamp AT TIME ZONE 'Asia/Tokyo')::int AS year,
                       ds.type, COUNT(*)
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                 GROUP BY year, ds.type
                 ORDER BY year, ds.type
            """)
            yearly_raw = cur.fetchall()

            cur.execute("""
                SELECT ds.name, ds.type, COUNT(*)
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                 GROUP BY ds.name, ds.type
                 ORDER BY COUNT(*) DESC
            """)
            source_counts = cur.fetchall()
        finally:
            cur.close(); conn.close()

        return render_template("stats.html",
            monthly_raw=monthly_raw, yearly_raw=yearly_raw,
            source_counts=source_counts)

    # ------------------------------------------------------------------ #
    # ソース管理
    # ------------------------------------------------------------------ #
    @app.route("/sources")
    def sources():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT id, name, type, base_url, account, is_active,
                       created_at, sort_order, short_name
                  FROM data_sources ORDER BY sort_order, id
            """)
            rows  = cur.fetchall()
            items = [{
                "id":         r[0],
                "name":       r[1],
                "type":       r[2],
                "base_url":   r[3],
                "account":    r[4],
                "is_active":  r[5],
                "created_at": r[6].astimezone(JST).strftime("%Y-%m-%d") if r[6] else "",
                "sort_order": r[7],
                "short_name_db":   r[8],
                "short_name_auto": _auto_short_name(r[2], r[3], r[1]),
            } for r in rows]
        finally:
            cur.close(); conn.close()

        return render_template("sources.html", items=items)

    @app.route("/sources/<int:source_id>/toggle", methods=["POST"])
    def source_toggle(source_id):
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE data_sources SET is_active = NOT is_active WHERE id = %s RETURNING is_active",
                (source_id,)
            )
            new_state = cur.fetchone()[0]
            conn.commit()
            return jsonify({"is_active": new_state})
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close(); conn.close()

    @app.route("/sources/<int:source_id>/move", methods=["POST"])
    def source_move(source_id):
        direction = request.json.get("direction")  # "up" | "down"
        if direction not in ("up", "down"):
            return jsonify({"error": "invalid direction"}), 400
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("SELECT sort_order FROM data_sources WHERE id = %s", (source_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "not found"}), 404
            cur_order = row[0]

            if direction == "up":
                cur.execute("""
                    SELECT id, sort_order FROM data_sources
                     WHERE sort_order < %s ORDER BY sort_order DESC LIMIT 1
                """, (cur_order,))
            else:
                cur.execute("""
                    SELECT id, sort_order FROM data_sources
                     WHERE sort_order > %s ORDER BY sort_order ASC LIMIT 1
                """, (cur_order,))

            adj = cur.fetchone()
            if not adj:
                return jsonify({"ok": True})  # 端なので何もしない

            adj_id, adj_order = adj
            cur.execute("UPDATE data_sources SET sort_order = %s WHERE id = %s", (adj_order, source_id))
            cur.execute("UPDATE data_sources SET sort_order = %s WHERE id = %s", (cur_order, adj_id))
            conn.commit()
            return jsonify({"ok": True})
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close(); conn.close()

    @app.route("/sources/<int:source_id>/rename", methods=["POST"])
    def source_rename(source_id):
        short_name = (request.json.get("short_name") or "").strip()
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE data_sources SET short_name = %s WHERE id = %s",
                (short_name or None, source_id),
            )
            conn.commit()
            return jsonify({"ok": True, "short_name": short_name or None})
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close(); conn.close()

    # ------------------------------------------------------------------ #
    # API: 手動収集
    # ------------------------------------------------------------------ #
    COLLECTOR_MAP = {
        "misskey":  ROOT / "collectors" / "misskey.py",
        "mastodon": ROOT / "collectors" / "mastodon.py",
        "lastfm":   ROOT / "collectors" / "lastfm.py",
        "weather":  ROOT / "collectors" / "weather.py",
        "github":   ROOT / "collectors" / "github.py",
        "rss":      ROOT / "collectors" / "rss.py",
        "youtube":  ROOT / "collectors" / "youtube.py",
        "scrapbox": ROOT / "collectors" / "scrapbox.py",
        "all":      ROOT / "collect_all.py",
    }
    PYTHON = ROOT / "venv" / "bin" / "python"

    @app.route("/api/collect/<string:stype>", methods=["POST"])
    def api_collect(stype):
        script = COLLECTOR_MAP.get(stype)
        if not script:
            return jsonify({"error": f"収集スクリプトがありません（{stype}）"}), 400
        try:
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            result = subprocess.run(
                [str(PYTHON), str(script)],
                capture_output=True, text=True,
                timeout=120, cwd=str(ROOT),
                env=env,
            )
            if result.returncode == 0:
                # 最後の 600 文字だけ返す（大量出力対策）
                out = (result.stdout or "").strip()
                return jsonify({"ok": True, "output": out[-600:] if out else "完了"})
            else:
                err = (result.stderr or result.stdout or "エラー").strip()
                return jsonify({"error": err[-600:]}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "タイムアウト（120秒）"}), 504
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------ #
    # API: Netflix / Prime 視聴 CSV 取り込み（ソース管理から DnD）
    # ------------------------------------------------------------------ #
    @app.route("/api/import/streaming-csv", methods=["POST"])
    def api_import_streaming_csv():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "file が必要です"}), 400
        cfg = load_config()
        si = cfg.get("streaming_import") or {}
        default_profile = (si.get("netflix_profile") or "ホ").strip()
        profile_raw = (request.form.get("netflix_profile") or "").strip()

        suffix = Path(f.filename).suffix or ".csv"
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="planet-streaming-", suffix=suffix)
            os.close(fd)
            f.save(tmp_path)
            path = Path(tmp_path)
            try:
                with open(path, encoding="utf-8-sig", newline="") as cf:
                    hdr_fmt = detect_format(csv.DictReader(cf).fieldnames)
                prof_kw = None
                if hdr_fmt == "netflix_activity":
                    prof_kw = profile_raw or default_profile
                res = import_streaming_csv(
                    path,
                    fmt=None,
                    dry_run=False,
                    strict=False,
                    netflix_profile=prof_kw,
                )
            finally:
                path.unlink(missing_ok=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        body = {
            "ok": res.ok,
            "skip": res.skip,
            "err": res.err,
            "format": res.format,
            "success": res.success,
            "messages": res.messages,
        }
        return jsonify(body), (200 if res.success else 500)

    # ------------------------------------------------------------------ #
    # 設定画面
    # ------------------------------------------------------------------ #
    _SETTINGS_KEYS = {
        "ollama_base_url":       ("ollama", "base_url"),
        "ollama_model":          ("ollama", "model"),
        "max_log_lines_daily":   ("summarizer", "max_log_lines_daily"),
        "max_log_lines_weekly":  ("summarizer", "max_log_lines_weekly"),
        "max_log_lines_monthly": ("summarizer", "max_log_lines_monthly"),
        "ollama_timeout_sec":    ("summarizer", "ollama_timeout_sec"),
    }

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        try:
            cfg = load_config()
            result = {}
            ollama = cfg.get("ollama") or {}
            summarizer = cfg.get("summarizer") or {}
            result["ollama_base_url"]       = ollama.get("base_url", "")
            result["ollama_model"]          = ollama.get("model", "")
            result["max_log_lines_daily"]   = summarizer.get("max_log_lines_daily", 0)
            result["max_log_lines_weekly"]  = summarizer.get("max_log_lines_weekly", 0)
            result["max_log_lines_monthly"] = summarizer.get("max_log_lines_monthly", 0)
            result["ollama_timeout_sec"]    = summarizer.get("ollama_timeout_sec", 0)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/settings", methods=["POST"])
    def api_settings_save():
        """settings.toml の [ollama] / [summarizer] セクションのみ更新する。"""
        data = request.get_json(silent=True) or {}
        try:
            path = CONFIG_PATH
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)

            def _set_toml_key(lines, section, key, value):
                """section 内の key = value を書き換える（値が無ければセクション末に追記）。
                value が None または空文字の場合は変更しない。
                """
                if value is None or (isinstance(value, str) and not value):
                    return lines
                if isinstance(value, int) and value == 0:
                    return lines

                in_sec = False
                key_found = False
                sec_end = None
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == f"[{section}]":
                        in_sec = True
                        sec_end = i + 1
                        continue
                    if in_sec and stripped.startswith("[") and not stripped.startswith(f"[{section}"):
                        in_sec = False
                    if in_sec:
                        if stripped and not stripped.startswith("#"):
                            sec_end = i + 1
                        if re.match(rf"^{re.escape(key)}\s*=", stripped):
                            if isinstance(value, str):
                                lines[i] = f'{key} = "{value}"\n'
                            else:
                                lines[i] = f"{key} = {value}\n"
                            key_found = True
                            break
                if not key_found and sec_end is not None:
                    if isinstance(value, str):
                        new_line = f'{key} = "{value}"\n'
                    else:
                        new_line = f"{key} = {value}\n"
                    lines.insert(sec_end, new_line)
                return lines

            # Ollama 設定
            if data.get("ollama_base_url"):
                lines = _set_toml_key(lines, "ollama", "base_url", data["ollama_base_url"])
            if data.get("ollama_model"):
                lines = _set_toml_key(lines, "ollama", "model", data["ollama_model"])

            # Summarizer 設定（[summarizer] セクションが無ければ末尾に追記）
            summarizer_keys = {
                "max_log_lines_daily":   data.get("max_log_lines_daily", 0),
                "max_log_lines_weekly":  data.get("max_log_lines_weekly", 0),
                "max_log_lines_monthly": data.get("max_log_lines_monthly", 0),
                "ollama_timeout_sec":    data.get("ollama_timeout_sec", 0),
            }
            has_summarizer_section = any(l.strip() == "[summarizer]" for l in lines)
            if not has_summarizer_section:
                lines.append("\n[summarizer]\n")

            for key, val in summarizer_keys.items():
                if val and val > 0:
                    lines = _set_toml_key(lines, "summarizer", key, val)

            path.write_text("".join(lines), encoding="utf-8")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------ #
    # プロンプト編集画面
    # ------------------------------------------------------------------ #
    PROMPTS_DIR = ROOT / "summarizer" / "prompts"
    _SAFE_PROMPT_NAME = re.compile(r'^[a-z][a-z0-9_]*\.txt$')

    @app.route("/prompts")
    def prompts_page():
        return render_template("prompts.html")

    @app.route("/api/prompts")
    def api_prompts_list():
        try:
            files = sorted(
                p.name for p in PROMPTS_DIR.glob("*.txt")
            )
            return jsonify({"files": files})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/prompts/<name>", methods=["GET"])
    def api_prompts_get(name):
        if not _SAFE_PROMPT_NAME.match(name):
            return jsonify({"error": "不正なファイル名です"}), 400
        path = PROMPTS_DIR / name
        if not path.is_file():
            return jsonify({"error": "ファイルが見つかりません"}), 404
        try:
            content = path.read_text(encoding="utf-8")
            return jsonify({"name": name, "content": content})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/prompts/<name>", methods=["POST"])
    def api_prompts_save(name):
        if not _SAFE_PROMPT_NAME.match(name):
            return jsonify({"error": "不正なファイル名です"}), 400
        path = PROMPTS_DIR / name
        if not path.is_file():
            return jsonify({"error": "ファイルが見つかりません"}), 404
        data = request.get_json(silent=True) or {}
        content = data.get("content")
        if content is None:
            return jsonify({"error": "content が必要です"}), 400
        try:
            path.write_text(content, encoding="utf-8")
            return jsonify({"ok": True, "name": name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


if __name__ == "__main__":
    config    = load_config()
    flask_cfg = config["flask"]
    app       = create_app()
    app.run(
        host=flask_cfg.get("host", "0.0.0.0"),
        port=flask_cfg.get("port", 5000),
        debug=flask_cfg.get("debug", False),
    )
