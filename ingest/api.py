"""iPhone からのデータ受け取り Flask API (Phase 4)"""

import json
import tomllib
import psycopg2
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, Blueprint, request, jsonify

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"

JST = timezone(timedelta(hours=9))

HEALTH_SOURCE_ID = 9
PHOTO_SOURCE_ID = 10


def _normalize_calendar_date_jst(raw) -> str:
    """YYYY-MM-DD または ISO 8601 日時を JST の暦日にそろえる（ingest の date 用）。"""
    s = str(raw).strip()
    if len(s) == 10 and s[4:5] == "-" and s[7:8] == "-":
        return s
    try:
        ts = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(
            "date は YYYY-MM-DD または ISO 8601 日時である必要があります"
        ) from None


def _source_id_by_type(cur, stype: str) -> int:
    cur.execute("SELECT id FROM data_sources WHERE type = %s LIMIT 1", (stype,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"data_sources に type={stype!r} がありません（マイグレーション未実行の可能性）")
    return row[0]


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_db_conn(config):
    db = config["database"]
    return psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )


def _archive_timeline_anchor_requested(data: dict) -> bool:
    """手動バックフィル: タイムライン上は date の JST 夜に載せる（オートメーション想定時刻）。"""
    v = data.get("archive")
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on", "y")


def _health_log_timestamp_jst_anchor(date_str: str, segment: str | None) -> datetime:
    """date（YYYY-MM-DD）の JST 固定時刻。分割時は movement→23:49, それ以外→23:50。"""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    if segment == "movement":
        h, m = 23, 49
    else:
        h, m = 23, 50
    local = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=JST)
    return local.astimezone(timezone.utc)


def _health_log_content(
    steps,
    active_calories,
    heart_rate_avg,
    exercise_minutes,
    stand_hours,
) -> str:
    """送信された指標だけを並べたタイムライン用本文（心拍は平均・安静時のみ表記）。"""
    parts = []
    if steps is not None:
        parts.append(f"歩数: {steps:,}歩")
    if active_calories is not None:
        parts.append(f"消費カロリー: {active_calories}kcal")
    if heart_rate_avg is not None:
        parts.append(f"心拍数: {heart_rate_avg}bpm")
    if exercise_minutes is not None:
        parts.append(f"運動: {exercise_minutes}分")
    if stand_hours is not None:
        parts.append(f"スタンド: {stand_hours}時間")
    return " / ".join(parts)


def _upsert_health(cur, data: dict) -> dict:
    """ヘルスデータを logs と health_daily にupsert"""
    date_str = _normalize_calendar_date_jst(data["date"])

    raw_seg = data.get("health_segment")
    if raw_seg is not None and str(raw_seg).strip() != "":
        segment = str(raw_seg).strip()
        if segment not in ("movement", "activity"):
            raise ValueError(
                "health_segment は 'movement' または 'activity' である必要があります"
            )
        original_id = f"{date_str}#{segment}"
    else:
        segment = None
        original_id = date_str

    def _int(v):
        return round(v) if v is not None else None

    steps            = _int(data.get("steps"))
    active_calories  = _int(data.get("active_calories"))
    heart_rate_avg   = _int(data.get("heart_rate_avg"))
    heart_rate_max   = _int(data.get("heart_rate_max"))
    heart_rate_min   = _int(data.get("heart_rate_min"))
    exercise_minutes = _int(data.get("exercise_minutes"))
    stand_hours      = _int(data.get("stand_hours"))

    content = _health_log_content(
        steps,
        active_calories,
        heart_rate_avg,
        exercise_minutes,
        stand_hours,
    )
    if not content:
        raise ValueError("ヘルス指標が1つもありません（いずれかの数値キーを送ってください）")

    archive_anchor = _archive_timeline_anchor_requested(data)
    if archive_anchor:
        ts = _health_log_timestamp_jst_anchor(date_str, segment)
    else:
        ts = datetime.now(timezone.utc)

    meta = {"type": "health", "date": date_str}
    if segment:
        meta["health_segment"] = segment
    if archive_anchor:
        meta["archive_timeline"] = True

    # logs upsert（分割時は original_id が日付ごとに2行）
    cur.execute(
        """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
           VALUES (%s, %s, %s, NULL, %s, %s)
           ON CONFLICT (source_id, original_id) DO UPDATE
             SET content  = EXCLUDED.content,
                 metadata = EXCLUDED.metadata,
                 timestamp = EXCLUDED.timestamp
           RETURNING id""",
        (
            HEALTH_SOURCE_ID, original_id, content, ts,
            json.dumps(meta),
        ),
    )
    log_id = cur.fetchone()[0]

    # health_daily upsert
    cur.execute(
        """INSERT INTO health_daily
               (log_id, date, steps, active_calories,
                heart_rate_avg, heart_rate_max, heart_rate_min,
                exercise_minutes, stand_hours)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (date) DO UPDATE SET
               log_id           = EXCLUDED.log_id,
               steps            = COALESCE(EXCLUDED.steps,            health_daily.steps),
               active_calories  = COALESCE(EXCLUDED.active_calories,  health_daily.active_calories),
               heart_rate_avg   = COALESCE(EXCLUDED.heart_rate_avg,   health_daily.heart_rate_avg),
               heart_rate_max   = COALESCE(EXCLUDED.heart_rate_max,   health_daily.heart_rate_max),
               heart_rate_min   = COALESCE(EXCLUDED.heart_rate_min,   health_daily.heart_rate_min),
               exercise_minutes = COALESCE(EXCLUDED.exercise_minutes, health_daily.exercise_minutes),
               stand_hours      = COALESCE(EXCLUDED.stand_hours,      health_daily.stand_hours)""",
        (
            log_id, date_str, steps, active_calories,
            heart_rate_avg, heart_rate_max, heart_rate_min,
            exercise_minutes, stand_hours,
        ),
    )

    out = {
        "date": date_str,
        "log_id": log_id,
        "original_id": original_id,
        "archive_timeline": archive_anchor,
    }
    if segment:
        out["health_segment"] = segment
    return out


