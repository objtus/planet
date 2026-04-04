"""planet-meta.json の sources[] に UI 用の上書きをマージ（settings.toml [planet_feed.source_display]）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_source_display_overrides(sources: list[dict], raw: Any) -> None:
    """各ソース dict をインプレース更新。

    TOML 例::

        [planet_feed.source_display.7]
        icon_emoji = "🌤️"

        [planet_feed.source_display.4]
        icon_file = "lastfm.svg"

        [planet_feed.source_display.8]
        icon_url = "https://example.com/gh.svg"

    優先度: icon_emoji（画像なし）> その後 icon_url / icon_file を個別に適用。
    """
    if not raw or not isinstance(raw, dict):
        return
    by_id = {str(s["id"]): s for s in sources}
    for sid_str, ov in raw.items():
        if not isinstance(ov, dict):
            continue
        s = by_id.get(str(sid_str))
        if not s:
            logger.warning("planet_feed.source_display: 不明な source id %s（無視）", sid_str)
            continue

        emoji = ov.get("icon_emoji")
        if isinstance(emoji, str) and emoji.strip():
            s["icon_emoji"] = emoji.strip()
            s.pop("icon_url", None)
            s.pop("favicon", None)
            continue

        if "icon_url" in ov:
            u = ov.get("icon_url")
            if isinstance(u, str) and u.strip():
                s["icon_url"] = u.strip()
                s.pop("favicon", None)
            else:
                s.pop("icon_url", None)

        if "icon_file" in ov:
            f = ov.get("icon_file")
            if isinstance(f, str) and f.strip():
                s["favicon"] = f.strip()
            elif f in (None, ""):
                s.pop("favicon", None)
