"""
週次・月次サマリーを生成して summaries に保存する CLI。

リポジトリルートで（venv の Python を使う）:
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12
  ./venv/bin/python -m summarizer.generate --period month --date 2026-01

  # 階層（既定）: 日次7回+週マージ1回。フラット従来方式は --pipeline flat
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W1 --pipeline flat

  # LLM に渡すプロンプトだけ確認（Ollama・DB 保存なし）
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W1 --dry-run > /tmp/week_prompt.txt
  # 階層+dry-run で各日のプロンプトも見る
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W1 --dry-run --dry-run-daily

  # 週次だけ作り直す（日次は DB にあれば LLM 再実行しない）
  # 日次も全部やり直すときは --regenerate-daily

  # 1 日だけ日次要約を生成（DB に保存。週次マージ時に再利用される）
  ./venv/bin/python -m summarizer.generate --period day --date 2026-01-04

`config/settings.toml` に `[ollama]`（`base_url`, `model`）と `[database]` が必要。
`--dry-run` のときは DB 接続のみ（Ollama 設定は未使用でもよい）。
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from summarizer.context import (
    MAX_LOG_LINES_DAILY,
    MAX_LOG_LINES_MONTHLY,
    MAX_LOG_LINES_WEEKLY,
    fetch_activity_digest,
    fetch_activity_digest_for_day,
    fetch_activity_digest_week_balanced,
)
from summarizer.db import get_conn, load_config
from summarizer.month_bounds import (
    month_calendar_range,
    month_label,
    month_utc_range,
    parse_year_month,
)
from summarizer.ollama_client import generate_text
from summarizer.progress_emit import emit_summary_progress
from summarizer.week_bounds import parse_iso_week_date, week_label, week_utc_range

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_weekly_template() -> str:
    return (_PROMPTS_DIR / "weekly_hybrid.txt").read_text(encoding="utf-8")


def _load_weekly_from_dailies_template() -> str:
    return (_PROMPTS_DIR / "weekly_from_dailies.txt").read_text(encoding="utf-8")


def _load_daily_template() -> str:
    return (_PROMPTS_DIR / "daily_hybrid.txt").read_text(encoding="utf-8")


def _load_monthly_template() -> str:
    return (_PROMPTS_DIR / "monthly_hybrid.txt").read_text(encoding="utf-8")


def _load_monthly_from_weeklies_template() -> str:
    return (_PROMPTS_DIR / "monthly_from_weeklies.txt").read_text(encoding="utf-8")


def _build_weekly_prompt(template: str, *, week_label_text: str, digest: str) -> str:
    return (
        template.replace("{{WEEK_LABEL}}", week_label_text).replace(
            "{{ACTIVITY_DIGEST}}", digest or "（この週のログはありません）"
        )
    )


def _build_daily_prompt(template: str, *, day_label: str, digest: str) -> str:
    return (
        template.replace("{{DAY_LABEL}}", day_label).replace(
            "{{ACTIVITY_DIGEST}}", digest or "（この日のログはありません）"
        )
    )


def _build_weekly_from_dailies_prompt(
    template: str, *, week_label_text: str, daily_summaries: str
) -> str:
    return (
        template.replace("{{WEEK_LABEL}}", week_label_text).replace(
            "{{DAILY_SUMMARIES}}",
            daily_summaries or "（日次要約がありません）",
        )
    )


def _build_monthly_prompt(template: str, *, month_label_text: str, digest: str) -> str:
    return (
        template.replace("{{MONTH_LABEL}}", month_label_text).replace(
            "{{ACTIVITY_DIGEST}}", digest or "（この月のログはありません）"
        )
    )


def _build_monthly_from_weeklies_prompt(
    template: str, *, month_label_text: str, weekly_summaries: str
) -> str:
    return (
        template.replace("{{MONTH_LABEL}}", month_label_text).replace(
            "{{WEEKLY_SUMMARIES}}",
            weekly_summaries or "（週次要約がありません）",
        )
    )


def _fetch_weekly_summaries_intersecting_month(
    conn, first: date, last: date
) -> list[tuple[date, date, int | None, str]]:
    """暦月 [first, last] と期間が重なる週次サマリー行（月曜始まりの period_start でソート）。"""
    sql = """
        SELECT period_start, period_end, week_number, content
          FROM summaries
         WHERE period_type = 'weekly'
           AND period_end >= %s
           AND period_start <= %s
         ORDER BY period_start
    """
    with conn.cursor() as cur:
        cur.execute(sql, (first, last))
        return list(cur.fetchall())


def _format_weekly_summaries_block(
    rows: list[tuple[date, date, int | None, str]],
) -> str:
    parts = []
    for period_start, period_end, _week_number, content in rows:
        iy, iw, _ = period_start.isocalendar()
        head = f"### {iy}年第{iw}週（{period_start}〜{period_end}）"
        parts.append(f"{head}\n\n{content.strip()}\n")
    return "\n".join(parts)


def _stub_daily_summaries_for_dry_run(
    monday: date, sunday: date, digest_by_day: dict[date, str]
) -> str:
    parts = []
    d = monday
    while d <= sunday:
        raw = digest_by_day.get(d, "")
        if not raw.strip():
            parts.append(
                f"### {d}（JST）\n\n"
                "（dry-run: ログ 0 件。実実行ではこの日の日次要約が入ります。）\n"
            )
        else:
            n = raw.count("\n") + 1
            parts.append(
                f"### {d}（JST）\n\n"
                f"（dry-run: 活動ログ抜粋は {n} 行。実実行ではこの日の LLM 要約がここに入ります。）\n"
            )
        d += timedelta(days=1)
    return "\n".join(parts)


def _strip_leading_h1_h2(text: str) -> str:
    """先頭の # / ## 見出し行（連続）を除く。### 以降は触らない。"""
    lines = text.splitlines()
    while lines:
        i = 0
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            return ""
        s = lines[i].lstrip()
        if not re.match(r"^#{1,2}\s+", s):
            return "\n".join(lines[i:])
        lines = lines[i + 1 :]
    return ""


