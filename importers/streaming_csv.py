"""Netflix / Amazon Prime Video 視聴履歴 CSV のインポート

使用例:
  python -m importers.streaming_csv ~/planet-data/exports/NetflixViewingHistory.csv
  python -m importers.streaming_csv ~/planet-data/exports/NetflixViewingActivityFull.csv
  python -m importers.streaming_csv --netflix-profile ホ ~/planet-data/exports/NetflixViewingActivityFull.csv
  python -m importers.streaming_csv --format prime ~/planet-data/exports/watch-history-export-123.csv
  python -m importers.streaming_csv --dry-run path/to/file.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

# import_streaming_csv の netflix_cutoff: 未指定時は DB から取得
_CUTOFF_UNSET = object()

sys.path.insert(0, str(Path(__file__).parent.parent))

from importers.common import get_db_conn, load_config  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
BATCH = 500


@dataclass
class ImportResult:
    """プログラム/API から参照する取り込み結果。"""

    success: bool
    exit_code: int
    format: str | None
    ok: int
    skip: int
    err: int
    messages: list[str] = field(default_factory=list)


def _source_id(cur, stype: str) -> int:
    cur.execute("SELECT id FROM data_sources WHERE type = %s", (stype,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"data_sources に type={stype!r} がありません。"
            " db/migrate_streaming_views.sql を実行してください。"
        )
    return row[0]


def detect_format(fieldnames: list[str] | None) -> str | None:
    if not fieldnames:
        return None
    keys = {fn.strip() for fn in fieldnames}
    if {"Title", "Start Time", "Duration"}.issubset(keys):
        return "netflix_activity"
    if {"Title", "Date"}.issubset(keys) and "Date Watched" not in keys:
        return "netflix"
    if "Date Watched" in keys and "Episode Global Title Identifier" in keys:
        return "prime"
    return None


def netflix_original_id(title: str, date_raw: str) -> str:
    payload = f"{title.strip()}\0{date_raw.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def netflix_watched_at_utc(date_mdy: str) -> datetime:
    d = datetime.strptime(date_mdy.strip(), "%m/%d/%y").date()
    local = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=JST)
    return local.astimezone(timezone.utc)


def netflix_simple_row_date_jst(date_raw: str) -> date:
    """簡易版 Date 列が指す暦日（JST）。"""
    return netflix_watched_at_utc(date_raw).astimezone(JST).date()


def get_netflix_cutoff_date_jst(cur) -> date | None:
    """DB にある Netflix の最新 timestamp を JST の日付にしたカットオフ（簡易版用）。
    行が無ければ None（簡易は全行対象）。
    """
    cur.execute(
        """
        SELECT MAX(l.timestamp)
          FROM logs l
          JOIN data_sources ds ON l.source_id = ds.id
         WHERE ds.type = 'netflix' AND l.is_deleted = FALSE
        """
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return row[0].astimezone(JST).date()


def netflix_activity_original_id(title: str, start_raw: str) -> str:
    payload = f"{title.strip()}\0{start_raw.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def netflix_activity_watched_at_utc(start_raw: str) -> datetime:
    s = (start_raw or "").strip()
    naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=JST).astimezone(timezone.utc)


def prime_original_id(row: dict) -> str:
    epi = (row.get("Episode Global Title Identifier") or "").strip()
    if epi:
        return epi
    raw = (
        f"{row.get('Title', '')}\0{row.get('Episode Title', '')}\0"
        f"{row.get('Date Watched', '')}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def prime_watched_at_utc(date_watched: str) -> datetime:
    s = (date_watched or "").strip()
    if not s:
        raise ValueError("Date Watched が空です")
    if "." in s:
        naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    else:
        naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=JST).astimezone(timezone.utc)


def prime_watched_on(watched_at_utc: datetime) -> date:
    return watched_at_utc.astimezone(JST).date()


UPSERT_LOG = """
INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
VALUES (%s, %s, %s, NULL, %s, %s::jsonb)
ON CONFLICT (source_id, original_id) DO UPDATE SET
    content = EXCLUDED.content,
    timestamp = EXCLUDED.timestamp,
    metadata = EXCLUDED.metadata
