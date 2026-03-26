"""ISO 週（`YYYY-Www`）と JST 基準の UTC 時間窓。"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def parse_iso_week_date(date_str: str) -> tuple[int, int, date, date]:
    """`2026-W12` 形式 → (iso_year, iso_week, monday, sunday)。"""
    s = date_str.strip().upper()
    if "-W" not in s:
        raise ValueError("週の date は YYYY-Www 形式（例: 2026-W12）である必要があります")
    y_str, w_str = s.split("-W", 1)
    try:
        y = int(y_str)
        w = int(w_str)
    except ValueError as e:
        raise ValueError("YYYY-Www の数値が不正です") from e
    if w < 1 or w > 53:
        raise ValueError("ISO 週番号は 1–53 の範囲である必要があります")
    try:
        monday = datetime.strptime(f"{y}-{w:02d}-1", "%G-%V-%u").date()
    except ValueError as e:
        raise ValueError(f"無効な ISO 週: {date_str!r}") from e
    sunday = monday + timedelta(days=6)
    return y, w, monday, sunday


def week_utc_range(monday: date) -> tuple[datetime, datetime]:
    """その週を JST で月曜 0:00〜翌週月曜 0:00（排他）として UTC の aware datetime に変換。"""
    start_local = datetime.combine(monday, time.min, tzinfo=JST)
    end_local = start_local + timedelta(days=7)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def week_label(iso_year: int, iso_week: int, monday: date, sunday: date) -> str:
    return f"{iso_year}年第{iso_week}週（{monday}〜{sunday}、JST）"
