"""
週次・月次サマリーを生成して summaries に保存する CLI。

リポジトリルートで（venv の Python を使う）:
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12
  ./venv/bin/python -m summarizer.generate --period month --date 2026-01

  # 新パイプライン（既定）: トピック別独立生成 → 統合
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12

  # 旧パイプライン（--legacy）: 階層（日次7回+週マージ）または フラット
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12 --legacy
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W12 --legacy --pipeline flat

  # LLM に渡すプロンプトだけ確認（Ollama・DB 保存なし）
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W1 --dry-run > /tmp/week_prompt.txt
  # 旧パイプライン+dry-run で各日のプロンプトも見る
  ./venv/bin/python -m summarizer.generate --period week --date 2026-W1 --legacy --dry-run --dry-run-daily

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
    TOPIC_SOURCE_TYPES,
    fetch_activity_digest,
    fetch_activity_digest_for_day,
    fetch_activity_digest_week_balanced,
    fetch_lastfm_digest_for_day,
    fetch_scrapbox_diary,
    fetch_topic_digest_for_day,
    fetch_topic_digest_for_week,
    get_source_name_map,
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

# 新パイプラインの summary_type 一覧（生成順）
DAILY_TOPICS = ["music", "media", "health", "sns", "dev"]
ALL_TOPIC_TYPES = ["music", "media", "health", "sns", "dev", "behavior", "full", "oneword"]

# トピック名→日本語ラベル（プロンプト内 {{TOPIC_LABEL}} 置換用）
TOPIC_LABELS: dict[str, str] = {
    "music":    "音楽",
    "media":    "メディア視聴",
    "health":   "健康・活動",
    "sns":      "SNS・投稿",
    "dev":      "開発",
    "behavior": "行動推測",
    "full":     "全体",
    "oneword":  "一言",
    "best_post": "ベスト投稿",
}


def _load_template(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


# ============================================================
# プロンプトビルダー（旧パイプライン用）
# ============================================================

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


# ============================================================
# プロンプトビルダー（新パイプライン用）
# ============================================================

def _build_topic_prompt(
    template: str,
    *,
    day_label: str,
    digest: str,
) -> str:
    """日次トピック別プロンプト（daily_music.txt 等）。"""
    return (
        template
        .replace("{{DAY_LABEL}}", day_label)
        .replace("{{ACTIVITY_DIGEST}}", digest or "（記録はありません）")
    )


def _build_topic_summary_prompt(
    template: str,
    *,
    period_label: str,
    topic_label: str,
    input_text: str,
) -> str:
    """週次・月次のトピックまとめ（topic_summary.txt）。"""
    return (
        template
        .replace("{{PERIOD_LABEL}}", period_label)
        .replace("{{TOPIC_LABEL}}", topic_label)
        .replace("{{INPUT_TEXT}}", input_text or "（この期間の記録はありません）")
    )


def _build_period_full_prompt(
    template: str,
    *,
    period_label: str,
    input_text: str,
) -> str:
    """週次・月次の全体統合（period_full.txt）。"""
    return (
        template
        .replace("{{PERIOD_LABEL}}", period_label)
        .replace("{{INPUT_TEXT}}", input_text or "（この期間の記録はありません）")
    )


def _build_oneword_prompt(template: str, *, period_label: str, input_text: str) -> str:
    return (
        template
        .replace("{{PERIOD_LABEL}}", period_label)
        .replace("{{INPUT_TEXT}}", input_text or "（記録はありません）")
    )


def _build_best_post_prompt(template: str, *, period_label: str, input_text: str) -> str:
    return (
        template
        .replace("{{PERIOD_LABEL}}", period_label)
        .replace("{{INPUT_TEXT}}", input_text or "（SNS ログはありません）")
    )


def _compose_best_post(
    conn, llm_out: str, sns_block: str,
    *, base_url: str | None = None, model: str | None = None,
    timeout: int = 120, period_label: str = "",
) -> str:
    """LLM 出力（BEST_ID 形式）を解析し、DB から実際の投稿本文を取得して組み合わせる。

    - REASON がない場合は第2の LLM コールで理由を生成（base_url/model 指定時）。
    - BEST_ID が取得できない場合は llm_out をそのまま返す（フォールバック）。
    """
    import re as _re
    best_id: int | None = None
    reason: str = ""

    # BEST_ID 抽出（"BEST_ID: 123", "BEST_ID:\n123", "BEST_ID 123" などに対応）
    m_id = _re.search(r"BEST_ID\s*[:：]?\s*[\n\r]?\s*(\d+)", llm_out)
    if m_id:
        best_id = int(m_id.group(1))

    # REASON 抽出（REASON: 以降の全テキスト。改行後コンテンツも含む）
    m_reason = _re.split(r"REASON\s*[:：]?\s*[\n\r]?\s*", llm_out, maxsplit=1, flags=_re.IGNORECASE)
    if len(m_reason) > 1:
        reason = m_reason[1].strip()

    if best_id is None:
        # フォールバック: LLM 出力をそのまま保存
        return llm_out

    # DB から実際の投稿本文を取得
    post_content: str | None = None
    with conn.cursor() as cur:
        cur.execute("SELECT content FROM logs WHERE id = %s AND is_deleted = FALSE", (best_id,))
        row = cur.fetchone()
        if row:
            post_content = (row[0] or "").strip()

    if not post_content:
        # ID が見つからない場合、sns_block から該当行を探す
        m2 = _re.search(rf"\[id={best_id} [^\]]+\] \(source \d+\) (.*)", sns_block)
        if m2:
            post_content = m2.group(1).strip()

    if not post_content:
        return llm_out  # 見つからなければ LLM 出力をそのまま

    # REASON がない場合: 第2 LLM コールで理由を生成
    if not reason and base_url and model and post_content:
        reason_prompt = (
            f"あなたは個人のライフログ要約アシスタントです。\n\n"
            f"以下は **{period_label}** のSNS投稿の中から選ばれた「今週のベスト投稿」です。\n\n"
            f"投稿: {post_content}\n\n"
            f"この投稿がなぜ週を代表する印象的な投稿なのか、80〜150字で説明してください。\n"
            f"説明文のみを出力し、前置きや後置きは一切書かないでください。"
        )
        reason_out = _generate_or_skip(base_url, model, reason_prompt, timeout, label="best_post_reason")
        if reason_out:
            reason = reason_out.strip()

    parts = [f"**投稿本文：**\n{post_content}", f"\n**投稿ID：** {best_id}"]
    if reason:
        parts.append(f"\n**選定理由：**\n{reason}")
    return "\n".join(parts)


def _build_daily_full_prompt(
    template: str,
    *,
    day_label: str,
    input_text: str,
) -> str:
    """日次全体統合（daily_full.txt）。"""
    return (
        template
        .replace("{{DAY_LABEL}}", day_label)
        .replace("{{ACTIVITY_DIGEST}}", input_text or "（この日のトピック記録はありません）")
    )


def _build_daily_behavior_prompt(
    template: str,
    *,
    day_label: str,
    input_text: str,
) -> str:
    """日次行動推測（daily_behavior.txt）。"""
    return (
        template
        .replace("{{DAY_LABEL}}", day_label)
        .replace("{{ACTIVITY_DIGEST}}", input_text or "（この日の記録はありません）")
    )


# ============================================================
# 旧パイプライン補助関数
# ============================================================

def _fetch_weekly_summaries_intersecting_month(
    conn, first: date, last: date
) -> list[tuple[date, date, int | None, str]]:
    """暦月 [first, last] と期間が重なる週次 full サマリー行（月曜始まりの period_start でソート）。"""
    sql = """
        SELECT period_start, period_end, week_number, content
          FROM summaries
         WHERE period_type = 'weekly'
           AND summary_type = 'full'
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


