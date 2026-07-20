"""Scrapbox 日記を Obsidian デイリーノートへ反映する。

既存ノートが無い場合は、Templater 版テンプレと同じ見出し・フロントマター・DataviewJS を
サーバー側で再現してから作成する（Obsidian 上で Templater を実行する代わり）。

設定: config/settings.toml の [obsidian] / [scrapbox] を参照。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from urllib.parse import quote
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from summarizer.db import get_conn, load_config
from collectors.scrapbox import (
    extract_my_entries_obsidian,
    scrapbox_cosense_page_url,
)

JST = ZoneInfo("Asia/Tokyo")

WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

SCRAPBOX_HEADING = "## Scrapbox（Planet・自動）"
MARK_START = "<!-- planet-scrapbox-start -->"
MARK_END = "<!-- planet-scrapbox-end -->"
SCRAPBOX_FM_KEY = "scrapbox_planet"


@dataclass
class ObsidianConfig:
    vault_path: Path
    daily_dir: str
    daily_template: Path
    weather_city: str
    weather_max_days_back: int


def _load_obsidian_config(raw: dict | None) -> ObsidianConfig | None:
    if not raw:
        return None
    vp = raw.get("vault_path")
    if not vp:
        return None
    vault = Path(vp).expanduser()
    daily_dir = (raw.get("daily_dir") or "20-daily").strip("/")
    tpl = raw.get("daily_template") or "99-templates/dailynote-template.md"
    return ObsidianConfig(
        vault_path=vault,
        daily_dir=daily_dir,
        daily_template=vault / tpl,
        weather_city=(raw.get("weather_city") or "Nagoya").strip(),
        weather_max_days_back=int(raw.get("weather_max_days_back") or 7),
    )


def _weekday_ja(d: date) -> str:
    return WEEKDAYS_JA[d.weekday()]


def _format_scrapbox_block(day: date, body_md: str, project: str) -> str:
    """日付ページへの Cosense リンク行を先頭に付け、本文を続ける。"""
    page_title = day.strftime("%Y/%m/%d")
    url = scrapbox_cosense_page_url(project, page_title)
    head = f"[この日の Cosense ページ]({url})"
    body = (body_md or "").strip()
    return f"{head}\n\n{body}" if body else head


def _fetch_diary_markdown_for_obsidian(
    conn,
    day: date,
    project: str,
    my_icons: list,
) -> str | None:
    """scrapbox_pages の生テキストから自分セクションを Markdown リンク付きで取得。失敗時は content_plain。"""
    page_title = day.strftime("%Y/%m/%d")
    with conn.cursor() as cur:
        cur.execute(
            """SELECT content, content_plain FROM scrapbox_pages
                WHERE project=%s AND page_title=%s""",
            (project, page_title),
        )
        row = cur.fetchone()
    if not row:
        return None
    raw, plain = row[0], row[1]
    plain_st = (plain or "").strip()
    if not plain_st:
        return None
    if raw and str(raw).strip():
        md = extract_my_entries_obsidian(str(raw), my_icons, project)
        if md.strip():
            return _format_scrapbox_block(day, md.strip(), project)
    return _format_scrapbox_block(day, plain_st, project)


def _fetch_wttr_line(city: str, timeout: float = 10.0) -> str:
    url = f"https://wttr.in/{quote(city)}?format=%C+%t"
    try:
        r = requests.get(url, timeout=timeout)
        if r.ok:
            t = (r.text or "").strip()
            return t or "天気情報取得失敗"
        return "天気情報取得失敗"
    except requests.RequestException:
        return "天気情報取得エラー"


def _weather_for_template_day(
    day: date,
    *,
    city: str,
    max_days_back: int,
    today: date,
) -> str:
    if day > today:
        return f"未来の日付のため天気情報なし"
    if (today - day).days > max_days_back:
        return f"過去{max_days_back}日より古い日付のため天気情報なし"
    return _fetch_wttr_line(city)


def _extract_dataview_tail_from_template(template_text: str) -> str:
    idx = template_text.find("```dataviewjs")
    if idx < 0:
        raise ValueError("daily_template に ```dataviewjs ブロックがありません")
    return template_text[idx:].lstrip()


def build_new_daily_note(
    day: date,
    *,
    obs: ObsidianConfig,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(JST)
    today = now.astimezone(JST).date()
    iso = day.isoformat()
    weather = _weather_for_template_day(
        day,
        city=obs.weather_city,
        max_days_back=obs.weather_max_days_back,
        today=today,
    )
    tpl_text = obs.daily_template.read_text(encoding="utf-8")
    tail = _extract_dataview_tail_from_template(tpl_text)
    prev_d = day - timedelta(days=1)
    next_d = day + timedelta(days=1)
    title_line = f"{day.year}年{day.month:02d}月{day.day:02d}日（{_weekday_ja(day)}）"
    stamp = now.strftime("%Y-%m-%d %H:%M")

    frontmatter = f"""---
