"""全コレクター一括実行スクリプト

使用例:
  python collect_all.py          # 全て実行
  python collect_all.py misskey  # Misskeyのみ
  python collect_all.py sns      # Misskey + Mastodon
"""

import sys

def run(targets):
    if "misskey" in targets or "sns" in targets or "all" in targets:
        from collectors.misskey import MisskeyCollector
        c = MisskeyCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "mastodon" in targets or "sns" in targets or "all" in targets:
        from collectors.mastodon import MastodonCollector
        c = MastodonCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "lastfm" in targets or "all" in targets:
        from collectors.lastfm import LastfmCollector
        c = LastfmCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "weather" in targets or "all" in targets:
        from collectors.weather import WeatherCollector
        c = WeatherCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "github" in targets or "all" in targets:
        from collectors.github import GithubCollector
        c = GithubCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "rss" in targets or "all" in targets:
        from collectors.rss import RssCollector
        c = RssCollector()
        try:
            c.collect()
        finally:
            c.close()

    if "youtube" in targets or "all" in targets:
        from collectors.youtube import YoutubeCollector
        c = YoutubeCollector()
        try:
            c.collect()
        finally:
            c.close()


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    run(targets)
