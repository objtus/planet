"""iPhone からのデータ受け取り Flask API (Phase 4)"""

import json
import tomllib
import psycopg2
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, Blueprint, request, jsonify

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"

HEALTH_SOURCE_ID = 9
PHOTO_SOURCE_ID = 10


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_db_conn(config):
    db = config["database"]
    return psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )


def _upsert_health(cur, data: dict) -> dict:
    """ヘルスデータを logs と health_daily にupsert"""
    date_str = data["date"]

    def _int(v):
        return round(v) if v is not None else None

    steps            = _int(data.get("steps"))
    active_calories  = _int(data.get("active_calories"))
    heart_rate_avg   = _int(data.get("heart_rate_avg"))
    heart_rate_max   = _int(data.get("heart_rate_max"))
    heart_rate_min   = _int(data.get("heart_rate_min"))
    exercise_minutes = _int(data.get("exercise_minutes"))
    stand_hours      = _int(data.get("stand_hours"))

    # logs.content 生成
    parts = []
    if steps           is not None: parts.append(f"歩数: {steps:,}歩")
    if active_calories is not None: parts.append(f"消費カロリー: {active_calories}kcal")
    if heart_rate_avg  is not None: parts.append(f"心拍数: {heart_rate_avg}bpm")
    if exercise_minutes is not None: parts.append(f"運動: {exercise_minutes}分")
    if stand_hours     is not None: parts.append(f"スタンド: {stand_hours}時間")
    content = " / ".join(parts)

    # timestamp: 実際の受信時刻（UTC）を使用
    ts = datetime.now(timezone.utc)

    # logs upsert (同じ日付のエントリがあれば上書き)
    cur.execute(
        """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
           VALUES (%s, %s, %s, NULL, %s, %s)
           ON CONFLICT (source_id, original_id) DO UPDATE
             SET content  = EXCLUDED.content,
                 metadata = EXCLUDED.metadata,
                 timestamp = EXCLUDED.timestamp
           RETURNING id""",
        (
            HEALTH_SOURCE_ID, date_str, content, ts,
            json.dumps({"type": "health", "date": date_str}),
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

    return {"date": date_str, "log_id": log_id}


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

        cur.execute(
            """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
               VALUES (%s, %s, %s, NULL, %s, %s)
               ON CONFLICT (source_id, original_id) DO UPDATE
                 SET content = EXCLUDED.content, metadata = EXCLUDED.metadata""",
            (PHOTO_SOURCE_ID, date_str, f"写真 {count}枚", ts,
             json.dumps({"type": "photo", "date": date_str, "count": count})),
        )
        # 枚数は photos_json の要素数で上書き可能
        actual_count = len(photo_locations) if photo_locations is not None else count

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
    if source not in ("health", "photo"):
        return jsonify({"error": "source must be 'health' or 'photo'"}), 400

    config = load_config()
    conn = get_db_conn(config)
    cur = conn.cursor()
    try:
        if source == "health":
            if "date" not in data:
                return jsonify({"error": "date is required for health source", "received_keys": list(data.keys()), "received_data": data}), 400
            result = _upsert_health(cur, data)
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
