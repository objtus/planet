"""暦月（`YYYY-MM`）と JST 基準の UTC 時間窓。"""

from calendar import monthrange
from datetime import date, datetime, time, timezone

from summarizer.week_bounds import JST


def parse_year_month(date_str: str) -> tuple[int, int]:
    """`2026-03` または `2026-3` → (year, month)。"""
    s = date_str.strip()
    parts = s.split("-", 1)
    if len(parts) != 2:
        raise ValueError("月の date は YYYY-MM 形式（例: 2026-03）である必要があります")
    try:
        y = int(parts[0])
        mo = int(parts[1])
    except ValueError as e:
        raise ValueError("YYYY-MM の数値が不正です") from e
    if mo < 1 or mo > 12:
        raise ValueError("月は 1–12 である必要があります")
    if y < 1:
        raise ValueError("年が不正です")
    return y, mo


def month_calendar_range(year: int, month: int) -> tuple[date, date]:
    """その月の 1 日と末日（date）。"""
    last_d = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_d)


def month_utc_range(year: int, month: int) -> tuple[datetime, datetime]:
    """JST で当月 1 日 0:00〜翌月 1 日 0:00（排他）を UTC aware datetime に。"""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    start_local = datetime.combine(first, time.min, tzinfo=JST)
    end_local = datetime.combine(next_first, time.min, tzinfo=JST)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def month_label(year: int, month: int, first: date, last: date) -> str:
    return f"{year}年{month}月（{first}〜{last}、JST）"
