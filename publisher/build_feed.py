"""planet-meta.json / planet-data.json を生成し planet-feed リポジトリへ書き出し・git push。

実行例（リポジトリルート）::

    ./venv/bin/python -m publisher.build_feed --dry-run
    ./venv/bin/python -m publisher.build_feed --no-push
    ./venv/bin/python -m publisher.build_feed
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from summarizer.db import get_conn, load_config

from publisher.feed_db import (
    build_days_payload,
    fetch_plays_by_jst_date,
    fetch_posts_by_jst_date,
    fetch_sources,
    fetch_steps_by_date,
    fetch_timeline,
    fetch_weather_by_date,
    jst_window,
)
from publisher.source_display import apply_source_display_overrides

logger = logging.getLogger(__name__)

DATA_FILES = ("planet-data.json", "planet-meta.json")


def _planet_feed_section() -> dict:
    cfg = load_config()
    raw = cfg.get("planet_feed")
    return raw if isinstance(raw, dict) else {}


def _timeline_collapse_raw(pf: dict) -> tuple[object | None, object]:
    """timeline_collapse_types / min_run（[planet_feed] 直下を優先）。"""
    raw = pf.get("timeline_collapse_types")
    mr = pf.get("timeline_collapse_min_run", 3)
    if raw is not None:
        return raw, mr
    sd = pf.get("source_display")
    if isinstance(sd, dict):
        for sid, sub in sd.items():
            if not isinstance(sub, dict):
                continue
            nested = sub.get("timeline_collapse_types")
            if nested is None:
                continue
            logger.warning(
                "timeline_collapse_* は [planet_feed] 直下に置いてください（"
                "いまは source_display.%s から読み取りました）",
                sid,
            )
            return nested, sub.get("timeline_collapse_min_run", mr)
    return None, mr


def _timeline_collapse_payload(pf: dict) -> dict | None:
    """Neocities TL 連続折りたたみ設定 → planet-meta に載せる。"""
    raw, mr = _timeline_collapse_raw(pf)
    if raw is None:
        return None
    if isinstance(raw, str):
        types = [raw]
    elif isinstance(raw, list):
        types = raw
    else:
        return None
    types = [str(t).strip() for t in types if str(t).strip()]
    if not types:
        return None
    try:
        min_run = int(mr)
    except (TypeError, ValueError):
        min_run = 3
    min_run = max(2, min_run)
    return {"types": types, "min_run": min_run}


def _coerce_push(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def generated_at_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()


def write_json(path: Path, data: dict) -> None:
    # 既存の planet-feed クローンに書くときは親が既に存在する。無闇に mkdir すると
    # repo_path が例の /home/you/... のままのとき /home/you の作成で PermissionError になりうる。
    parent = path.parent
    if not parent.is_dir():
        parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def git_commit_push(repo: Path, do_push: bool) -> None:
    for name in DATA_FILES:
        p = repo / name
        if not p.is_file():
            raise FileNotFoundError(f"git: ファイルが存在しません: {p}")

    subprocess.run(["git", "add", *DATA_FILES], cwd=repo, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if diff.returncode == 0:
        logger.info("git: 変更なし（commit / push スキップ）")
        return

    msg = (
        "Update planet feed ("
        f"{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M')} JST)"
    )
    subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True)
    if do_push:
        subprocess.run(["git", "push"], cwd=repo, check=True)
        logger.info("git: push 完了")
    else:
        logger.info("git: commit のみ（push していません）")


def run(
    *,
    days: int,
    repo: Path,
    dry_run: bool,
    no_git: bool,
    do_push: bool,
) -> int:
    oldest, latest, ts_start, ts_end = jst_window(days)
    gen_at = generated_at_iso()
    pf = _planet_feed_section()

    conn = get_conn()
    cur = conn.cursor()
    try:
        sources = fetch_sources(cur)
        apply_source_display_overrides(sources, pf.get("source_display"))
        timeline = fetch_timeline(cur, ts_start, ts_end)
        posts = fetch_posts_by_jst_date(cur, ts_start, ts_end)
        plays = fetch_plays_by_jst_date(cur, ts_start, ts_end)
        steps = fetch_steps_by_date(cur, oldest, latest)
        weather = fetch_weather_by_date(cur, oldest, latest)
    finally:
        cur.close()
        conn.close()

    days_payload = build_days_payload(oldest, latest, posts, plays, steps, weather)

    planet_data = {
        "generated_at": gen_at,
        "timeline": timeline,
    }
    planet_meta = {
        "generated_at": gen_at,
        "latest_date": latest.isoformat(),
        "oldest_date": oldest.isoformat(),
        "sources": sources,
        "days": days_payload,
    }
    tc = _timeline_collapse_payload(pf)
    if tc:
        planet_meta["timeline_collapse"] = tc

    if dry_run:
        logger.info(
            "dry-run: days=%s window=%s..%s timeline=%s sources=%s timeline_collapse=%s",
            days,
            oldest,
            latest,
            len(timeline),
            len(sources),
            tc,
        )
        return 0

    repo = repo.resolve()
    if not repo.is_dir():
        logger.error(
            "planet-feed のディレクトリがありません: %s\n"
            "先に git clone するか、config/settings.toml の [planet_feed] repo_path を "
            "実在するパスにしてください（settings.toml.example の /home/you/... はプレースホルダです）。",
            repo,
        )
        return 1

    write_json(repo / "planet-data.json", planet_data)
    write_json(repo / "planet-meta.json", planet_meta)
    logger.info("JSON を書き込みました: %s", repo)

    if no_git:
        logger.info("git: --no-push のため add/commit/push は行いません")
        return 0

    try:
        git_commit_push(repo, do_push=do_push)
    except subprocess.CalledProcessError as e:
        logger.error("git 操作に失敗しました: %s", e)
        return e.returncode or 1
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    p = argparse.ArgumentParser(description="planet-feed 用 JSON を生成し git push する")
    p.add_argument("--days", type=int, default=30, help="JST 暦日で直近 N 日（既定 30）")
    p.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="planet-feed リポジトリのパス（未指定時は settings.toml または ~/planet-feed）",
    )
    p.add_argument("--dry-run", action="store_true", help="DB のみ読み、ファイルと git は行わない")
    p.add_argument(
        "--no-push",
        "--write-only",
        action="store_true",
        dest="no_git",
        help="JSON のみ書き、git は一切行わない（add/commit/push なし）",
    )
    p.add_argument(
        "--push",
        action="store_true",
        help="settings.toml で push=false でも push する（commit は変更時のみ）",
    )
    args = p.parse_args(argv)

    pf = _planet_feed_section()
    default_repo = Path.home() / "planet-feed"
    repo = args.repo or Path(pf.get("repo_path") or default_repo).expanduser()

    if args.days < 1:
        logger.error("--days は 1 以上にしてください")
        return 1

    if args.dry_run and args.no_git:
        logger.error("--dry-run と --no-push は同時に指定できません")
        return 1

    cfg_push = _coerce_push(pf.get("push"), True)
    do_push = cfg_push or args.push

    return run(
        days=args.days,
        repo=repo,
        dry_run=args.dry_run,
        no_git=args.no_git,
        do_push=do_push,
    )


if __name__ == "__main__":
    sys.exit(main())