# ============================================================
# DB 操作
# ============================================================

def upsert_summary(
    conn,
    *,
    period_type: str,
    period_start: date,
    period_end: date,
    week_number: int | None,
    summary_type: str,
    content: str,
    model: str,
    prompt_style: str,
) -> None:
    """汎用 upsert（summary_type 対応）。"""
    sql = """
        INSERT INTO summaries (
            period_type, period_start, period_end, week_number,
            summary_type, content, model, prompt_style
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT summaries_unique
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
            (period_type, period_start, period_end, week_number,
             summary_type, content, model, prompt_style),
        )
    conn.commit()


def upsert_weekly(
    conn,
    *,
    period_start,
    period_end,
    week_number: int,
    content: str,
    model: str,
    prompt_style: str,
    summary_type: str = "full",
) -> None:
    upsert_summary(
        conn,
        period_type="weekly",
        period_start=period_start,
        period_end=period_end,
        week_number=week_number,
        summary_type=summary_type,
        content=content,
        model=model,
        prompt_style=prompt_style,
    )


def upsert_monthly(
    conn,
    *,
    period_start,
    period_end,
    content: str,
    model: str,
    prompt_style: str,
    summary_type: str = "full",
) -> None:
    upsert_summary(
        conn,
        period_type="monthly",
        period_start=period_start,
        period_end=period_end,
        week_number=None,
        summary_type=summary_type,
        content=content,
        model=model,
        prompt_style=prompt_style,
    )


DAILY_PROMPT_STYLE = "hybrid_hierarchical_daily"


def fetch_daily_summary_content(
    conn, day: date, summary_type: str = "full"
) -> str | None:
    """保存済み日次要約の本文。無ければ None。"""
    sql = """
        SELECT content FROM summaries
         WHERE period_type = 'daily'
           AND period_start = %s
           AND summary_type = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (day, summary_type))
        row = cur.fetchone()
    if not row or not (row[0] or "").strip():
        return None
    return str(row[0]).strip()


