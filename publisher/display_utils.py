"""ダッシュボード [dashboard/app.py] / [calendar.js] と整合する表示用ヘルパ（Flask 非依存）。"""

from __future__ import annotations

import re

# app.py の SHORT_NAME_MAP と同じ
SHORT_NAME_MAP = {
    "misskey.io": "msk.io",
    "tanoshii.site": "tanoshii",
    "sushi.ski": "sushi.ski",
    "mistodon.cloud": "mistodon",
    "mastodon.cloud": "masto.cloud",
    "msk.ilnk.info": "ilnk",
    "pon.icu": "pon.icu",
    "groundpolis.app": "g.app",
    "yuinoid.neocities.org": "100%health",
}

DOMAIN_TO_FAVICON = {
    "misskey.io": "misskeyio.webp",
    "tanoshii.site": "tanoshii.webp",
    "sushi.ski": "sushi.webp",
    "mistodon.cloud": "mistodon.webp",
    "mastodon.cloud": "mastocloud.webp",
    "msk.ilnk.info": "ilnk.webp",
    "pon.icu": "pon.webp",
    "groundpolis.app": "groundpolis.webp",
    "yuinoid.neocities.org": "neocities.webp",
}


def _domain_from_base_url(base_url: str | None) -> str:
    if not base_url:
        return ""
    return base_url.replace("https://", "").replace("http://", "").rstrip("/")


def auto_short_name(stype: str, base_url: str | None, name: str) -> str:
    domain = _domain_from_base_url(base_url)
    fixed = {
        "lastfm": "last.fm",
        "health": "health",
        "photo": "photo",
        "screen_time": "jomo",
        "weather": "weather",
        "github": "github",
        "youtube": "youtube",
        "scrapbox": "scrapbox",
        "netflix": "netflix",
        "prime": "prime",
    }
    return fixed.get(stype) or SHORT_NAME_MAP.get(domain) or domain or name


def favicon_filename(
    stype: str,
    base_url: str | None,
    is_active: bool,
    source_id: int,
) -> str:
    """planet-meta.json の favicon キー用（Neocities 上のファイル名・拡張子込み）。

    既定は .webp。Neocities 側に .svg / .png だけ置く場合は、クライアント
    (planet-app.js) が同一ベース名の別拡張子を順に試す。完全に一致させるなら
    ここを .svg に変更して build_feed し直す。
    """
    if not is_active:
        return f"src{source_id}.webp"
    domain = _domain_from_base_url(base_url)
    if domain in DOMAIN_TO_FAVICON:
        return DOMAIN_TO_FAVICON[domain]
    if stype == "lastfm":
        return "lastfm.webp"
    if stype == "github":
        return "github.webp"
    if stype == "youtube":
        return "youtube.webp"
    if stype == "scrapbox":
        return "scrapbox.webp"
    if stype == "netflix":
        return "netflix.webp"
    if stype == "prime":
        return "prime.webp"
    if stype == "rss":
        return f"rss_{source_id}.webp"
    if stype == "health":
        return "health.webp"
    if stype == "photo":
        return "photo.webp"
    if stype == "screen_time":
        return "screen_time.webp"
    if stype == "weather":
        return "weather.webp"
    return f"{stype}_{source_id}.webp"


def source_row_to_feed_meta(row: tuple) -> dict:
    """data_sources 1行 -> planet-meta の sources[] 要素。

    row: (id, name, type, base_url, account, is_active, sort_order, short_name)
    """
    sid = row[0]
    name = row[1]
    stype = row[2]
    base_url = row[3]
    is_active = row[5]
    db_short = row[7] if len(row) > 7 else None
    short_name = db_short or auto_short_name(stype, base_url, name)
    return {
        "id": sid,
        "name": name,
        "short_name": short_name,
        "type": stype,
        "favicon": favicon_filename(stype, base_url, is_active, sid),
    }


def weather_emoji(main: str | None, desc: str | None) -> str:
    """[dashboard/static/js/calendar.js] weatherEmoji の Python 移植。"""
    d = desc or ""
    if re.search(r"激しい雷雨|雷雨", d):
        return "⛈"
    if "雹" in d:
        return "⛈"
    if re.search(r"雪|霰|小雪|大雪", d):
        return "❄️"
    if re.search(r"雨|小雨|強い雨|にわか|霧雨|着氷性の雨", d):
        return "🌧"
    if re.search(r"霧|着氷霧", d):
        return "🌫"
    if re.search(r"快晴|ほぼ晴れ", d):
        return "☀️"
    if re.search(r"晴れ時々曇り|時々曇", d):
        return "🌤"
    if re.search(r"曇り|くもり|薄い雲|曇がち|雲", d) and "晴" not in d:
        return "☁️"

    m = str(main or "").lower()
    if m == "thunderstorm":
        return "⛈"
    if m == "drizzle":
        return "🌦"
    if m == "rain":
        return "🌧"
    if m == "snow":
        return "❄️"
    if m in ("mist", "fog", "haze", "smoke", "dust", "sand", "ash", "squall"):
        return "🌫"
    if m == "tornado":
        return "🌪"
    if m == "clear":
        return "☀️"
    if m == "clouds":
        return "☁️"

    low = d.lower()
    if re.search(r"thunder|storm", low):
        return "⛈"
    if "drizzle" in low:
        return "🌦"
    if re.search(r"rain|shower", low):
        return "🌧"
    if "snow" in low:
        return "❄️"
    if re.search(r"fog|mist|haze", low):
        return "🌫"
    if "clear" in low:
        return "☀️"
    if "cloud" in low:
        return "☁️"

    return "🌡"
