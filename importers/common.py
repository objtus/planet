"""インポーター共通モジュール"""

import tomllib
import psycopg2
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_db_conn(config):
    db = config["database"]
    return psycopg2.connect(
        host=db["host"],
        port=db["port"],
        dbname=db["name"],
        user=db["user"],
        password=db["password"],
    )


def strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text()


def parse_timestamp(value: str):
    """タイムスタンプをUTC-aware datetimeに変換"""
    import datetime
    dt = dateutil_parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def classify_item(item: dict, own_account_id: str) -> str:
    """
    'own_note'    : 自分の通常投稿
    'boost'       : 自分のブースト/リノート
    'boosted_note': ブースト元の他者投稿（スキップ）
    'unknown'     : 不明（スキップ）
    """
    if "announce" in item:
        return "boost"
    if item.get("type") == "Note":
        if item.get("attributedTo", "") == own_account_id:
            return "own_note"
        else:
            return "boosted_note"
    return "unknown"


def get_own_account_id(data: list) -> str:
    """JSONの最初のアイテムからアカウントIDを取得"""
    for item in data:
        if "account" in item:
            return item["account"]["id"]
    raise ValueError("アカウントIDが見つかりません")


def get_or_create_source(cur, name: str, type_: str, base_url: str, account: str, is_active: bool) -> int:
    cur.execute(
        "SELECT id FROM data_sources WHERE name = %s",
        (name,)
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO data_sources (name, type, base_url, account, is_active)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (name, type_, base_url, account, is_active)
    )
    return cur.fetchone()[0]


PUBLIC = "https://www.w3.org/ns/activitystreams#Public"


def get_misskey_visibility(item: dict) -> str:
    to = item.get("to", [])
    cc = item.get("cc", [])
    if PUBLIC in to:
        return "public"
    elif PUBLIC in cc:
        return "home"
    else:
        return "followers"


def get_mastodon_visibility(item: dict) -> str:
    to = item.get("to", [])
    cc = item.get("cc", [])
    if PUBLIC in to:
        return "public"
    elif PUBLIC in cc:
        return "unlisted"
    else:
        return "followers"


def extract_id_from_url(url: str) -> str:
    """URLの末尾セグメントを取得"""
    return url.rstrip("/").split("/")[-1]
