"""
週次サマリーを生成して summaries に保存する CLI。

リポジトリルートで（**venv の Python を使う**。システムの python3 には psycopg2 が無いことが多い）:
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12

`config/settings.toml` に `[ollama]`（`base_url`, `model`）と `[database]` が必要。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from summarizer.context import fetch_activity_digest
from summarizer.db import get_conn, load_config
from summarizer.ollama_client import generate_text
from summarizer.week_bounds import parse_iso_week_date, week_label, week_utc_range


def _load_weekly_template() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "weekly_hybrid.txt"
    return path.read_text(encoding="utf-8")


def _build_prompt(template: str, *, week_label_text: str, digest: str) -> str:
    return (
        template.replace("{{WEEK_LABEL}}", week_label_text).replace(
            "{{ACTIVITY_DIGEST}}", digest or "（この週のログはありません）"
        )
    )


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Planet 週次サマリー生成（Ollama）")
    p.add_argument("--period", choices=["week"], default="week", help="M1 では week のみ")
    p.add_argument("--date", required=True, help="ISO 週: YYYY-Www（例: 2026-W12）")
    p.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Ollama リクエストタイムアウト（秒）",
    )
    args = p.parse_args(argv)

    if args.period != "week":
        print("M1 では --period week のみ対応です", file=sys.stderr)
        return 2

    try:
        iso_year, iso_week, monday, sunday = parse_iso_week_date(args.date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    label = week_label(iso_year, iso_week, monday, sunday)
    start_utc, end_utc = week_utc_range(monday)

    cfg = load_config()
    ollama_cfg = cfg.get("ollama") or {}
    base_url = ollama_cfg.get("base_url")
    model = ollama_cfg.get("model")
    if not base_url or not model:
        print(
            "settings.toml に [ollama] base_url と model が必要です",
            file=sys.stderr,
        )
        return 2

    conn = get_conn()
    try:
        digest = fetch_activity_digest(conn, start_utc, end_utc)
        if not digest.strip():
            # 方針 (A): ログなし週はスキップ（ダッシュボードは「まだありません」のまま）
            print(
                f"ログが 0 件のためスキップします: {label}",
                file=sys.stderr,
            )
            return 0

        template = _load_weekly_template()
        prompt = _build_prompt(template, week_label_text=label, digest=digest)

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
    finally:
        conn.close()

    print(f"保存しました: weekly {monday} (ISO {iso_year}-W{iso_week:02d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
