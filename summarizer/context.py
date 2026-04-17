"""
期間内の logs を要約用テキストに変換。

週次: **日別に均等上限**（暦日 JST ごと）を取り、結合後に時系列ソートする。
  直近 N 件だけ取る方式だと、Last.fm 等で週末に件数が偏ると「最終日しか無い」digest になるため。

日次: `fetch_activity_digest_for_day` — 階層パイプライン（`generate --pipeline hierarchical`）で 1 日ずつ LLM に渡す。

月次: 従来どおり期間内 **直近** max_lines（月はログ量が大きいため別定数）。

トピック別: `fetch_topic_digest_for_day` — source_types でフィルタリングし、トピック別プロンプトに渡す。
"""

from datetime import date, datetime, time, timedelta, timezone

from summarizer.week_bounds import JST

# 日次（階層パイプライン）: 1 暦日あたりの最大行数（時系列昇順）。Last.fm 集中日でも上限で打ち切り。
MAX_LOG_LINES_DAILY = 3500
# 週: 7 日で均等割り（5600 // 7 = 800 行/日）。Last.fm 等で週末が厚い週でも他日の行を残す。
MAX_LOG_LINES_WEEKLY = 5600
# fetch_activity_digest の既定（月次は generate 側で MAX_LOG_LINES_MONTHLY を指定）
MAX_LOG_LINES = 2000
MAX_LOG_LINES_MONTHLY = 8000
CONTENT_PREVIEW_CHARS = 500
# 週次は行数も増やすので、1 行あたりの本文も長めに（SNS 本文・複数日の手がかり用）
CONTENT_PREVIEW_CHARS_WEEKLY = 1200
CONTENT_PREVIEW_CHARS_DAILY = 1500


def _format_digest_line(
    lid, source_id, content, ts, *, preview_limit: int | None = None,
    include_id: bool = False,
    source_name_map: dict | None = None,
) -> str | None:
    if ts is None:
        return None
    limit = CONTENT_PREVIEW_CHARS if preview_limit is None else preview_limit
    ts_jst = ts.astimezone(JST) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(JST)
    raw = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(raw) > limit:
        raw = raw[:limit] + "…"
    one = raw.replace("\n", " ").strip()
    if not one:
        one = "(本文なし)"
    # source ラベル: マップがあればアカウント名、なければ数値 ID
    if source_name_map and source_id in source_name_map:
        src_label = source_name_map[source_id]
    else:
        src_label = f"source {source_id}"
    if include_id and lid is not None:
        return f"[id={lid} {ts_jst:%Y-%m-%d %H:%M}] ({src_label}) {one}"
    return f"[{ts_jst:%Y-%m-%d %H:%M}] ({src_label}) {one}"


def fetch_activity_digest(
    conn,
    start_utc: datetime,
    end_utc: datetime,
    *,
    max_lines: int = MAX_LOG_LINES,
) -> str:
    """月次など: 期間内の直近 max_lines 件を古い順に並べた 1 文字列。"""
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
        cur.execute(sql, (start_utc, end_utc, max_lines))
        rows = list(reversed(cur.fetchall()))

    lines = []
    for row in rows:
        line = _format_digest_line(*row)
        if line:
            lines.append(line)
    return "\n".join(lines)


def fetch_scrapbox_diary(conn, day: date) -> str | None:
    """指定日の Scrapbox 日記（自分のセクション・記法除去済み）を返す。なければ None。"""
    page_title = day.strftime("%Y/%m/%d")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content_plain FROM scrapbox_pages WHERE page_title = %s AND content_plain != ''",
            (page_title,)
        )
        row = cur.fetchone()
    if not row or not row[0].strip():
        return None
    return row[0].strip()