def finalize_weekly_markdown(body: str, week_label_text: str) -> str:
    """週タイトルは常に機械生成（モデルの「○月○日週」等を排除）。"""
    inner = _strip_leading_h1_h2(body.strip())
    header = f"## 週次サマリー（{week_label_text}）"
    if not inner:
        return header
    return f"{header}\n\n{inner}"


def finalize_monthly_markdown(body: str, month_label_text: str) -> str:
    """月タイトルは常に機械生成。"""
    inner = _strip_leading_h1_h2(body.strip())
    header = f"## 月次サマリー（{month_label_text}）"
    if not inner:
        return header
    return f"{header}\n\n{inner}"


def upsert_weekly(
    conn,
    *,
    period_start,
    period_end,
    week_number: int,
    content: str,
    model: str,
    prompt_style: str,
) -> None:
    sql = """
        INSERT INTO summaries (
            period_type, period_start, period_end, week_number,
            content, model, prompt_style
        )
        VALUES ('weekly', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (period_type, period_start)
        DO UPDATE SET
            period_end   = EXCLUDED.period_end,
            week_number  = EXCLUDED.week_number,
            content      = EXCLUDED.content,
            model        = EXCLUDED.model,
            prompt_style = EXCLUDED.prompt_style
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (period_start, period_end, week_number, content, model, prompt_style),
        )
    conn.commit()


def upsert_monthly(
    conn,
    *,
    period_start,
    period_end,
    content: str,
    model: str,
    prompt_style: str,
) -> None:
    sql = """
        INSERT INTO summaries (
            period_type, period_start, period_end, week_number,
            content, model, prompt_style
        )
        VALUES ('monthly', %s, %s, NULL, %s, %s, %s)
        ON CONFLICT (period_type, period_start)
        DO UPDATE SET
            period_end   = EXCLUDED.period_end,
            week_number  = EXCLUDED.week_number,
            content      = EXCLUDED.content,
            model        = EXCLUDED.model,
            prompt_style = EXCLUDED.prompt_style
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (period_start, period_end, content, model, prompt_style),
        )
    conn.commit()


