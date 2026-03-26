"""
期間内の logs を要約用テキストに変換。

件数が多いときは **直近** MAX_LOG_LINES 件のみ（タイムスタンプ降順で取り、昇順で並べ直す）。
TODO(M3/M4): トークン上限に基づくトリミング・ソース別サンプリング。
"""

from datetime import datetime, timezone

from summarizer.week_bounds import JST

# M1: 固定上限。肥大化したら設計見直し。
MAX_LOG_LINES = 2000
CONTENT_PREVIEW_CHARS = 500


def fetch_activity_digest(conn, start_utc: datetime, end_utc: datetime) -> str:
    """指定期間のログを 1 行ずつ連結した文字列。0 件なら空文字。"""
    sql = """
        SELECT id, source_id, content, timestamp
          FROM logs
         WHERE is_deleted = FALSE
           AND timestamp >= %s
           AND timestamp < %s
         ORDER BY timestamp DESC
         LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start_utc, end_utc, MAX_LOG_LINES))
        rows = list(reversed(cur.fetchall()))

    lines = []
    for _lid, source_id, content, ts in rows:
        if ts is None:
            continue
        ts_jst = ts.astimezone(JST) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(JST)
        raw = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        if len(raw) > CONTENT_PREVIEW_CHARS:
            raw = raw[: CONTENT_PREVIEW_CHARS] + "…"
        one = raw.replace("\n", " ").strip()
        if not one:
            one = "(本文なし)"
        lines.append(f"[{ts_jst:%Y-%m-%d %H:%M}] (source {source_id}) {one}")

    return "\n".join(lines)
