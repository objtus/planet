"""全コレクター一括実行スクリプト

使用例:
  python collect_all.py          # 全て実行
  python collect_all.py misskey  # Misskeyのみ
  python collect_all.py sns      # Misskey + Mastodon
"""

import importlib
import sys

# 実行順を保持した (モジュールパス, クラス名) のマッピング
COLLECTORS = {
    "misskey":  ("collectors.misskey",   "MisskeyCollector"),
    "mastodon": ("collectors.mastodon",  "MastodonCollector"),
    "lastfm":   ("collectors.lastfm",    "LastfmCollector"),
    "weather":  ("collectors.weather",   "WeatherCollector"),
    "github":   ("collectors.github",    "GithubCollector"),
    "rss":      ("collectors.rss",       "RssCollector"),
    "youtube":  ("collectors.youtube",   "YoutubeCollector"),
    "scrapbox": ("collectors.scrapbox",  "ScrapboxCollector"),
}

# グループエイリアス
GROUPS = {
    "sns": {"misskey", "mastodon"},
}


def run(targets):
    active = set()
    for t in targets:
        if t == "all":
            active.update(COLLECTORS)
        elif t in GROUPS:
            active.update(GROUPS[t])
        elif t in COLLECTORS:
            active.add(t)

    for name, (module_path, class_name) in COLLECTORS.items():
        if name not in active:
            continue
        cls = getattr(importlib.import_module(module_path), class_name)
        c = cls()
        try:
            c.collect()
        finally:
            c.close()


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    run(targets)
