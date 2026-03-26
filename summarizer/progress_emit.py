"""サマリー生成の進捗を stderr に出す（CLI 人間向け / ダッシュボード用機械可読）。"""

from __future__ import annotations

import json
import os
import sys

PROGRESS_PREFIX = "__PLANET_PROGRESS__ "
MACHINE_ENV = "PLANET_SUMMARY_PROGRESS_MACHINE"


def _message(
    phase: str,
    label: str | None = None,
    *,
    num_weeks: int | None = None,
) -> str:
    if phase == "daily" and label:
        return f"{label} の日次要約を生成中"
    if phase == "daily_skip" and label:
        return f"{label} はログなし（日次スキップ）"
    if phase == "weekly_merge":
        return "週次サマリーを統合中（日次要約をマージ）"
    if phase == "weekly_flat":
        return "週次要約を生成中（活動ログ一括）"
    if phase == "monthly_flat":
        return "月次要約を生成中（活動ログ一括）"
    if phase == "monthly_from_weeklies":
        if num_weeks is not None:
            return f"月次要約を生成中（週次 {num_weeks} 件を集約）"
        return "月次要約を生成中（週次から集約）"
    return "処理中"


def emit_summary_progress(
    step: int,
    total: int,
    *,
    phase: str,
    label: str | None = None,
    num_weeks: int | None = None,
) -> None:
    """
    CLI: 人間向け 1 行（進捗: …（n/m））。
    PLANET_SUMMARY_PROGRESS_MACHINE=1 のときは機械向け 1 行のみ（PREFIX + JSON）。
    """
    message = _message(phase, label, num_weeks=num_weeks)
    payload: dict = {
        "step": step,
        "total": total,
        "phase": phase,
        "message": message,
    }
    if label is not None:
        payload["label"] = label
    if num_weeks is not None:
        payload["num_weeks"] = num_weeks

    if os.environ.get(MACHINE_ENV) == "1":
        print(
            PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=False),
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            f"進捗: {message}（{step}/{total}）",
            file=sys.stderr,
            flush=True,
        )
