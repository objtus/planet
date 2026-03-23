"""Planet ダッシュボード Flask アプリ (Phase 5)"""

import sys
import tomllib
import psycopg2
from pathlib import Path
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ingest.api import ingest_bp  # noqa: E402

CONFIG_PATH = ROOT / "config" / "settings.toml"
JST = timezone(timedelta(hours=9))

# ソース表示名のドメイン→短縮名マッピング
SHORT_NAME_MAP = {
    "misskey.io":           "msk.io",
    "tanoshii.site":        "tanoshii",
    "sushi.ski":            "sushi.ski",
    "mistodon.cloud":       "mistodon",
    "mastodon.cloud":       "masto.cloud",
    "msk.ilnk.info":        "ilnk",
    "yuinoid.neocities.org": "100%health",
    "github.com":           "github",
}

# ソース種別ごとの CSS クラスと絵文字
TYPE_INFO = {
    "misskey":  {"cls": "msk",  "emoji": "🍣"},
    "mastodon": {"cls": "mst",  "emoji": "🐘"},
    "lastfm":   {"cls": "lfm",  "emoji": "🎵"},
    "health":   {"cls": "hlth", "emoji": "🍎"},
    "photo":    {"cls": "hlth", "emoji": "📷"},
    "rss":      {"cls": "rss",  "emoji": "🌐"},
    "weather":  {"cls": "rss",  "emoji": "☁️"},
    "github":   {"cls": "rss",  "emoji": "🐱"},
    "youtube":  {"cls": "rss",  "emoji": "▶️"},
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


def make_source_info(row):
    """data_sources の行から表示用の dict を返す"""
    sid, name, stype, base_url, account = row[0], row[1], row[2], row[3], row[4]
    domain  = (base_url or "").replace("https://", "").replace("http://", "").rstrip("/")
    info    = TYPE_INFO.get(stype, {"cls": "rss", "emoji": "🌐"})
    favicon = f"{base_url}/favicon.ico" if base_url else None

    if stype == "lastfm":
        short_name = "last.fm"
    elif stype == "health":
        short_name = "health"
    elif stype == "photo":
        short_name = "photo"
    elif stype == "weather":
        short_name = "weather"
    elif stype == "github":
        short_name = "github"
    elif stype == "youtube":
        short_name = "youtube"
    else:
        short_name = SHORT_NAME_MAP.get(domain, domain or name)

    return {
        "id":          sid,
        "name":        name,
        "type":        stype,
        "short_name":  short_name,
        "cls":         info["cls"],
        "emoji":       info["emoji"],
        "favicon_url": favicon,
    }


def create_app():
    app = Flask(__name__)
    config = load_config()
    app.secret_key = config["flask"]["secret_key"]

    app.register_blueprint(ingest_bp)

    # ------------------------------------------------------------------ #
    # カレンダー（メイン画面）
    # ------------------------------------------------------------------ #
    @app.route("/")
    def calendar():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            # 全期間の日別投稿数（ヒートマップ用）
            cur.execute("""
                SELECT DATE(timestamp AT TIME ZONE 'Asia/Tokyo') AS d, COUNT(*)
                  FROM logs
                 WHERE is_deleted = FALSE
                 GROUP BY d
            """)
            heatmap = {str(r[0]): r[1] for r in cur.fetchall()}

            # アクティブなソース一覧
            cur.execute("""
                SELECT id, name, type, base_url, account
                  FROM data_sources
                 WHERE is_active
                 ORDER BY id
            """)
            sources = [make_source_info(r) for r in cur.fetchall()]

            today = datetime.now(JST).date()
            return render_template("calendar.html",
                heatmap=heatmap, sources=sources, today=str(today))
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
            if period == "day":
                cur.execute("""
                    SELECT l.id, l.source_id, l.content, l.url,
                           (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                           l.metadata
                      FROM logs l
                     WHERE l.is_deleted = FALSE
                       AND DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp
                """, (date_arg,))

            elif period == "week":
                # date_arg: "YYYY-WXX"
                year_part, week_part = date_arg.split("-W")
                cur.execute("""
                    SELECT l.id, l.source_id, l.content, l.url,
                           (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                           l.metadata
                      FROM logs l
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(isoyear FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                       AND EXTRACT(week    FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp
                     LIMIT 1000
                """, (int(year_part), int(week_part)))

            elif period == "month":
                # date_arg: "YYYY-MM"
                cur.execute("""
                    SELECT l.id, l.source_id, l.content, l.url,
                           (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                           l.metadata
                      FROM logs l
                     WHERE l.is_deleted = FALSE
                       AND TO_CHAR(l.timestamp AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') = %s
                     ORDER BY l.timestamp
                     LIMIT 2000
                """, (date_arg,))

            elif period == "year":
                # date_arg: "YYYY"
                cur.execute("""
                    SELECT l.id, l.source_id, l.content, l.url,
                           (l.timestamp AT TIME ZONE 'Asia/Tokyo') AS ts,
                           l.metadata
                      FROM logs l
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(year FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp
                     LIMIT 5000
                """, (int(date_arg),))

            else:
                return jsonify({"error": "invalid period"}), 400

            rows    = cur.fetchall()
            entries = []
            for r in rows:
                meta     = r[5] or {}
                ts       = r[4]
                is_boost = bool(meta.get("renote_id") or meta.get("reblog_id"))
                entries.append({
                    "id":        r[0],
                    "source_id": r[1],
                    "content":   r[2] or "",
                    "url":       r[3],
                    "time":      ts.strftime("%H:%M"),
                    "date":      ts.strftime("%Y-%m-%d"),
                    "cw":        meta.get("cw"),
                    "is_boost":  is_boost,
                })
            return jsonify({"entries": entries, "count": len(entries)})
        finally:
            cur.close(); conn.close()

    # ------------------------------------------------------------------ #
    # API: 統計（JSON）
    # ------------------------------------------------------------------ #
    @app.route("/api/stats")
    def api_stats():
        date_arg = request.args.get("date", str(datetime.now(JST).date()))

        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            # ソース種別ごとの投稿数
            cur.execute("""
                SELECT ds.type, COUNT(*)
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                   AND DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                 GROUP BY ds.type
            """, (date_arg,))
            by_type = dict(cur.fetchall())

            misskey_cnt  = by_type.get("misskey",  0)
            mastodon_cnt = by_type.get("mastodon", 0)
            play_cnt     = by_type.get("lastfm",   0)
            post_cnt     = misskey_cnt + mastodon_cnt \
                         + by_type.get("rss", 0) + by_type.get("youtube", 0)
            breakdown    = f"Misskey {misskey_cnt} / Mastodon {mastodon_cnt}"

            # ヘルスデータ
            cur.execute("""
                SELECT steps, active_calories, heart_rate_avg
                  FROM health_daily WHERE date = %s
            """, (date_arg,))
            health = cur.fetchone()

            # 天気
            cur.execute("""
                SELECT temp_max, weather_desc, location
                  FROM weather_daily WHERE date = %s
            """, (date_arg,))
            weather = cur.fetchone()

            return jsonify({
                "posts":            post_cnt,
                "posts_breakdown":  breakdown,
                "plays":            play_cnt,
                "steps":            health[0] if health else None,
                "weather": {
                    "desc":     weather[1] if weather else None,
                    "temp":     float(weather[0]) if weather and weather[0] else None,
                    "location": weather[2] if weather else None,
                } if weather else None,
            })
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
                entries = [
                    {
                        "id": r[0], "content": r[1], "url": r[2],
                        "timestamp": r[3].strftime("%Y-%m-%d %H:%M"),
                        "metadata":  r[4] or {},
                        "source_name": r[5], "source_type": r[6],
                    }
                    for r in rows
                ]
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
                 ORDER BY period_start DESC
            """)
            rows  = cur.fetchall()
            items = [{
                "id": r[0], "period_type": r[1],
                "period_start": str(r[2]), "period_end": str(r[3]),
                "week_number": r[4], "content": r[5],
                "model": r[6], "is_published": r[7],
                "created_at": r[8].astimezone(JST).strftime("%Y-%m-%d %H:%M") if r[8] else "",
            } for r in rows]
        finally:
            cur.close(); conn.close()

        return render_template("summaries.html", items=items)

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
            monthly_raw=monthly_raw, source_counts=source_counts)

    # ------------------------------------------------------------------ #
    # ソース管理
    # ------------------------------------------------------------------ #
    @app.route("/sources")
    def sources():
        conn = get_db_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT id, name, type, base_url, account, is_active, created_at
                  FROM data_sources ORDER BY id
            """)
            rows  = cur.fetchall()
            items = [{
                "id": r[0], "name": r[1], "type": r[2],
                "base_url": r[3], "account": r[4], "is_active": r[5],
                "created_at": r[6].astimezone(JST).strftime("%Y-%m-%d") if r[6] else "",
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