def _upsert_photos(cur, data: dict) -> dict:
    """写真メタデータを logs と health_daily にupsert"""

    # 新形式: count + photos_json（位置情報付き）or count のみ
    if "date" in data and "count" in data:
        date_str = data["date"]
        count = int(data["count"])
        ts = datetime.now(timezone.utc)

        # photos_json が文字列で渡された場合はパースして位置情報を取り出す
        photo_locations = None
        # "photo_json" / "photos_json" どちらのキー名でも受け付ける
        photos_json_str = data.get("photos_json") or data.get("photo_json")
        if photos_json_str:
            try:
                # 住所に含まれる改行をスペースに変換してからパース
                cleaned = str(photos_json_str).replace('\n', ' ').replace('\r', ' ')
                raw = json.loads(cleaned)
                locations = []
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    entry: dict = {}
                    if item.get("t"):
                        entry["timestamp"] = item["t"]
                    # loc: iOSが返す位置情報文字列をそのまま保存
                    loc = item.get("loc")
                    if loc not in (None, ""):
                        entry["location"] = str(loc)
                    if entry:
                        locations.append(entry)
                if locations:
                    photo_locations = locations
            except (ValueError, TypeError):
                pass

        # 枚数は photos_json の要素数を優先（ショートカットの count は 0 ダミー可）
        actual_count = len(photo_locations) if photo_locations is not None else count

        cur.execute(
            """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
               VALUES (%s, %s, %s, NULL, %s, %s)
               ON CONFLICT (source_id, original_id) DO UPDATE
                 SET content = EXCLUDED.content, metadata = EXCLUDED.metadata""",
            (
                PHOTO_SOURCE_ID,
                date_str,
                f"写真 {actual_count}枚",
                ts,
                json.dumps(
                    {"type": "photo", "date": date_str, "count": actual_count}
                ),
            ),
        )

        cur.execute(
            """INSERT INTO health_daily (date, photo_count, photo_locations)
               VALUES (%s, %s, %s)
               ON CONFLICT (date) DO UPDATE SET
                   photo_count     = EXCLUDED.photo_count,
                   photo_locations = COALESCE(EXCLUDED.photo_locations, health_daily.photo_locations)""",
            (date_str, actual_count, json.dumps(photo_locations) if photo_locations else None),
        )
        return {"date": date_str, "saved": actual_count}

    photos = data.get("photos", [])
    if not photos:
        return {"dates": [], "saved": 0, "note": "no valid photos"}

    # 日付ごとにグループ化
    jst = timezone(timedelta(hours=9))
    by_date: dict[str, list] = defaultdict(list)
    for photo in photos:
        # ショートカットが辞書をJSON文字列として送ってくる場合に対応
        if isinstance(photo, str):
            try:
                photo = json.loads(photo)
            except (ValueError, TypeError):
                continue
        if not isinstance(photo, dict) or "timestamp" not in photo:
            continue

        ts_raw = str(photo["timestamp"]).strip()
        if not ts_raw:
            continue
        try:
            # 日付のみ（"2026-03-23"）の場合は JST 00:00 として扱う
            if len(ts_raw) == 10:
                ts_raw += "T00:00:00+09:00"
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            continue

        date_str = ts.astimezone(jst).strftime("%Y-%m-%d")
        entry: dict = {"timestamp": ts_raw}
        # lat/lng が空文字でない数値の場合のみ追加
        try:
            lat = photo.get("lat")
            lng = photo.get("lng")
            if lat not in (None, "") and lng not in (None, ""):
                entry["lat"] = float(lat)
                entry["lng"] = float(lng)
        except (ValueError, TypeError):
            pass
        by_date[date_str].append(entry)

    total_saved = 0
    for date_str, photo_list in by_date.items():
        count = len(photo_list)
        first_ts = datetime.fromisoformat(photo_list[0]["timestamp"])

        # logs upsert (写真ソース)
        cur.execute(
            """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
               VALUES (%s, %s, %s, NULL, %s, %s)
               ON CONFLICT (source_id, original_id) DO UPDATE
                 SET content  = EXCLUDED.content,
                     metadata = EXCLUDED.metadata,
                     timestamp = EXCLUDED.timestamp""",
            (
                PHOTO_SOURCE_ID, date_str, f"写真 {count}枚", first_ts,
                json.dumps({"type": "photo", "date": date_str, "count": count}),
            ),
        )

        # health_daily の photo 列だけ更新（行がなければ新規挿入）
        cur.execute(
            """INSERT INTO health_daily (date, photo_count, photo_locations)
               VALUES (%s, %s, %s)
               ON CONFLICT (date) DO UPDATE SET
                   photo_count     = EXCLUDED.photo_count,
                   photo_locations = EXCLUDED.photo_locations""",
            (date_str, count, json.dumps(photo_list)),
        )
        total_saved += count

    return {"dates": sorted(by_date.keys()), "saved": total_saved}