def fetch_activity_digest_for_day(
    conn,
    day: date,
    *,
    max_lines: int = MAX_LOG_LINES_DAILY,
    preview_limit: int | None = None,
) -> str:
    """JST の 1 暦日（0:00〜翌日未満）の logs を時系列昇順で最大 max_lines 件。
    Scrapbox 日記がある場合は末尾にセクションとして追加する。
    """
    limit = (
        CONTENT_PREVIEW_CHARS_DAILY if preview_limit is None else preview_limit
    )
    day_start_local = datetime.combine(day, time.min, tzinfo=JST)
    day_end_local = day_start_local + timedelta(days=1)
    ds_utc = day_start_local.astimezone(timezone.utc)
    de_utc = day_end_local.astimezone(timezone.utc)
    sql = """
        SELECT id, source_id, content, timestamp
          FROM logs
         WHERE is_deleted = FALSE
           AND timestamp >= %s
           AND timestamp < %s
         ORDER BY timestamp ASC
         LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ds_utc, de_utc, max_lines))
        rows = cur.fetchall()
    lines = []
    for row in rows:
        line = _format_digest_line(*row, preview_limit=limit)
        if line:
            lines.append(line)

    diary = fetch_scrapbox_diary(conn, day)
    if diary:
        lines.append(f"\n--- Scrapbox日記 ---\n{diary}")

    return "\n".join(lines)


# トピック別生成用: ソース種別→トピック名の対応
TOPIC_SOURCE_TYPES: dict[str, list[str]] = {
    "music":  ["lastfm"],
    "health": ["health", "photo", "screen_time"],
    "sns":    ["misskey", "mastodon"],
    "dev":    ["github"],
}

# トピック別の 1 日あたりログ上限
MAX_LOG_LINES_TOPIC = 800


def get_source_name_map(conn) -> dict[int, str]:
    """data_sources.id → 表示名（例: "tanoshii.site @health"）のマッピングを返す。
    ログ行のサーバー/アカウント情報を LLM に渡すために使う。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM data_sources")
        return {row[0]: row[1] for row in cur.fetchall()}