def fetch_daily_summary_prompt_style(
    conn, day: date, summary_type: str = "full"
) -> str | None:
    """保存済み日次要約の prompt_style。無ければ None。"""
    sql = """
        SELECT prompt_style FROM summaries
         WHERE period_type = 'daily'
           AND period_start = %s
           AND summary_type = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (day, summary_type))
        row = cur.fetchone()
    return row[0] if row else None


def upsert_daily(
    conn,
    day: date,
    content: str,
    model: str,
    *,
    prompt_style: str = DAILY_PROMPT_STYLE,
    summary_type: str = "full",
) -> None:
    """対象日は JST 暦日。period_end も同一日。"""
    upsert_summary(
        conn,
        period_type="daily",
        period_start=day,
        period_end=day,
        week_number=None,
        summary_type=summary_type,
        content=content,
        model=model,
        prompt_style=prompt_style,
    )


def delete_daily_summaries(conn, day: date) -> None:
    """ログ無し日などで古い日次行をすべて消す。"""
    sql = "DELETE FROM summaries WHERE period_type = 'daily' AND period_start = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (day,))
    conn.commit()


# 旧コードとの互換エイリアス
def delete_daily_summary(conn, day: date) -> None:
    delete_daily_summaries(conn, day)


def _ollama_config():
    cfg = load_config()
    ollama_cfg = cfg.get("ollama") or {}
    base_url = ollama_cfg.get("base_url")
    model = ollama_cfg.get("model")
    return base_url, model


# ============================================================
# 新パイプライン — 日次トピック別生成
# ============================================================

def _generate_or_skip(
    base_url: str,
    model: str,
    prompt: str,
    timeout_sec: float,
    *,
    label: str,
) -> str | None:
    """Ollama を呼び出す。失敗時は None を返す（例外は飲み込む）。"""
    try:
        out = generate_text(base_url, model, prompt, timeout_sec=timeout_sec)
    except Exception as e:
        print(f"警告: {label} の Ollama エラー: {e}", file=sys.stderr)
        return None
    if not out or not out.strip():
        print(f"警告: {label} の応答が空でした", file=sys.stderr)
        return None
    return out.strip()


def _run_day_topics(
    conn,
    args,
    base_url: str,
    model: str,
    day: date,
    *,
    dry_run: bool,
) -> int:
    """新パイプライン: 1 暦日のトピック別生成。"""
    day_label = f"{day.strftime('%Y-%m-%d')}（JST）"
    day_iso = day.isoformat()

    # ① 各トピックの生ログを取得
    # music は lastfm_plays テーブルの構造化データ（artist/track/album）+ SNS 音楽関連投稿
    # その他 SNS ソースを含むトピックはアカウント名マップを使う
    SNS_TYPES = {"sns", "music", "media"}
    source_name_map = get_source_name_map(conn)
    topic_digests: dict[str, str] = {}
    for topic, src_types in TOPIC_SOURCE_TYPES.items():
        if topic == "music":
            # Last.fm は lastfm_plays から構造化取得（YouTube スクロブルの乱れを防ぐ）
            lastfm_part = fetch_lastfm_digest_for_day(conn, day)
            # SNS の音楽関連投稿（misskey/mastodon のみ）
            sns_only_types = [t for t in src_types if t in ("misskey", "mastodon")]
            sns_part = fetch_topic_digest_for_day(
                conn, day, sns_only_types, source_name_map=source_name_map
            ) if sns_only_types else ""
            parts = []
            if lastfm_part:
                parts.append(f"--- Last.fm 再生ログ ---\n{lastfm_part}")
            if sns_part:
                parts.append(f"--- SNS 投稿ログ ---\n{sns_part}")
            topic_digests[topic] = "\n\n".join(parts)
        else:
            use_name_map = source_name_map if topic in SNS_TYPES else None
            topic_digests[topic] = fetch_topic_digest_for_day(
                conn, day, src_types, source_name_map=use_name_map
            )

    has_any = any(d.strip() for d in topic_digests.values())
    # health/sns が無くても Scrapbox 日記があれば続行（full の生成に使うため）
    scrapbox_diary = fetch_scrapbox_diary(conn, day)
    if not has_any and not scrapbox_diary:
        print(f"ログが 0 件のためスキップします: {day_label}", file=sys.stderr)
        return 0

    if dry_run:
        for topic, src_types in TOPIC_SOURCE_TYPES.items():
            tmpl = _load_template(f"daily_{topic}")
            prompt = _build_topic_prompt(tmpl, day_label=day_label, digest=topic_digests[topic])
            print(f"===== 日次トピックプロンプト [{topic}] {day_label} =====\n{prompt}\n")
        return 0

    total_steps = len(DAILY_TOPICS) + 3  # 5 topics (music/media/health/sns/dev) + behavior + full + oneword
    step = 0
    topic_results: dict[str, str] = {}

    # ① トピック別生成（music / health / sns / dev）
    for topic in DAILY_TOPICS:
        step += 1
        digest = topic_digests.get(topic, "")
        emit_summary_progress(step, total_steps, phase=f"topic_{topic}", label=day_iso)

        cached = (
            None if getattr(args, "regenerate_daily", False)
            else fetch_daily_summary_content(conn, day, summary_type=topic)
        )
        if cached:
            emit_summary_progress(step, total_steps, phase=f"topic_{topic}_reuse", label=day_iso)
            topic_results[topic] = cached
            continue

        if not digest.strip():
            topic_results[topic] = ""
            continue

        tmpl = _load_template(f"daily_{topic}")
        prompt = _build_topic_prompt(tmpl, day_label=day_label, digest=digest)
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label=f"{topic} {day_iso}")
        if out:
            upsert_daily(conn, day, out, model, summary_type=topic, prompt_style=f"topic_{topic}")
            topic_results[topic] = out
        else:
            topic_results[topic] = ""

    # ② behavior（①の結果を入力）
    step += 1
    emit_summary_progress(step, total_steps, phase="topic_behavior", label=day_iso)
    behavior_input = "\n\n".join(
        f"### {TOPIC_LABELS[t]}\n{topic_results[t]}"
        for t in DAILY_TOPICS
        if topic_results.get(t, "").strip()
    )
    if behavior_input.strip():
        cached_beh = (
            None if getattr(args, "regenerate_daily", False)
            else fetch_daily_summary_content(conn, day, summary_type="behavior")
        )
        if cached_beh:
            behavior_result = cached_beh
        else:
            beh_tmpl = _load_template("daily_behavior")
            beh_prompt = _build_daily_behavior_prompt(
                beh_tmpl, day_label=day_label, input_text=behavior_input
            )
            behavior_result = _generate_or_skip(
                base_url, model, beh_prompt, args.timeout, label=f"behavior {day_iso}"
            ) or ""
            if behavior_result:
                upsert_daily(conn, day, behavior_result, model,
                             summary_type="behavior", prompt_style="topic_behavior")
    else:
        behavior_result = ""

    # ③ full 統合（①②の結果 + Scrapbox日記 を入力）
    step += 1
    emit_summary_progress(step, total_steps, phase="topic_full", label=day_iso)
    full_input_parts = []
    for t in DAILY_TOPICS:
        if topic_results.get(t, "").strip():
            full_input_parts.append(f"### {TOPIC_LABELS[t]}\n{topic_results[t]}")
    if behavior_result.strip():
        full_input_parts.append(f"### {TOPIC_LABELS['behavior']}\n{behavior_result}")
    if scrapbox_diary:
        full_input_parts.append(f"--- Scrapbox日記 ---\n{scrapbox_diary}")
    full_input = "\n\n".join(full_input_parts)

    cached_full_raw = (
        None if getattr(args, "regenerate_daily", False)
        else fetch_daily_summary_content(conn, day, summary_type="full")
    )
    # 旧パイプライン（hybrid_hierarchical_daily）で生成された full は再生成する
    if cached_full_raw:
        old_style = fetch_daily_summary_prompt_style(conn, day, "full")
        cached_full = None if old_style == DAILY_PROMPT_STYLE else cached_full_raw
    else:
        cached_full = None
    if cached_full:
        full_result = cached_full
    else:
        full_tmpl = _load_template("daily_full")
        full_prompt = _build_daily_full_prompt(full_tmpl, day_label=day_label, input_text=full_input)
        full_result = _generate_or_skip(
            base_url, model, full_prompt, args.timeout, label=f"full {day_iso}"
        ) or ""
        if full_result:
            upsert_daily(conn, day, full_result, model,
                         summary_type="full", prompt_style="topic_full")

    # ④ oneword（③の結果を入力）
    step += 1
    emit_summary_progress(step, total_steps, phase="topic_oneword", label=day_iso)
    if full_result.strip():
        ow_tmpl = _load_template("oneword")
        ow_prompt = _build_oneword_prompt(ow_tmpl, period_label=day_label, input_text=full_result)
        ow_result = _generate_or_skip(
            base_url, model, ow_prompt, args.timeout, label=f"oneword {day_iso}"
        ) or ""
        if ow_result:
            upsert_daily(conn, day, ow_result, model,
                         summary_type="oneword", prompt_style="topic_oneword")

    print(f"保存しました: daily topics {day_iso}")
    return 0


# ============================================================
# 新パイプライン — 週次トピック別生成
# ============================================================

def _collect_daily_topic_summaries(
    conn,
    monday: date,
    sunday: date,
    summary_type: str,
) -> str:
    """月〜日の各日の指定 summary_type を結合して返す。"""
    parts = []
    d = monday
    while d <= sunday:
        content = fetch_daily_summary_content(conn, d, summary_type=summary_type)
        if content:
            parts.append(f"### {d.isoformat()}（JST）\n\n{content}\n")
        d += timedelta(days=1)
    return "\n".join(parts)


def _run_week_topics(
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
    """新パイプライン: 週次トピック別生成。日次の各トピック×7日分を入力とする。"""

    if dry_run:
        print(f"===== 週次トピックパイプライン ({label}) =====")
        print("（dry-run: 実実行では日次トピックサマリー×7を入力に各トピックまとめを生成します）")
        return 0

    # ① 各トピック（7日分の日次結果 → topic_summary）
    topic_weekly: dict[str, str] = {}
    total_topics = len(DAILY_TOPICS) + 1 + 1 + 1 + 1  # 5 topics +behavior +full +oneword +best_post
    step = 0

    topic_tmpl = _load_template("topic_summary")
    for topic in DAILY_TOPICS:
        step += 1
        emit_summary_progress(step, total_topics, phase=f"weekly_topic_{topic}", label=label)
        daily_block = _collect_daily_topic_summaries(conn, monday, sunday, topic)
        if not daily_block.strip():
            topic_weekly[topic] = ""
            continue
        prompt = _build_topic_summary_prompt(
            topic_tmpl,
            period_label=label,
            topic_label=TOPIC_LABELS[topic],
            input_text=daily_block,
        )
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label=f"weekly_{topic}")
        if out:
            upsert_weekly(conn, period_start=monday, period_end=sunday,
                          week_number=iso_week, content=out, model=model,
                          prompt_style=f"topic_{topic}", summary_type=topic)
            topic_weekly[topic] = out
        else:
            topic_weekly[topic] = ""

    # ② behavior（日次 behavior×7 → topic_summary）
    step += 1
    emit_summary_progress(step, total_topics, phase="weekly_topic_behavior", label=label)
    beh_block = _collect_daily_topic_summaries(conn, monday, sunday, "behavior")
    behavior_weekly = ""
    if beh_block.strip():
        prompt = _build_topic_summary_prompt(
            topic_tmpl,
            period_label=label,
            topic_label=TOPIC_LABELS["behavior"],
            input_text=beh_block,
        )
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label="weekly_behavior")
        if out:
            upsert_weekly(conn, period_start=monday, period_end=sunday,
                          week_number=iso_week, content=out, model=model,
                          prompt_style="topic_behavior", summary_type="behavior")
            behavior_weekly = out

    # ③ full 統合
    step += 1
    emit_summary_progress(step, total_topics, phase="weekly_full", label=label)
    full_input_parts = []
    for t in DAILY_TOPICS:
        if topic_weekly.get(t, "").strip():
            full_input_parts.append(f"### {TOPIC_LABELS[t]}\n{topic_weekly[t]}")
    if behavior_weekly.strip():
        full_input_parts.append(f"### {TOPIC_LABELS['behavior']}\n{behavior_weekly}")
    full_input = "\n\n".join(full_input_parts)

    full_result = ""
    if full_input.strip():
        period_tmpl = _load_template("period_full")
        prompt = _build_period_full_prompt(period_tmpl, period_label=label, input_text=full_input)
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label="weekly_full")
        if out:
            body = finalize_weekly_markdown(out, label)
            upsert_weekly(conn, period_start=monday, period_end=sunday,
                          week_number=iso_week, content=body, model=model,
                          prompt_style="topic_full", summary_type="full")
            full_result = body

    # ④ oneword
    step += 1
    emit_summary_progress(step, total_topics, phase="weekly_oneword", label=label)
    if full_result.strip():
        ow_tmpl = _load_template("oneword")
        prompt = _build_oneword_prompt(ow_tmpl, period_label=label, input_text=full_result)
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label="weekly_oneword")
        if out:
            upsert_weekly(conn, period_start=monday, period_end=sunday,
                          week_number=iso_week, content=out, model=model,
                          prompt_style="topic_oneword", summary_type="oneword")

    # ⑤ best_post（週次のみ: LLM に ID だけ選ばせ、本文は DB から取得して組み合わせ）
    step += 1
    emit_summary_progress(step, total_topics, phase="weekly_best_post", label=label)
    source_name_map = get_source_name_map(conn)
    sns_block = fetch_topic_digest_for_week(
        conn, monday, sunday, TOPIC_SOURCE_TYPES["sns"],
        include_id=True, source_name_map=source_name_map,
    )
    if sns_block.strip():
        bp_tmpl = _load_template("best_post")
        prompt = _build_best_post_prompt(bp_tmpl, period_label=label, input_text=sns_block)
        llm_out = _generate_or_skip(base_url, model, prompt, args.timeout, label="weekly_best_post")
        if llm_out:
            # LLM 出力から BEST_ID を抽出し、本文を DB から取得
            # REASON がなかった場合は第2の LLM コールで理由を生成
            bp_content = _compose_best_post(
                conn, llm_out, sns_block,
                base_url=base_url, model=model,
                timeout=args.timeout, period_label=label,
            )
            upsert_weekly(conn, period_start=monday, period_end=sunday,
                          week_number=iso_week, content=bp_content, model=model,
                          prompt_style="topic_best_post", summary_type="best_post")

    print(f"保存しました: weekly topics {monday} (ISO {iso_year}-W{iso_week:02d}) [topic_pipeline]")
    return 0


# ============================================================
# 新パイプライン — 月次トピック別生成
# ============================================================

def _collect_weekly_topic_summaries_for_month(
    conn, first: date, last: date, summary_type: str
) -> str:
    """暦月と重なる週次の指定 summary_type を結合して返す。"""
    sql = """
        SELECT period_start, period_end, week_number, content
          FROM summaries
         WHERE period_type = 'weekly'
           AND summary_type = %s
           AND period_end >= %s
           AND period_start <= %s
         ORDER BY period_start
    """
    with conn.cursor() as cur:
        cur.execute(sql, (summary_type, first, last))
        rows = cur.fetchall()
    parts = []
    for period_start, period_end, wn, content in rows:
        iy, iw, _ = period_start.isocalendar()
        parts.append(f"### {iy}年第{iw}週（{period_start}〜{period_end}）\n\n{content.strip()}\n")
    return "\n".join(parts)


def _run_month_topics(
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
    """新パイプライン: 月次トピック別生成。週次の各トピックを入力とする。"""

    if dry_run:
        print(f"===== 月次トピックパイプライン ({label}) =====")
        print("（dry-run: 実実行では週次トピックサマリーを入力に各月次トピックまとめを生成します）")
        return 0

    topic_monthly: dict[str, str] = {}
    total_topics = len(DAILY_TOPICS) + 1 + 1 + 1  # 5 topics +behavior +full +oneword
    step = 0
    topic_tmpl = _load_template("topic_summary")

    # ① 各トピック（週次トピックサマリー → topic_summary）
    for topic in DAILY_TOPICS:
        step += 1
        emit_summary_progress(step, total_topics, phase=f"monthly_topic_{topic}", label=label)
        weekly_block = _collect_weekly_topic_summaries_for_month(conn, first, last, topic)
        if not weekly_block.strip():
            topic_monthly[topic] = ""
            continue
        prompt = _build_topic_summary_prompt(
            topic_tmpl,
            period_label=label,
            topic_label=TOPIC_LABELS[topic],
            input_text=weekly_block,
        )
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label=f"monthly_{topic}")
        if out:
            upsert_monthly(conn, period_start=first, period_end=last,
                           content=out, model=model,
                           prompt_style=f"topic_{topic}", summary_type=topic)
            topic_monthly[topic] = out
        else:
            topic_monthly[topic] = ""

    # ② behavior
    step += 1
    emit_summary_progress(step, total_topics, phase="monthly_topic_behavior", label=label)
    beh_block = _collect_weekly_topic_summaries_for_month(conn, first, last, "behavior")
    behavior_monthly = ""
    if beh_block.strip():
        prompt = _build_topic_summary_prompt(
            topic_tmpl,
            period_label=label,
            topic_label=TOPIC_LABELS["behavior"],
            input_text=beh_block,
        )
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label="monthly_behavior")
        if out:
            upsert_monthly(conn, period_start=first, period_end=last,
                           content=out, model=model,
                           prompt_style="topic_behavior", summary_type="behavior")
            behavior_monthly = out

    # ③ full 統合
    step += 1
    emit_summary_progress(step, total_topics, phase="monthly_full", label=label)
    full_input_parts = []
    for t in DAILY_TOPICS:
        if topic_monthly.get(t, "").strip():
            full_input_parts.append(f"### {TOPIC_LABELS[t]}\n{topic_monthly[t]}")
    if behavior_monthly.strip():
        full_input_parts.append(f"### {TOPIC_LABELS['behavior']}\n{behavior_monthly}")
    full_input = "\n\n".join(full_input_parts)

    if not full_input.strip():
        # フォールバック: 生ログ一括（旧 flat）
        print("週次トピックが空のためフラットにフォールバックします", file=sys.stderr)
        return _run_month_flat(conn, args, base_url, model, year, month, first, last, label, dry_run=False)

    period_tmpl = _load_template("period_full")
    prompt = _build_period_full_prompt(period_tmpl, period_label=label, input_text=full_input)
    out = _generate_or_skip(base_url, model, prompt, args.timeout, label="monthly_full")
    full_result = ""
    if out:
        body = finalize_monthly_markdown(out, label)
        upsert_monthly(conn, period_start=first, period_end=last,
                       content=body, model=model,
                       prompt_style="topic_full", summary_type="full")
        full_result = body

    # ④ oneword
    step += 1
    emit_summary_progress(step, total_topics, phase="monthly_oneword", label=label)
    if full_result.strip():
        ow_tmpl = _load_template("oneword")
        prompt = _build_oneword_prompt(ow_tmpl, period_label=label, input_text=full_result)
        out = _generate_or_skip(base_url, model, prompt, args.timeout, label="monthly_oneword")
        if out:
            upsert_monthly(conn, period_start=first, period_end=last,
                           content=out, model=model,
                           prompt_style="topic_oneword", summary_type="oneword")

    print(f"保存しました: monthly topics {first}（{year}-{month:02d}） [topic_pipeline]")
    return 0


# ============================================================
# 旧パイプライン（--legacy）
# ============================================================

def _run_day(
    conn,
    args,
    base_url: str,
    model: str,
    *,
    dry_run: bool,
) -> int:
    """旧: 1 暦日の日次要約のみ生成（daily_hybrid.txt）。"""
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

    tmpl = _load_template("daily_hybrid")
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
            conn, args, base_url, model,
            iso_year, iso_week, monday, sunday, label, dry_run=dry_run,
        )
    return _run_week_hierarchical(
        conn, args, base_url, model,
        iso_year, iso_week, monday, sunday, label, dry_run=dry_run,
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

    template = _load_template("weekly_hybrid")
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

    daily_tmpl = _load_template("daily_hybrid")
    merge_tmpl = _load_template("weekly_from_dailies")

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
            delete_daily_summaries(conn, d)
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

    template = _load_template("monthly_hybrid")
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
    template = _load_template("monthly_from_weeklies")
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


# ============================================================
# エントリポイント
# ============================================================

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
        help="--legacy 時のみ有効。week・month の旧パイプライン選択。",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="旧パイプライン（daily_hybrid / weekly_from_dailies / monthly_from_weeklies）を使用する",
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
        help="--dry-run かつ旧週次 hierarchical のとき、7 日分の日次プロンプトも先に出力する",
    )
    p.add_argument(
        "--regenerate-daily",
        action="store_true",
        help="日次要約を毎回 LLM で作り直す（既定は DB にあれば再利用）",
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
            if args.legacy:
                return _run_day(conn, args, base_url, model, dry_run=args.dry_run)
            # 新パイプライン: 日次トピック別
            raw = (args.date or "").strip()
            try:
                d = date.fromisoformat(raw)
            except ValueError:
                print(
                    "day の --date は YYYY-MM-DD 形式で指定してください（例: 2026-01-04）",
                    file=sys.stderr,
                )
                return 2
            return _run_day_topics(conn, args, base_url, model, d, dry_run=args.dry_run)

        if args.period == "week":
            try:
                iso_year, iso_week, monday, sunday = parse_iso_week_date(args.date)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 2
            label = week_label(iso_year, iso_week, monday, sunday)
            if args.legacy:
                return _run_week(conn, args, base_url, model, dry_run=args.dry_run)
            return _run_week_topics(
                conn, args, base_url, model,
                iso_year, iso_week, monday, sunday, label,
                dry_run=args.dry_run,
            )

        # month
        try:
            year, month_num = parse_year_month(args.date)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        first, last = month_calendar_range(year, month_num)
        label = month_label(year, month_num, first, last)
        if args.legacy:
            return _run_month(conn, args, base_url, model, dry_run=args.dry_run)
        return _run_month_topics(
            conn, args, base_url, model,
            year, month_num, first, last, label,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
