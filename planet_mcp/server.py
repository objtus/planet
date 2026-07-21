"""Planet MCP server — FastMCP stdio エントリ。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP

from planet_mcp.queries import (
    dumps_result,
    get_activity_digest as get_activity_digest_fn,
    get_stats as get_stats_fn,
    get_summaries as get_summaries_fn,
    get_timeline as get_timeline_fn,
    list_sources as list_sources_fn,
    search_posts as search_posts_fn,
)

mcp = FastMCP("planet")


@mcp.tool()
def list_sources() -> str:
    """Planet の全データソース（Misskey, Last.fm, health 等）一覧を返す。"""
    return dumps_result(list_sources_fn())


@mcp.tool()
def search_posts(
    query: str,
    source_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
) -> str:
    """ログ本文をキーワード検索（日本語 LIKE）。source_id / 日付範囲で絞り込み可。最大 200 件。"""
    return dumps_result(
        search_posts_fn(
            query,
            source_id=source_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    )


@mcp.tool()
def get_timeline(period: str, date: str) -> str:
    """指定期間のタイムライン。period=day|week|month、date=YYYY-MM-DD / YYYY-Www / YYYY-MM。"""
    return dumps_result(get_timeline_fn(period, date))


@mcp.tool()
def get_stats(period: str, date: str) -> str:
    """指定期間の統計（投稿数、Last.fm 再生、歩数、天気）。period=day|week|month|year。"""
    return dumps_result(get_stats_fn(period, date))


@mcp.tool()
def get_activity_digest(date: str, topic: str | None = None) -> str:
    """1 日分のアクティビティ digest テキスト。topic 省略時は全ソース、指定時は music|media|health|sns|dev。"""
    return dumps_result(get_activity_digest_fn(date, topic))


@mcp.tool()
def get_summaries(period: str, date: str) -> str:
    """AI 生成サマリー（トピック別）。period=day|week|month、date 形式は period に合わせる。"""
    return dumps_result(get_summaries_fn(period, date))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
