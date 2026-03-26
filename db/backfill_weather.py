"""
Open-Meteo Archive API を使って過去の天気データをバックフィルするスクリプト。
APIキー不要・完全無料。

実行: python db/backfill_weather.py
"""

import sys
import tomllib
import datetime
import time
import requests
import psycopg2
from pathlib import Path

ROOT = Path(__file__).parent.parent

with open(ROOT / "config" / "settings.toml", "rb") as f:
    config = tomllib.load(f)

db  = config["database"]
owm = config["openweathermap"]

SOURCE_ID = owm["source_id"]  # 7
LAT       = owm["lat"]         # 35.1815 (Nagoya)
LON       = owm["lon"]         # 136.9066
LOCATION  = owm.get("location", "Nagoya")

# WMO 天気コード → (main, description_ja)
WMO_MAP = {
    0:  ("Clear",        "快晴"),
    1:  ("Clear",        "ほぼ晴れ"),
    2:  ("Clouds",       "晴れ時々曇り"),
    3:  ("Clouds",       "曇り"),
    45: ("Fog",          "霧"),
    48: ("Fog",          "着氷霧"),
    51: ("Drizzle",      "小雨"),
    53: ("Drizzle",      "霧雨"),
    55: ("Drizzle",      "強い霧雨"),
    56: ("Drizzle",      "着氷性霧雨"),
    57: ("Drizzle",      "強い着氷性霧雨"),
    61: ("Rain",         "小雨"),
    63: ("Rain",         "雨"),
    65: ("Rain",         "強い雨"),
    66: ("Rain",         "着氷性の雨"),
    67: ("Rain",         "強い着氷性の雨"),
    71: ("Snow",         "小雪"),
    73: ("Snow",         "雪"),
    75: ("Snow",         "大雪"),
    77: ("Snow",         "霰"),
    80: ("Rain",         "にわか雨"),
    81: ("Rain",         "強いにわか雨"),
    82: ("Rain",         "激しいにわか雨"),
    85: ("Snow",         "にわか雪"),
    86: ("Snow",         "強いにわか雪"),
    95: ("Thunderstorm", "雷雨"),
    96: ("Thunderstorm", "雷雨（雹）"),
    99: ("Thunderstorm", "激しい雷雨（雹）"),
}

def wmo_to_desc(code):
    return WMO_MAP.get(code, ("Unknown", f"コード{code}"))


def fetch_open_meteo(start_date: str, end_date: str) -> dict:
    url = "https://archive-api.open-meteo.com/v1/archive"
    resp = requests.get(url, params={
        "latitude":  LAT,
        "longitude": LON,
        "start_date": start_date,
        "end_date":   end_date,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "weathercode",
            "relative_humidity_2m_mean",
        ]),
        "timezone": "Asia/Tokyo",
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    conn = psycopg2.connect(
        host=db["host"], port=db["port"], dbname=db["name"],
        user=db["user"], password=db["password"],
    )
    cur = conn.cursor()

    # 既存データの日付セットを取得
    cur.execute("SELECT date FROM weather_daily")
    existing = {r[0] for r in cur.fetchall()}
    print(f"既存レコード: {len(existing)} 件")

    # 対象期間: logs の最古日〜昨日
    cur.execute(
        "SELECT MIN(DATE(timestamp AT TIME ZONE 'Asia/Tokyo')) FROM logs WHERE is_deleted=FALSE"
    )
    start_date = cur.fetchone()[0]
    end_date   = datetime.date.today() - datetime.timedelta(days=1)

    print(f"バックフィル期間: {start_date} 〜 {end_date}")

    # Open-Meteo は一度に複数年取れるが、年単位で分割して進捗表示
    year_start = start_date.year
    year_end   = end_date.year

    inserted = 0
    skipped  = 0

    for year in range(year_start, year_end + 1):
        s = max(start_date, datetime.date(year, 1, 1))
        e = min(end_date,   datetime.date(year, 12, 31))
        if s > e:
            continue

        print(f"\n[{year}] {s} 〜 {e} を取得中…", end=" ", flush=True)

        try:
            data   = fetch_open_meteo(str(s), str(e))
            daily  = data["daily"]
            dates  = daily["time"]
            t_max  = daily["temperature_2m_max"]
            t_min  = daily["temperature_2m_min"]
            t_mean = daily["temperature_2m_mean"]
            codes  = daily["weathercode"]
            humid  = daily["relative_humidity_2m_mean"]
        except Exception as ex:
            print(f"エラー: {ex}")
            continue

        year_ins = 0
        for i, d_str in enumerate(dates):
            d = datetime.date.fromisoformat(d_str)
            if d in existing:
                skipped += 1
                continue
            if t_max[i] is None or t_min[i] is None:
                continue

            code  = int(codes[i]) if codes[i] is not None else 0
            main, desc = wmo_to_desc(code)
            tmax  = round(t_max[i],  1)
            tmin  = round(t_min[i],  1)
            tavg  = round(t_mean[i], 1) if t_mean[i] is not None else round((tmax + tmin) / 2, 1)
            hum   = int(humid[i]) if humid[i] is not None else None

            content   = f"{d} {desc} {tavg}℃ ({tmin}〜{tmax}℃)"
            timestamp = datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)

            # logs テーブルに挿入
            cur.execute("""
                INSERT INTO logs (source_id, content, url, timestamp, metadata, is_deleted)
                VALUES (%s, %s, NULL, %s, %s, FALSE)
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (SOURCE_ID, content, timestamp,
                  psycopg2.extras.Json({"type": "weather", "temp_max": tmax, "temp_min": tmin,
                                        "weather_main": main, "weather_desc": desc})))
            row = cur.fetchone()
            if not row:
                skipped += 1
                continue
            log_id = row[0]

            # weather_daily に挿入
            cur.execute("""
                INSERT INTO weather_daily
                  (log_id, date, temp_max, temp_min, temp_avg, weather_main, weather_desc, humidity, location)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (date) DO NOTHING
            """, (log_id, d, tmax, tmin, tavg, main, desc, hum, LOCATION))

            existing.add(d)
            inserted += 1
            year_ins += 1

        conn.commit()
        print(f"挿入 {year_ins} 件")
        time.sleep(0.3)  # API に負荷をかけない

    cur.close()
    conn.close()
    print(f"\n完了: 挿入 {inserted} 件 / スキップ {skipped} 件")


if __name__ == "__main__":
    import psycopg2.extras  # Json() のために追加インポート
    main()