def fetch_topic_digest_for_day(
    conn,
    day: date,
    source_types: list[str],
    *,
    max_lines: int = MAX_LOG_LINES_TOPIC,
    preview_limit: int | None = None,
    source_name_map: dict | None = None,
) -> str:
    """JST の 1 暦日（0:00〜翌日未満）のうち、指定ソース種別のログのみ抽出する。
    トピック別プロンプト（daily_music.txt 等）に渡すために使う。
    """
    limit = CONTENT_PREVIEW_CHARS_DAILY if preview_limit is None else preview_limit
    day_start_local = datetime.combine(day, time.min, tzinfo=JST)
    day_end_local = day_start_local + timedelta(days=1)
    ds_utc = day_start_local.astimezone(timezone.utc)
    de_utc = day_end_local.astimezone(timezone.utc)

    # source_types に一致する source_id を取得
    placeholders = ",".join(["%s"] * len(source_types))
    sql_ids = f"""
        SELECT id FROM data_sources
         WHERE type IN ({placeholders}) AND is_active = TRUE
    """
    with conn.cursor() as cur:
        cur.execute(sql_ids, source_types)
        src_ids = [r[0] for r in cur.fetchall()]

    if not src_ids:
        return ""

    id_placeholders = ",".join(["%s"] * len(src_ids))
    sql = f"""
        SELECT id, source_id, content, timestamp
          FROM logs
         WHERE is_deleted = FALSE
           AND source_id IN ({id_placeholders})
           AND timestamp >= %s
           AND timestamp < %s
         ORDER BY timestamp ASC
         LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (*src_ids, ds_utc, de_utc, max_lines))
        rows = cur.fetchall()

    lines = []
    for row in rows:
        line = _format_digest_line(*row, preview_limit=limit, source_name_map=source_name_map)
        if line:
            lines.append(line)
    return "\n".join(lines)


def fetch_topic_digest_for_week(
    conn,
    monday: date,
    sunday: date,
    source_types: list[str],
    *,
    per_day: int = 200,
    preview_limit: int = 1500,
    include_id: bool = False,
    source_name_map: dict | None = None,
) -> str:
    """JST の月〜日の間、指定ソース種別の生ログを日均等に取得して返す。
    best_post 等「生の投稿文を引用したい」場合に使う（サマリーではなく原文）。
    """
    # source_ids を解決
    placeholders = ",".join(["%s"] * len(source_types))
    sql_ids = f"""
        SELECT id FROM data_sources
         WHERE type IN ({placeholders}) AND is_active = TRUE
    """
    with conn.cursor() as cur:
        cur.execute(sql_ids, source_types)
        src_ids = [r[0] for r in cur.fetchall()]

    if not src_ids:
        return ""

    id_placeholders = ",".join(["%s"] * len(src_ids))
    sql = f"""
        SELECT id, source_id, content, timestamp
          FROM logs
         WHERE is_deleted = FALSE
           AND source_id IN ({id_placeholders})
           AND timestamp >= %s
           AND timestamp < %s
         ORDER BY timestamp ASC
         LIMIT %s
    """

    rows_by_id: dict[int, tuple] = {}
    d = monday
    while d <= sunday:
        day_start_local = datetime.combine(d, time.min, tzinfo=JST)
        day_end_local = day_start_local + timedelta(days=1)
        ds_utc = day_start_local.astimezone(timezone.utc)
        de_utc = day_end_local.astimezone(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(sql, (*src_ids, ds_utc, de_utc, per_day))
            for row in cur.fetchall():
                rid = row[0]
                if rid is not None:
                    rows_by_id[rid] = row
        d += timedelta(days=1)

    rows = sorted(
        rows_by_id.values(),
        key=lambda r: r[3] or datetime.min.replace(tzinfo=timezone.utc),
    )
    lines = []
    for row in rows:
        line = _format_digest_line(
            *row, preview_limit=preview_limit, include_id=include_id,
            source_name_map=source_name_map,
        )
        if line:
            lines.append(line)
    return "\n".join(lines)


def fetch_activity_digest_week_balanced(
    conn,
    start_utc: datetime,
    end_utc: datetime,
    monday: date,
    sunday: date,
    *,
    max_total: int = MAX_LOG_LINES_WEEKLY,
) -> str:
    """
    週次専用: JST の各暦日（月〜日）について、その日の先頭から最大 per_day 件を取得し、
    週全体を時系列でつなぐ。週末にログが集中しても他日が digest から消えない。
    """
    per_day = max(1, max_total // 7)
    sql = """
        SELECT id, source_id, content, timestamp
          FROM logs
         WHERE is_deleted = FALSE
           AND timestamp >= %s
           AND timestamp < %s
         ORDER BY timestamp ASC
         LIMIT %s
    """
    rows_by_id: dict[int, tuple] = {}
    d = monday
    while d <= sunday:
        day_start_local = datetime.combine(d, time.min, tzinfo=JST)
        day_end_local = day_start_local + timedelta(days=1)
        ds_utc = day_start_local.astimezone(timezone.utc)
        de_utc = day_end_local.astimezone(timezone.utc)
        # 週の全体窓と交差（月曜 0:00〜日曜 23:59… の日ループで十分）
        with conn.cursor() as cur:
            cur.execute(sql, (ds_utc, de_utc, per_day))
            for row in cur.fetchall():
                rid = row[0]
                if rid is not None:
                    rows_by_id[rid] = row
        d += timedelta(days=1)

    rows = sorted(rows_by_id.values(), key=lambda r: r[3] or datetime.min.replace(tzinfo=timezone.utc))
    lines = []
    for row in rows:
        line = _format_digest_line(
            *row, preview_limit=CONTENT_PREVIEW_CHARS_WEEKLY
        )
        if line:
            lines.append(line)
    return "\n".join(lines)