DAILY_PROMPT_STYLE = "hybrid_hierarchical_daily"


def fetch_daily_summary_content(conn, day: date) -> str | None:
    """保存済み日次要約の本文。無ければ None。"""
    sql = """
        SELECT content FROM summaries
         WHERE period_type = 'daily' AND period_start = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (day,))
        row = cur.fetchone()
    if not row or not (row[0] or "").strip():
        return None
    return str(row[0]).strip()


def upsert_daily(
    conn,
    day: date,
    content: str,
    model: str,
    *,
    prompt_style: str = DAILY_PROMPT_STYLE,
) -> None:
    """対象日は JST 暦日。period_end も同一日（時刻は created_at に任せる）。"""
    sql = """
        INSERT INTO summaries (
            period_type, period_start, period_end, week_number,
            content, model, prompt_style
        )
        VALUES ('daily', %s, %s, NULL, %s, %s, %s)
        ON CONFLICT (period_type, period_start)
        DO UPDATE SET
            period_end   = EXCLUDED.period_end,
            content      = EXCLUDED.content,
            model        = EXCLUDED.model,
            prompt_style = EXCLUDED.prompt_style
    """
    with conn.cursor() as cur:
        cur.execute(sql, (day, day, content, model, prompt_style))
    conn.commit()


def delete_daily_summary(conn, day: date) -> None:
    """ログ無し日などで古い日次行を消す。"""
    sql = "DELETE FROM summaries WHERE period_type = 'daily' AND period_start = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (day,))
    conn.commit()


def _ollama_config():
    cfg = load_config()
    ollama_cfg = cfg.get("ollama") or {}
    base_url = ollama_cfg.get("base_url")
    model = ollama_cfg.get("model")
    return base_url, model


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Planet 週・月・日サマリー生成（Ollama）")
    p.add_argument(
        "--period",
        choices=["week", "month", "day"],
        default="week",
        help="week / month / day（day は日次要約のみ 1 回）",
    )
    p.add_argument(
        "--date",
        required=True,
        help="week: YYYY-Www / month: YYYY-MM / day: YYYY-MM-DD",
    )
    p.add_argument(
        "--pipeline",
        choices=["flat", "hierarchical"],
        default="hierarchical",
        help="week・month のみ有効。day は無視される",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Ollama リクエストタイムアウト（秒）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="プロンプト全文を標準出力に出して終了（Ollama 呼び出し・DB 保存なし）",
    )
    p.add_argument(
        "--dry-run-daily",
        action="store_true",
        help="--dry-run かつ週次 hierarchical のとき、7 日分の日次プロンプトも先に出力する",
    )
    p.add_argument(
        "--regenerate-daily",
        action="store_true",
        help="週次 hierarchical 時、日次要約を毎回 LLM で作り直す（既定は DB にあれば再利用）",
    )
    args = p.parse_args(argv)

    if not args.dry_run:
        base_url, model = _ollama_config()
        if not base_url or not model:
            print(
                "settings.toml に [ollama] base_url と model が必要です",
                file=sys.stderr,
            )
            return 2
    else:
        base_url, model = "", ""

    conn = get_conn()
    try:
        if args.period == "day":
            return _run_day(conn, args, base_url, model, dry_run=args.dry_run)
        if args.period == "week":
            return _run_week(conn, args, base_url, model, dry_run=args.dry_run)
        return _run_month(conn, args, base_url, model, dry_run=args.dry_run)
    finally:
        conn.close()


def _run_day(
    conn,
    args,
    base_url: str,
    model: str,
    *,
    dry_run: bool,
) -> int:
    """1 暦日の日次要約のみ生成して summaries に保存（週次 hierarchical で再利用可）。"""
    raw = (args.date or "").strip()
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        print(
            "day の --date は YYYY-MM-DD 形式で指定してください（例: 2026-01-04）",
            file=sys.stderr,
        )
        return 2

    day_label = f"{d.strftime('%Y-%m-%d')}（JST）"
    digest = fetch_activity_digest_for_day(conn, d, max_lines=MAX_LOG_LINES_DAILY)
    if not digest.strip():
        print(f"ログが 0 件のためスキップします: {day_label}", file=sys.stderr)
        return 0

    tmpl = _load_daily_template()
    prompt = _build_daily_prompt(tmpl, day_label=day_label, digest=digest)

    if dry_run:
        print(prompt)
        return 0

    emit_summary_progress(1, 1, phase="daily", label=d.isoformat())

    try:
        out = generate_text(
            base_url, model, prompt, timeout_sec=args.timeout
        )
    except Exception:
        return 1

    if not out or not out.strip():
        print("Ollama から空の応答が返りました", file=sys.stderr)
        return 1

    body = out.strip()
    upsert_daily(conn, d, body, model)
    print(f"保存しました: daily {d.isoformat()}")
    return 0


def _run_week(
    conn, args, base_url: str, model: str, *, dry_run: bool = False
) -> int:
    try:
        iso_year, iso_week, monday, sunday = parse_iso_week_date(args.date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    label = week_label(iso_year, iso_week, monday, sunday)

    if args.pipeline == "flat":
        return _run_week_flat(
            conn,
            args,
            base_url,
            model,
            iso_year,
            iso_week,
            monday,
            sunday,
            label,
            dry_run=dry_run,
        )
    return _run_week_hierarchical(
        conn,
        args,
        base_url,
        model,
        iso_year,
        iso_week,
        monday,
        sunday,
        label,
        dry_run=dry_run,
    )


def _run_week_flat(
    conn,
    args,
    base_url: str,
    model: str,
    iso_year: int,
    iso_week: int,
    monday: date,
    sunday: date,
    label: str,
    *,
    dry_run: bool,
) -> int:
    start_utc, end_utc = week_utc_range(monday)

    digest = fetch_activity_digest_week_balanced(
        conn, start_utc, end_utc, monday, sunday, max_total=MAX_LOG_LINES_WEEKLY
    )
    if not digest.strip():
        print(f"ログが 0 件のためスキップします: {label}", file=sys.stderr)
        return 0

    per_day = max(1, MAX_LOG_LINES_WEEKLY // 7)
    digest = (
        f"※ 抽出ルール: JST の各日（月〜日）あたり最大 {per_day} 件までを取り、"
        "週全体を時系列（古い→新しい）に並べています。特定の日だけに偏って要約しないでください。\n\n"
        + digest
    )

    template = _load_weekly_template()
    prompt = _build_weekly_prompt(template, week_label_text=label, digest=digest)

    if dry_run:
        print(prompt)
        return 0

    emit_summary_progress(1, 1, phase="weekly_flat", label=label)

    try:
        summary_text = generate_text(
            base_url, model, prompt, timeout_sec=args.timeout
        )
    except Exception:
        return 1

    if not summary_text:
        print("Ollama から空の応答が返りました", file=sys.stderr)
        return 1

    summary_text = finalize_weekly_markdown(summary_text, label)

    upsert_weekly(
        conn,
        period_start=monday,
        period_end=sunday,
        week_number=iso_week,
        content=summary_text,
        model=model,
        prompt_style="hybrid",
    )

    print(f"保存しました: weekly {monday} (ISO {iso_year}-W{iso_week:02d}) [flat]")
    return 0


def _run_week_hierarchical(
    conn,
    args,
    base_url: str,
    model: str,
    iso_year: int,
    iso_week: int,
    monday: date,
    sunday: date,
    label: str,
    *,
    dry_run: bool,
) -> int:
    digest_by_day: dict[date, str] = {}
    d = monday
    while d <= sunday:
        digest_by_day[d] = fetch_activity_digest_for_day(
            conn, d, max_lines=MAX_LOG_LINES_DAILY
        )
        d += timedelta(days=1)

    if not any(s.strip() for s in digest_by_day.values()):
        print(f"ログが 0 件のためスキップします: {label}", file=sys.stderr)
        return 0

    daily_tmpl = _load_daily_template()
    merge_tmpl = _load_weekly_from_dailies_template()

    if dry_run:
        if args.dry_run_daily:
            d = monday
            while d <= sunday:
                dig = digest_by_day[d]
                day_label = f"{d.strftime('%Y-%m-%d')}（JST）"
                dp = _build_daily_prompt(
                    daily_tmpl, day_label=day_label, digest=dig
                )
                print(f"===== 日次プロンプト {day_label} =====\n{dp}\n")
                d += timedelta(days=1)
        stub = _stub_daily_summaries_for_dry_run(monday, sunday, digest_by_day)
        merge_prompt = _build_weekly_from_dailies_prompt(
            merge_tmpl, week_label_text=label, daily_summaries=stub
        )
        print(
            "===== 週次マージプロンプト（日次要約は dry-run プレースホルダ） =====\n"
            f"{merge_prompt}"
        )
        return 0

    t0 = time.perf_counter()
    daily_blocks: list[str] = []
    d = monday
    total_steps = 8
    step = 0
    while d <= sunday:
        step += 1
        dig = digest_by_day[d]
        day_label = f"{d.strftime('%Y-%m-%d')}（JST）"
        day_iso = d.isoformat()
        if not dig.strip():
            delete_daily_summary(conn, d)
            emit_summary_progress(
                step, total_steps, phase="daily_skip", label=day_iso
            )
            body = "（この日のログはありません）"
            daily_blocks.append(f"### {day_label}\n\n{body}\n")
            d += timedelta(days=1)
            continue

        cached = (
            None
            if getattr(args, "regenerate_daily", False)
            else fetch_daily_summary_content(conn, d)
        )
        if cached:
            emit_summary_progress(
                step, total_steps, phase="daily_reuse", label=day_iso
            )
            daily_out = cached
        else:
            emit_summary_progress(step, total_steps, phase="daily", label=day_iso)
            daily_prompt = _build_daily_prompt(
                daily_tmpl, day_label=day_label, digest=dig
            )
            try:
                daily_out = generate_text(
                    base_url, model, daily_prompt, timeout_sec=args.timeout
                )
            except Exception:
                print(
                    f"警告: {day_label} の日次要約で Ollama エラー（プレースホルダで続行）",
                    file=sys.stderr,
                )
                daily_out = "（この日の要約の生成に失敗しました。）"
            if not daily_out:
                print(
                    f"警告: {day_label} の日次要約が空でした（プレースホルダで続行）",
                    file=sys.stderr,
                )
                daily_out = "（この日の要約が空でした。）"
            else:
                body_to_store = daily_out.strip()
                if not body_to_store.startswith("（この日の要約"):
                    upsert_daily(conn, d, body_to_store, model)

        daily_blocks.append(f"### {day_label}\n\n{daily_out.strip()}\n")
        d += timedelta(days=1)

    merge_body = "\n".join(daily_blocks)
    merge_prompt = _build_weekly_from_dailies_prompt(
        merge_tmpl, week_label_text=label, daily_summaries=merge_body
    )

    emit_summary_progress(total_steps, total_steps, phase="weekly_merge")

    try:
        summary_text = generate_text(
            base_url, model, merge_prompt, timeout_sec=args.timeout
        )
    except Exception:
        return 1

    if not summary_text:
        print("Ollama から空の応答が返りました（週次マージ）", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print(
        f"hierarchical 週次: 日次7回+マージ1回 完了 ({elapsed:.1f}s)",
        file=sys.stderr,
    )

    summary_text = finalize_weekly_markdown(summary_text, label)

    upsert_weekly(
        conn,
        period_start=monday,
        period_end=sunday,
        week_number=iso_week,
        content=summary_text,
        model=model,
        prompt_style="hybrid_hierarchical",
    )

    print(f"保存しました: weekly {monday} (ISO {iso_year}-W{iso_week:02d}) [hierarchical]")
    return 0


def _run_month(
    conn, args, base_url: str, model: str, *, dry_run: bool = False
) -> int:
    try:
        year, month = parse_year_month(args.date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    first, last = month_calendar_range(year, month)
    label = month_label(year, month, first, last)

    if args.pipeline == "hierarchical":
        return _run_month_hierarchical(
            conn, args, base_url, model, year, month, first, last, label, dry_run=dry_run
        )
    return _run_month_flat(
        conn, args, base_url, model, year, month, first, last, label, dry_run=dry_run
    )


def _run_month_flat(
    conn,
    args,
    base_url: str,
    model: str,
    year: int,
    month: int,
    first: date,
    last: date,
    label: str,
    *,
    dry_run: bool,
) -> int:
    start_utc, end_utc = month_utc_range(year, month)

    digest = fetch_activity_digest(
        conn,
        start_utc,
        end_utc,
        max_lines=MAX_LOG_LINES_MONTHLY,
    )
    if not digest.strip():
        print(f"ログが 0 件のためスキップします: {label}", file=sys.stderr)
        return 0

    template = _load_monthly_template()
    prompt = _build_monthly_prompt(template, month_label_text=label, digest=digest)

    if dry_run:
        print(prompt)
        return 0

    emit_summary_progress(1, 1, phase="monthly_flat", label=label)

    try:
        summary_text = generate_text(
            base_url, model, prompt, timeout_sec=args.timeout
        )
    except Exception:
        return 1

    if not summary_text:
        print("Ollama から空の応答が返りました", file=sys.stderr)
        return 1

    summary_text = finalize_monthly_markdown(summary_text, label)

    upsert_monthly(
        conn,
        period_start=first,
        period_end=last,
        content=summary_text,
        model=model,
        prompt_style="hybrid",
    )

    print(f"保存しました: monthly {first}（{year}-{month:02d}） [flat]")
    return 0


def _run_month_hierarchical(
    conn,
    args,
    base_url: str,
    model: str,
    year: int,
    month: int,
    first: date,
    last: date,
    label: str,
    *,
    dry_run: bool,
) -> int:
    rows = _fetch_weekly_summaries_intersecting_month(conn, first, last)
    if not rows:
        print(
            "週次要約が 1 件も無いため、月次はフラット（生ログ一括）にフォールバックします",
            file=sys.stderr,
        )
        return _run_month_flat(
            conn, args, base_url, model, year, month, first, last, label, dry_run=dry_run
        )

    block = _format_weekly_summaries_block(rows)
    template = _load_monthly_from_weeklies_template()
    prompt = _build_monthly_from_weeklies_prompt(
        template, month_label_text=label, weekly_summaries=block
    )

    if dry_run:
        print(prompt)
        return 0

    emit_summary_progress(
        1,
        1,
        phase="monthly_from_weeklies",
        label=label,
        num_weeks=len(rows),
    )

    try:
        summary_text = generate_text(
            base_url, model, prompt, timeout_sec=args.timeout
        )
    except Exception:
        return 1

    if not summary_text:
        print("Ollama から空の応答が返りました", file=sys.stderr)
        return 1

    summary_text = finalize_monthly_markdown(summary_text, label)

    upsert_monthly(
        conn,
        period_start=first,
        period_end=last,
        content=summary_text,
        model=model,
        prompt_style="hybrid_hierarchical",
    )

    print(
        f"保存しました: monthly {first}（{year}-{month:02d}） "
        f"[hierarchical, {len(rows)} 週分]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