title: {iso}
date: {stamp}
created: {stamp}
modified: {stamp}
tags: 
- daily/{day.year}/{day.month:02d}/{day.day:02d}
- daily/{day.year}/{day.month:02d}
- daily/{day.year}
- daily
type: daily
aliases:
- {day.year}年{day.month:02d}月{day.day:02d}日
- {day.month}月{day.day}日
weather: 
- {weather}
mood: 
---
# {title_line}
<< [[{obs.daily_dir}/{prev_d.isoformat()}|{prev_d.isoformat()}]] | [[{obs.daily_dir}/{next_d.isoformat()}|{next_d.isoformat()}]] >>
***
## 今日のハイライト
- 
^highlight-{iso}


## タスク
![[todoリスト#ToDoリスト]]


## メモ
- 
^memo-{iso}

---
{tail}
"""
    return frontmatter


_RE_SCRAPBOX = re.compile(
    re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
    re.DOTALL | re.MULTILINE,
)


def inject_or_replace_scrapbox(body: str, diary_plain: str) -> str:
    block_core = f"{MARK_START}\n\n{diary_plain.rstrip()}\n\n{MARK_END}"
    wrapped = f"\n{SCRAPBOX_HEADING}\n{block_core}\n"

    if MARK_START in body and MARK_END in body:
        return _RE_SCRAPBOX.sub(block_core, body, count=1)

    anchor = "\n---\n```dataviewjs"
    idx = body.find(anchor)
    if idx == -1:
        idx = body.find("\r\n---\r\n```dataviewjs")
    if idx >= 0:
        return body[:idx].rstrip() + wrapped + body[idx:]
    return body.rstrip() + "\n" + wrapped


_RE_REMOVE_SCRAPBOX = re.compile(
    r"\r?\n" + re.escape(SCRAPBOX_HEADING) + r"\s*\r?\n"
    + re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\s*",
    re.DOTALL,
)


def remove_scrapbox_section(body: str) -> str:
    body2, n = _RE_REMOVE_SCRAPBOX.subn("", body, count=1)
    if n:
        return body2
    pat2 = re.compile(
        re.escape(SCRAPBOX_HEADING) + r"\s*\r?\n"
        + re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\s*",
        re.DOTALL,
    )
    return pat2.sub("", body, count=1)


def _split_frontmatter(body: str) -> tuple[str | None, str]:
    raw = body.lstrip("\ufeff")
    if not raw.startswith("---"):
        return None, body
    lines = raw.splitlines(keepends=True)
    if not lines:
        return None, body
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "".join(lines[: i + 1])
            rest = "".join(lines[i + 1 :])
            return fm, rest
    return None, body


def merge_scrapbox_frontmatter(body: str, enabled: bool) -> str:
    fm, rest = _split_frontmatter(body)
    if fm is None:
        return body
    lines = fm.splitlines(keepends=True)
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None or close_idx < 1:
        return body
    inner = lines[1:close_idx]
    out_inner: list[str] = []
    saw = False
    for line in inner:
        if re.match(rf"^{re.escape(SCRAPBOX_FM_KEY)}:\s*", line):
            saw = True
            if enabled:
                out_inner.append(f"{SCRAPBOX_FM_KEY}: true\n")
        else:
            out_inner.append(line)
    if enabled and not saw:
        out_inner.append(f"{SCRAPBOX_FM_KEY}: true\n")
    new_fm = lines[0] + "".join(out_inner) + lines[close_idx]
    return new_fm + rest


def daily_note_path(obs: ObsidianConfig, day: date) -> Path:
    return obs.vault_path / obs.daily_dir / f"{day.isoformat()}.md"


def ensure_daily_note(
    day: date,
    obs: ObsidianConfig,
) -> tuple[Path, bool]:
    path = daily_note_path(obs, day)
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    text = build_new_daily_note(day, obs=obs)
    path.write_text(text, encoding="utf-8")
    return path, True


def sync_scrapbox_for_day(day: date, obs: ObsidianConfig) -> tuple[bool, str]:
    if not obs.vault_path.is_dir():
        return False, f"vault_path が存在しません: {obs.vault_path}"
    if not obs.daily_template.is_file():
        return False, f"daily_template が見つかりません: {obs.daily_template}"

    cfg = load_config()
    scrap = cfg.get("scrapbox") or {}
    project = (scrap.get("project") or "stall").strip()
    my_icons = scrap.get("my_icons") or ["health.icon"]

    conn = get_conn()
    try:
        diary = _fetch_diary_markdown_for_obsidian(conn, day, project, my_icons)
    finally:
        conn.close()

    path = daily_note_path(obs, day)

    if diary:
        path, created = ensure_daily_note(day, obs)
        body = path.read_text(encoding="utf-8")
        new_body = inject_or_replace_scrapbox(body, diary)
        new_body = merge_scrapbox_frontmatter(new_body, True)
        if new_body != body:
            path.write_text(new_body, encoding="utf-8")
        action = "新規作成" if created else "更新"
        return True, f"{day}: {action} → {path}"

    if not path.exists():
        return True, f"{day}: DB なし・ノートなし（スキップ）"

    body = path.read_text(encoding="utf-8")
    if MARK_START not in body or MARK_END not in body:
        return True, f"{day}: DB なし・Planet ブロックなし（スキップ）"

    new_body = remove_scrapbox_section(body)
    new_body = merge_scrapbox_frontmatter(new_body, False)
    if new_body != body:
        path.write_text(new_body, encoding="utf-8")
        return True, f"{day}: Planet ブロック削除 → {path}"
    return True, f"{day}: 変更なし"


def sync_recent_to_obsidian(lookback_days: int) -> tuple[bool, list[str]]:
    """今日（JST）を含む過去 lookback_days 暦日について、DB と vault を揃える。"""
    cfg = load_config()
    obs_raw = cfg.get("obsidian")
    obs = _load_obsidian_config(obs_raw if isinstance(obs_raw, dict) else None)
    if not obs:
        return False, ["[obsidian] が settings.toml に無いか vault_path がありません。"]
    n = max(1, int(lookback_days))
    msgs: list[str] = []
    ok = True
    today = datetime.now(JST).date()
    for i in range(n):
        day = today - timedelta(days=i)
        o, msg = sync_scrapbox_for_day(day, obs)
        msgs.append(msg)
        if not o:
            ok = False
    return ok, msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrapbox 日記を Obsidian デイリーノートへ")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--date",
        dest="day",
        type=lambda s: date.fromisoformat(s),
        help="対象日 YYYY-MM-DD（JST の暦日）",
    )
    g.add_argument(
        "--recent",
        action="store_true",
        help="今日から N 暦日ぶん一括同期（N は --lookback-days または [scrapbox].lookback_days）",
    )
    ap.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        metavar="N",
        help="--recent のときの暦日窓（省略時は settings [scrapbox].lookback_days）",
    )
    args = ap.parse_args(argv)

    cfg = load_config()
    obs_raw = cfg.get("obsidian")
    obs = _load_obsidian_config(obs_raw if isinstance(obs_raw, dict) else None)
    if not obs:
        print(
            "[obsidian] が settings.toml に無いか vault_path がありません。",
            file=sys.stderr,
        )
        return 1

    if args.day is not None:
        ok, msg = sync_scrapbox_for_day(args.day, obs)
        print(msg)
        return 0 if ok else 1

    scrap = cfg.get("scrapbox") or {}
    lb = args.lookback_days
    if lb is None:
        lb = int(scrap.get("lookback_days", 30))
    ok, msgs = sync_recent_to_obsidian(lb)
    for m in msgs:
        print(m)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