def _format_screen_time_seconds(sec: int) -> str:
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"スクリーンタイム: {h}時間{m}分"
    if m > 0:
        return f"スクリーンタイム: {m}分{s}秒"
    return f"スクリーンタイム: {s}秒"


def _upsert_screen_time(cur, data: dict) -> dict:
    """Jomo 由来の1日スクリーンタイム（秒）を logs と health_daily に保存"""
    date_str = _normalize_calendar_date_jst(data["date"])
    raw = data.get("screen_time_seconds")
    if raw is None:
        raise ValueError("screen_time_seconds が必要です")
    try:
        sec = int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError("screen_time_seconds は整数である必要があります") from e
    if sec < 0 or sec > 86400 * 2:
        raise ValueError("screen_time_seconds が範囲外です（0〜172800 秒まで）")

    source_id = _source_id_by_type(cur, "screen_time")
    content = _format_screen_time_seconds(sec)
    ts = datetime.now(timezone.utc)
    meta = json.dumps(
        {"type": "screen_time", "date": date_str, "screen_time_seconds": sec}
    )

    cur.execute(
        """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
           VALUES (%s, %s, %s, NULL, %s, %s)
           ON CONFLICT (source_id, original_id) DO UPDATE
             SET content   = EXCLUDED.content,
                 metadata  = EXCLUDED.metadata,
                 timestamp = EXCLUDED.timestamp
           RETURNING id""",
        (source_id, date_str, content, ts, meta),
    )
    log_id = cur.fetchone()[0]

    cur.execute(
        """INSERT INTO health_daily (date, screen_time_seconds)
           VALUES (%s, %s)
           ON CONFLICT (date) DO UPDATE SET
               screen_time_seconds = EXCLUDED.screen_time_seconds""",
        (date_str, sec),
    )

    return {"date": date_str, "log_id": log_id, "screen_time_seconds": sec}


# ---- Blueprint ----

ingest_bp = Blueprint("ingest", __name__)


@ingest_bp.route("/api/ingest", methods=["POST"])
def ingest():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON required"}), 400

    # "dates" は "date" の typo として許容
    if "dates" in data and "date" not in data:
        data["date"] = data.pop("dates")

    source = data.get("source")
    if source not in ("health", "photo", "screen_time"):
        return jsonify(
            {"error": "source must be 'health', 'photo', or 'screen_time'"}
        ), 400

    config = load_config()
    conn = get_db_conn(config)
    cur = conn.cursor()
    try:
        if source == "health":
            if "date" not in data:
                return jsonify({"error": "date is required for health source", "received_keys": list(data.keys()), "received_data": data}), 400
            try:
                result = _upsert_health(cur, data)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        elif source == "screen_time":
            if "date" not in data:
                return jsonify(
                    {
                        "error": "date is required for screen_time source",
                        "received_keys": list(data.keys()),
                    }
                ), 400
            try:
                result = _upsert_screen_time(cur, data)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            result = _upsert_photos(cur, data)

        conn.commit()
        return jsonify({"status": "ok", **result}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


@ingest_bp.route("/api/health", methods=["GET"])
def health_check():
    """死活確認用エンドポイント"""
    return jsonify({"status": "ok"}), 200


# ---- スタンドアロン起動 ----

def create_app():
    config = load_config()
    app = Flask(__name__)
    app.secret_key = config["flask"]["secret_key"]
    app.register_blueprint(ingest_bp)
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