RETURNING id
"""

UPSERT_SV = """
INSERT INTO streaming_views (
    log_id, source_id, provider, title, episode_title, watched_on, watched_at,
    content_kind, external_series_id, external_episode_id, metadata
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
ON CONFLICT (log_id) DO UPDATE SET
    source_id = EXCLUDED.source_id,
    provider = EXCLUDED.provider,
    title = EXCLUDED.title,
    episode_title = EXCLUDED.episode_title,
    watched_on = EXCLUDED.watched_on,
    watched_at = EXCLUDED.watched_at,
    content_kind = EXCLUDED.content_kind,
    external_series_id = EXCLUDED.external_series_id,
    external_episode_id = EXCLUDED.external_episode_id,
    metadata = EXCLUDED.metadata
"""


def _upsert_pair(
    cur,
    source_id: int,
    provider: str,
    original_id: str,
    content: str,
    ts: datetime,
    log_meta: dict,
    title: str,
    episode_title: str | None,
    watched_on: date,
    watched_at: datetime,
    content_kind: str | None,
    ext_series: str | None,
    ext_episode: str | None,
    sv_meta: dict | None,
) -> None:
    cur.execute(
        UPSERT_LOG,
        (
            source_id,
            original_id,
            content,
            ts,
            json.dumps(log_meta, ensure_ascii=False),
        ),
    )
    log_id = cur.fetchone()[0]
    cur.execute(
        UPSERT_SV,
        (
            log_id,
            source_id,
            provider,
            title,
            episode_title,
            watched_on,
            watched_at,
            content_kind,
            ext_series,
            ext_episode,
            json.dumps(sv_meta or {}, ensure_ascii=False),
        ),
    )


def _dry_run_validate(
    rows: list[dict],
    use_fmt: str,
    strict: bool,
    netflix_cutoff: date | None,
    messages: list[str],
) -> tuple[int, int, int]:
    ok = skip = err = 0
    cutoff_skipped = 0
    for row in rows:
        if use_fmt == "netflix":
            title = (row.get("Title") or "").strip()
            date_raw = (row.get("Date") or "").strip()
            if not title or not date_raw:
                skip += 1
                if strict:
                    raise ValueError(f"strict: 空の Title/Date: {row!r}")
                continue
            try:
                row_d = netflix_simple_row_date_jst(date_raw)
                if netflix_cutoff is not None and row_d <= netflix_cutoff:
                    cutoff_skipped += 1
                    skip += 1
                    continue
                netflix_watched_at_utc(date_raw)
                netflix_original_id(title, date_raw)
            except ValueError as e:
                err += 1
                if strict:
                    raise
                messages.append(f"日付パース失敗: {date_raw!r} ({e})")
                continue
            ok += 1
        elif use_fmt == "netflix_activity":
            title = (row.get("Title") or "").strip()
            start_raw = (row.get("Start Time") or "").strip()
            if not title or not start_raw:
                skip += 1
                if strict:
                    raise ValueError(f"strict: 空の Title/Start Time: {row!r}")
                continue
            try:
                netflix_activity_watched_at_utc(start_raw)
                netflix_activity_original_id(title, start_raw)
            except ValueError as e:
                err += 1
                if strict:
                    raise
                messages.append(f"Start Time パース失敗: {start_raw!r} ({e})")
                continue
            ok += 1
        else:
            title_p = (row.get("Title") or "").strip()
            dw = (row.get("Date Watched") or "").strip()
            if not title_p:
                skip += 1
                if strict:
                    raise ValueError("strict: Title 空")
                continue
            if not dw:
                skip += 1
                if strict:
                    raise ValueError("strict: Date Watched 空")
                continue
            try:
                prime_watched_at_utc(dw)
                prime_original_id(row)
            except ValueError as e:
                err += 1
                if strict:
                    raise
                messages.append(f"日時パース失敗: {dw!r} ({e})")
                continue
            ok += 1
    if cutoff_skipped:
        messages.append(f"カットオフより前の日付でスキップ: {cutoff_skipped} 行")
    return ok, skip, err


def import_streaming_csv(
    path: Path,
    fmt: str | None,
    dry_run: bool,
    strict: bool,
    netflix_profile: str | None = None,
    netflix_cutoff: date | None | Any = _CUTOFF_UNSET,
) -> ImportResult:
    """CSV を取り込む。netflix_cutoff が _CUTOFF_UNSET のとき簡易版は DB からカットオフ取得。

    netflix_cutoff に None を明示すると「カットオフなし」で簡易を全行処理。
    """
    messages: list[str] = []

    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    detected = detect_format(fieldnames)
    use_fmt = fmt or detected
    if not use_fmt:
        return ImportResult(
            success=False,
            exit_code=1,
            format=None,
            ok=0,
            skip=0,
            err=0,
            messages=[
                "フォーマットを判定できませんでした。--format を指定してください。",
                f"ヘッダ: {fieldnames}",
            ],
        )

    if netflix_profile is not None and use_fmt != "netflix_activity":
        return ImportResult(
            success=False,
            exit_code=1,
            format=use_fmt,
            ok=0,
            skip=0,
            err=0,
            messages=[
                "エラー: --netflix-profile は netflix_activity（視聴アクティビティ詳細 CSV）でのみ使えます。"
            ],
        )

    if fmt and detected and fmt != detected:
        messages.append(f"警告: --format {fmt} を指定しましたが、ヘッダは {detected} 向きに見えます")

    if use_fmt == "netflix_activity":
        messages.append(
            "Netflix 視聴アクティビティ詳細: Start Time を JST として解釈し logs.timestamp に保存"
        )

    if netflix_profile is not None:
        n0 = len(rows)
        rows = [r for r in rows if (r.get("Profile Name") or "").strip() == netflix_profile]
        messages.append(
            f'プロファイル「{netflix_profile}」のみ: {len(rows)} 行（元 {n0} 行、除外 {n0 - len(rows)} 行）'
        )

    messages.append(f"ファイル: {path}")
    messages.append(f"フォーマット: {use_fmt}  行数: {len(rows)}")

    co: date | None = None
    if use_fmt == "netflix":
        if netflix_cutoff is _CUTOFF_UNSET:
            config = load_config()
            conn = get_db_conn(config)
            cur = conn.cursor()
            try:
                co = get_netflix_cutoff_date_jst(cur)
            finally:
                cur.close()
                conn.close()
        else:
            co = cast(date | None, netflix_cutoff)
        if co is not None:
            messages.append(
                f"Netflix 簡易カットオフ (JST): {co.isoformat()} より後の暦日のみ"
            )
        else:
            messages.append(
                "Netflix 簡易カットオフ: なし（DB に Netflix 行が無い → 全行対象）"
            )

    if dry_run:
        try:
            ok, skip, err = _dry_run_validate(rows, use_fmt, strict, co, messages)
        except ValueError:
            return ImportResult(
                success=False,
                exit_code=1,
                format=use_fmt,
                ok=0,
                skip=0,
                err=0,
                messages=messages,
            )
        messages.append(f"[dry-run] 取り込み予定: {ok}  スキップ: {skip}  エラー: {err}")
        bad = strict and err > 0
        return ImportResult(
            success=not bad,
            exit_code=1 if bad else 0,
            format=use_fmt,
            ok=ok,
            skip=skip,
            err=err,
            messages=messages,
        )

    config = load_config()
    conn = get_db_conn(config)
    cur = conn.cursor()
    ok = skip = err = 0
    batch = 0
    try:
        sid = _source_id(
            cur,
            "netflix" if use_fmt in ("netflix", "netflix_activity") else "prime",
        )

        for row in rows:
            if use_fmt == "netflix":
                title = (row.get("Title") or "").strip()
                date_raw = (row.get("Date") or "").strip()
                if not title or not date_raw:
                    skip += 1
                    if strict:
                        raise ValueError("strict: 空の Title/Date")
                    continue
                try:
                    row_d = netflix_simple_row_date_jst(date_raw)
                    if co is not None and row_d <= co:
                        skip += 1
                        continue
                    ts = netflix_watched_at_utc(date_raw)
                    watched_on = ts.astimezone(JST).date()
                except ValueError as e:
                    err += 1
                    if strict:
                        raise
                    messages.append(f"日付パース失敗: {date_raw!r} ({e})")
                    continue
                oid = netflix_original_id(title, date_raw)
                content = f"Netflix視聴: {title}"
                log_meta = {
                    "type": "netflix_view",
                    "title": title,
                    "watch_date": watched_on.isoformat(),
                }
                _upsert_pair(
                    cur,
                    sid,
                    "netflix",
                    oid,
                    content,
                    ts,
                    log_meta,
                    title,
                    None,
                    watched_on,
                    ts,
                    None,
                    None,
                    None,
                    None,
                )
            elif use_fmt == "netflix_activity":
                title = (row.get("Title") or "").strip()
                start_raw = (row.get("Start Time") or "").strip()
                if not title or not start_raw:
                    skip += 1
                    if strict:
                        raise ValueError("strict: 空の Title/Start Time")
                    continue
                try:
                    ts = netflix_activity_watched_at_utc(start_raw)
                    watched_on = ts.astimezone(JST).date()
                except ValueError as e:
                    err += 1
                    if strict:
                        raise
                    messages.append(f"Start Time パース失敗: {start_raw!r} ({e})")
                    continue
                oid = netflix_activity_original_id(title, start_raw)
                content = f"Netflix視聴: {title}"
                log_meta = {
                    "type": "netflix_view",
                    "title": title,
                    "watch_date": watched_on.isoformat(),
                    "start_time_local": start_raw,
                    "duration": (row.get("Duration") or "").strip(),
                    "profile_name": (row.get("Profile Name") or "").strip(),
                }
                sv_meta = {
                    "duration": (row.get("Duration") or "").strip() or None,
                    "device_type": (row.get("Device Type") or "").strip() or None,
                    "supplemental_video_type": (row.get("Supplemental Video Type") or "").strip()
                    or None,
                    "profile_name": (row.get("Profile Name") or "").strip() or None,
                }
                sv_meta = {k: v for k, v in sv_meta.items() if v}
                _upsert_pair(
                    cur,
                    sid,
                    "netflix",
                    oid,
                    content,
                    ts,
                    log_meta,
                    title,
                    None,
                    watched_on,
                    ts,
                    None,
                    None,
                    None,
                    sv_meta if sv_meta else None,
                )
            else:
                title = (row.get("Title") or "").strip()
                dw = (row.get("Date Watched") or "").strip()
                if not title:
                    skip += 1
                    if strict:
                        raise ValueError("strict: Title 空")
                    continue
                if not dw:
                    skip += 1
                    if strict:
                        raise ValueError("strict: Date Watched 空")
                    continue
                try:
                    watched_at = prime_watched_at_utc(dw)
                    watched_on = prime_watched_on(watched_at)
                except ValueError as e:
                    err += 1
                    if strict:
                        raise
                    messages.append(f"日時パース失敗: {dw!r} ({e})")
                    continue
                ep = (row.get("Episode Title") or "").strip() or None
                oid = prime_original_id(row)
                parts = [f"Prime視聴: {title}"]
                if ep:
                    parts.append(f"— {ep}")
                content = " ".join(parts)
                ck = (row.get("Type") or "").strip() or None
                gti = (row.get("Global Title Identifier") or "").strip() or None
                egti = (row.get("Episode Global Title Identifier") or "").strip() or None
                log_meta = {
                    "type": "prime_view",
                    "title": title,
                    "episode_title": ep,
                    "watched_at_local": dw,
                }
                sv_meta = {}
                for k, v in (
                    ("path", row.get("Path")),
                    ("episode_path", row.get("Episode Path")),
                    ("image_url", row.get("Image URL")),
                ):
                    if v and str(v).strip():
                        sv_meta[k] = str(v).strip()
                _upsert_pair(
                    cur,
                    sid,
                    "prime",
                    oid,
                    content,
                    watched_at,
                    log_meta,
                    title,
                    ep,
                    watched_on,
                    watched_at,
                    ck,
                    gti,
                    egti,
                    sv_meta if sv_meta else None,
                )
            ok += 1
            batch += 1
            if batch >= BATCH:
                conn.commit()
                messages.append(f"コミット… 累計 {ok} 件")
                batch = 0

        conn.commit()
        messages.append(f"完了: 投入 {ok}  スキップ {skip}  エラー {err}")
        code = 0 if (err == 0 or not strict) else 1
        return ImportResult(
            success=code == 0,
            exit_code=code,
            format=use_fmt,
            ok=ok,
            skip=skip,
            err=err,
            messages=messages,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def run_import(
    path: Path,
    fmt: str | None,
    dry_run: bool,
    strict: bool,
    netflix_profile: str | None = None,
) -> int:
    """CLI 用: ImportResult を print して終了コードを返す。"""
    res = import_streaming_csv(path, fmt, dry_run, strict, netflix_profile)
    for line in res.messages:
        print(line)
    return res.exit_code


def main() -> None:
    p = argparse.ArgumentParser(description="Netflix / Prime Video 視聴 CSV インポート")
    p.add_argument("csv_path", type=Path, help="CSV ファイルパス")
    p.add_argument(
        "--format",
        choices=("netflix", "netflix_activity", "prime"),
        default=None,
        help="省略時はヘッダから自動判定",
    )
    p.add_argument("--dry-run", action="store_true", help="DB に書かずパース検証のみ")
    p.add_argument("--strict", action="store_true", help="パースエラーで即終了")
    p.add_argument(
        "--netflix-profile",
        metavar="NAME",
        default=None,
        help="netflix_activity のみ: Profile Name が一致する行だけ取り込む（例: ホ）",
    )
    args = p.parse_args()
    path = args.csv_path.expanduser().resolve()
    if not path.is_file():
        print(f"ファイルがありません: {path}", file=sys.stderr)
        sys.exit(1)
    sys.exit(
        run_import(
            path,
            args.format,
            args.dry_run,
            args.strict,
            args.netflix_profile,
        )
    )


if __name__ == "__main__":
    main()
