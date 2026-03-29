"""Scrapbox (Cosense) 日記収集スクリプト

stallプロジェクトの日付ページから自分のセクションを抽出してDBに保存する。
複数人が同じページに書くため、アイコン記法（[health.icon]）でセクション分割。
"""

import re
import json
import urllib.parse
import datetime
import time
import requests
from collectors.base import BaseCollector

NAV_PATTERN = re.compile(r'.*←\d{4}/\d{2}/\d{2}→.*')
ICON_PATTERN = re.compile(r'^\[[\w\.]+\.icon\]$')


def strip_scrapbox_notation(text: str) -> str:
    """Scrapbox記法を除去してプレーンテキストに変換"""
    text = re.sub(r'\[\*+\s+(.*?)\]', r'\1', text)
    text = re.sub(r'\[([^\]]+?)\s+https?://[^\]]+\]', r'\1', text)
    text = re.sub(r'\[https?://[^\]]+\]', '', text)
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)
    return text.strip()


def extract_my_entries(text: str, my_icons: list) -> str:
    """自分のアイコン行から次のアイコン行までの全行を抽出する"""
    lines = text.split("\n")
    my_sections = []
    in_my_section = False

    for line in lines:
        stripped = line.strip()

        if any(f"[{icon}]" == stripped for icon in my_icons):
            in_my_section = True
            continue

        if ICON_PATTERN.match(stripped) and in_my_section:
            in_my_section = False
            continue

        if in_my_section:
            if NAV_PATTERN.match(stripped):
                continue
            clean = strip_scrapbox_notation(stripped)
            if clean:
                my_sections.append(clean)

    return "\n".join(my_sections).strip()


class ScrapboxCollector(BaseCollector):

    def collect(self):
        cfg = self.config["scrapbox"]
        source_id  = cfg["source_id"]
        project    = cfg["project"]
        my_icons   = cfg["my_icons"]
        lookback   = cfg.get("lookback_days", 30)

        print(f"[Scrapbox] project={project} lookback={lookback}日 (source_id={source_id})")

        upserted = 0
        today = datetime.date.today()

        for i in range(lookback):
            d = today - datetime.timedelta(days=i)
            page_title   = d.strftime("%Y/%m/%d")
            encoded_title = urllib.parse.quote(page_title, safe="")
            meta_url     = f"https://scrapbox.io/api/pages/{project}/{encoded_title}"

            try:
                res = requests.get(meta_url, timeout=10)
            except requests.RequestException as e:
                print(f"  {page_title}: 取得エラー ({e})", flush=True)
                continue

            if res.status_code == 404:
                continue
            if res.status_code != 200:
                print(f"  {page_title}: HTTP {res.status_code}", flush=True)
                continue

            page_meta   = res.json()
            sb_updated  = page_meta.get("updated")

            # 前回保存したupdatedと比較して変化がなければスキップ
            self.cur.execute(
                "SELECT scrapbox_updated FROM scrapbox_pages WHERE project=%s AND page_title=%s",
                (project, page_title)
            )
            row = self.cur.fetchone()
            if row and row[0] == sb_updated:
                continue  # 変更なし

            # 本文取得
            text_url = f"https://scrapbox.io/api/pages/{project}/{encoded_title}/text"
            try:
                text_res = requests.get(text_url, timeout=10)
                raw_text = text_res.text
            except requests.RequestException as e:
                print(f"  {page_title}: 本文取得エラー ({e})", flush=True)
                continue

            content_plain = extract_my_entries(raw_text, my_icons)

            # logsのtimestamp: ページ日付のJST 00:00をUTCに変換
            jst = datetime.timezone(datetime.timedelta(hours=9))
            ts  = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=jst)

            log_url = f"https://scrapbox.io/{project}/{encoded_title}"

            # logs upsert（内容が変わる可能性があるのでDO UPDATE）
            self.cur.execute(
                """INSERT INTO logs (source_id, original_id, content, url, timestamp, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (source_id, original_id)
                   DO UPDATE SET content=EXCLUDED.content, metadata=EXCLUDED.metadata
                   RETURNING id""",
                (
                    source_id,
                    f"{project}/{page_title}",
                    content_plain,
                    log_url,
                    ts,
                    json.dumps({"type": "scrapbox", "page_title": page_title, "scrapbox_updated": sb_updated}),
                )
            )
            log_row = self.cur.fetchone()
            log_id  = log_row[0] if log_row else None

            # log_idが取れない場合（DO UPDATEでRETURNINGが返らないケース）はSELECTで取得
            if log_id is None:
                self.cur.execute(
                    "SELECT id FROM logs WHERE source_id=%s AND original_id=%s",
                    (source_id, f"{project}/{page_title}")
                )
                r = self.cur.fetchone()
                log_id = r[0] if r else None

            # scrapbox_pages upsert
            self.cur.execute(
                """INSERT INTO scrapbox_pages
                       (log_id, source_id, project, page_title, content, content_plain, page_date, scrapbox_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (project, page_title)
                   DO UPDATE SET
                       log_id=EXCLUDED.log_id,
                       content=EXCLUDED.content,
                       content_plain=EXCLUDED.content_plain,
                       scrapbox_updated=EXCLUDED.scrapbox_updated,
                       fetched_at=NOW()""",
                (log_id, source_id, project, page_title, raw_text, content_plain, d, sb_updated)
            )

            action = "更新" if row else "挿入"
            print(f"  {page_title}: {action} ({len(content_plain)}文字)")
            upserted += 1
            time.sleep(0.5)  # レート制限配慮

        self.commit()
        print(f"[Scrapbox] {upserted}件処理完了")


if __name__ == "__main__":
    c = ScrapboxCollector()
    try:
        c.collect()
    finally:
        c.close()
