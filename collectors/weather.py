"""OpenWeatherMap収集スクリプト（1日1回）"""

import datetime
import requests
from collectors.base import BaseCollector

API_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherCollector(BaseCollector):

    def collect(self):
        cfg = self.config["openweathermap"]
        source_id = cfg["source_id"]
        today = datetime.date.today()

        print(f"[Weather] {today} (source_id={source_id})")

        # 今日のデータが既にあればスキップ
        self.cur.execute("SELECT id FROM weather_daily WHERE date = %s", (today,))
        if self.cur.fetchone():
            print("  本日分取得済み")
            return

        resp = requests.get(
            API_URL,
            params={
                "lat": cfg["lat"],
                "lon": cfg["lon"],
                "appid": cfg["api_key"],
                "units": "metric",
                "lang": "ja",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        main = data["main"]
        weather = data["weather"][0]
        temp_max = round(main["temp_max"], 1)
        temp_min = round(main["temp_min"], 1)
        temp_avg = round((temp_max + temp_min) / 2, 1)
        weather_main = weather["main"]
        weather_desc = weather["description"]
        humidity = main["humidity"]
        location = cfg.get("location", "")

        content = f"{today} {weather_desc} {temp_avg}℃ ({temp_min}〜{temp_max}℃)"
        timestamp = datetime.datetime.combine(today, datetime.time.min, tzinfo=datetime.timezone.utc)

        log_id = self.insert_log(
            source_id, str(today), content, None, timestamp,
            {"type": "weather", "temp_max": temp_max, "temp_min": temp_min,
             "weather_main": weather_main, "weather_desc": weather_desc}
        )
        if log_id:
            self.cur.execute(
                """INSERT INTO weather_daily
                   (log_id, date, temp_max, temp_min, temp_avg, weather_main, weather_desc, humidity, location)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (date) DO NOTHING""",
                (log_id, today, temp_max, temp_min, temp_avg,
                 weather_main, weather_desc, humidity, location)
            )
            self.commit()
            print(f"  挿入: {content}")
        else:
            print("  重複スキップ")


if __name__ == "__main__":
    c = WeatherCollector()
    try:
        c.collect()
    finally:
        c.close()
