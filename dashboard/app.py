"""Planet ダッシュボード Flask アプリ (Phase 5)"""

import sys
import tomllib
import psycopg2
from pathlib import Path
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify, redirect, url_for

# planet/ ルートを sys.path に追加して ingest パッケージをインポート
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ingest.api import ingest_bp  # noqa: E402

CONFIG_PATH = ROOT / "config" / "settings.toml"
JST = timezone(timedelta(hours=9))


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_db_conn():
    db = load_config()["database"]
    return psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )


def create_app():
    app = Flask(__name__)
    config = load_config()
    app.secret_key = config["flask"]["secret_key"]

    app.register_blueprint(ingest_bp)

    # ------------------------------------------------------------------ #
    # カレンダー（メイン）
    # ------------------------------------------------------------------ #
    @app.route("/")
    def calendar():
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            # 直近365日の日別投稿数（ヒートマップ用）
            cur.execute("""
                SELECT DATE(timestamp AT TIME ZONE 'Asia/Tokyo') AS d,
                       COUNT(*) AS cnt
                  FROM logs
                 WHERE is_deleted = FALSE
                   AND timestamp >= NOW() - INTERVAL '365 days'
                 GROUP BY d
                 ORDER BY d
            """)
            heatmap_raw = cur.fetchall()
            heatmap = {str(row[0]): row[1] for row in heatmap_raw}

            # 合計ログ件数
            cur.execute("SELECT COUNT(*) FROM logs WHERE is_deleted = FALSE")
            total_logs = cur.fetchone()[0]

            # 今日の日付（JST）
            today = datetime.now(JST).date()

            return render_template(
                "calendar.html",
                heatmap=heatmap,
                total_logs=total_logs,
                today=str(today),
            )
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------ #
    # タイムライン（日・週・月・年）
    # ------------------------------------------------------------------ #
    @app.route("/timeline")
    def timeline():
        period = request.args.get("period", "day")
        date_str = request.args.get("date", str(datetime.now(JST).date()))

        conn = get_db_conn()
        cur = conn.cursor()
        try:
            if period == "day":
                cur.execute("""
                    SELECT l.id, l.content, l.url, l.timestamp, l.metadata,
                           ds.name AS source_name, ds.type AS source_type
                      FROM logs l
                      JOIN data_sources ds ON l.source_id = ds.id
                     WHERE l.is_deleted = FALSE
                       AND DATE(l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp DESC
                """, (date_str,))
            elif period == "week":
                # ISO週番号指定 例: date_str = "2026-W12"
                cur.execute("""
                    SELECT l.id, l.content, l.url, l.timestamp, l.metadata,
                           ds.name AS source_name, ds.type AS source_type
                      FROM logs l
                      JOIN data_sources ds ON l.source_id = ds.id
                     WHERE l.is_deleted = FALSE
                       AND EXTRACT(isoyear FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                       AND EXTRACT(week    FROM l.timestamp AT TIME ZONE 'Asia/Tokyo') = %s
                     ORDER BY l.timestamp DESC
                """, (date_str[:4], date_str[6:]))
            else:
                # month: date_str = "2026-03"
                cur.execute("""
                    SELECT l.id, l.content, l.url, l.timestamp, l.metadata,
                           ds.name AS source_name, ds.type AS source_type
                      FROM logs l
                      JOIN data_sources ds ON l.source_id = ds.id
                     WHERE l.is_deleted = FALSE
                       AND TO_CHAR(l.timestamp AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') = %s
                     ORDER BY l.timestamp DESC
                     LIMIT 500
                """, (date_str,))

            rows = cur.fetchall()
            entries = [
                {
                    "id": r[0],
                    "content": r[1],
                    "url": r[2],
                    "timestamp": r[3].astimezone(JST).strftime("%H:%M"),
                    "timestamp_full": r[3].astimezone(JST).strftime("%Y-%m-%d %H:%M"),
                    "metadata": r[4] or {},
                    "source_name": r[5],
                    "source_type": r[6],
                }
                for r in rows
            ]

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"entries": entries, "count": len(entries)})

            return render_template(
                "timeline.html",
                entries=entries,
                period=period,
                date_str=date_str,
            )
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------ #
    # 検索
    # ------------------------------------------------------------------ #
    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        source_id = request.args.get("source_id", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        entries = []
        total = 0

        conn = get_db_conn()
        cur = conn.cursor()
        try:
            # ソース一覧（フィルター用）
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
                    SELECT l.id, l.content, l.url, l.timestamp, l.metadata,
                           ds.name, ds.type
                      FROM logs l
                      JOIN data_sources ds ON l.source_id = ds.id
                     WHERE {where}
                     ORDER BY l.timestamp DESC
                     LIMIT 200
                """, params)
                rows = cur.fetchall()
                entries = [
                    {
                        "id": r[0],
                        "content": r[1],
                        "url": r[2],
                        "timestamp": r[3].astimezone(JST).strftime("%Y-%m-%d %H:%M"),
                        "metadata": r[4] or {},
                        "source_name": r[5],
                        "source_type": r[6],
                    }
                    for r in rows
                ]
                total = len(entries)

        finally:
            cur.close()
            conn.close()

        return render_template(
            "search.html",
            q=q, entries=entries, total=total,
            sources=sources,
            source_id=source_id, date_from=date_from, date_to=date_to,
        )

    # ------------------------------------------------------------------ #
    # サマリー一覧
    # ------------------------------------------------------------------ #
    @app.route("/summaries")
    def summaries():
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, period_type, period_start, period_end,
                       week_number, content, model, is_published, created_at
                  FROM summaries
                 ORDER BY period_start DESC
            """)
            rows = cur.fetchall()
            items = [
                {
                    "id": r[0], "period_type": r[1],
                    "period_start": str(r[2]), "period_end": str(r[3]),
                    "week_number": r[4], "content": r[5],
                    "model": r[6], "is_published": r[7],
                    "created_at": r[8].astimezone(JST).strftime("%Y-%m-%d %H:%M") if r[8] else "",
                }
                for r in rows
            ]
        finally:
            cur.close()
            conn.close()

        return render_template("summaries.html", items=items)

    # ------------------------------------------------------------------ #
    # 統計
    # ------------------------------------------------------------------ #
    @app.route("/stats")
    def stats():
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            # 月別投稿数（直近12ヶ月）
            cur.execute("""
                SELECT TO_CHAR(timestamp AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS month,
                       ds.type, COUNT(*) AS cnt
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                   AND l.timestamp >= NOW() - INTERVAL '12 months'
                 GROUP BY month, ds.type
                 ORDER BY month, ds.type
            """)
            monthly_raw = cur.fetchall()

            # ソース別合計
            cur.execute("""
                SELECT ds.name, ds.type, COUNT(*) AS cnt
                  FROM logs l
                  JOIN data_sources ds ON l.source_id = ds.id
                 WHERE l.is_deleted = FALSE
                 GROUP BY ds.name, ds.type
                 ORDER BY cnt DESC
            """)
            source_counts = cur.fetchall()

        finally:
            cur.close()
            conn.close()

        return render_template(
            "stats.html",
            monthly_raw=monthly_raw,
            source_counts=source_counts,
        )

    # ------------------------------------------------------------------ #
    # ソース管理
    # ------------------------------------------------------------------ #
    @app.route("/sources")
    def sources():
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, name, type, base_url, account, is_active, created_at
                  FROM data_sources
                 ORDER BY id
            """)
            rows = cur.fetchall()
            items = [
                {
                    "id": r[0], "name": r[1], "type": r[2],
                    "base_url": r[3], "account": r[4],
                    "is_active": r[5],
                    "created_at": r[6].astimezone(JST).strftime("%Y-%m-%d") if r[6] else "",
                }
                for r in rows
            ]
        finally:
            cur.close()
            conn.close()

        return render_template("sources.html", items=items)

    @app.route("/sources/<int:source_id>/toggle", methods=["POST"])
    def source_toggle(source_id):
        conn = get_db_conn()
        cur = conn.cursor()
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
            cur.close()
            conn.close()

    return app


if __name__ == "__main__":
    config = load_config()
    flask_cfg = config["flask"]
    app = create_app()
    app.run(
        host=flask_cfg.get("host", "0.0.0.0"),
        port=flask_cfg.get("port", 5000),
        debug=flask_cfg.get("debug", False),
    )
