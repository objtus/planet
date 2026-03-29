-- Scrapbox (Cosense) 日記収集のためのマイグレーション
-- 実行: psql -U planet -d planet -f db/migrate_scrapbox.sql

-- scrapbox_pages テーブル作成
CREATE TABLE IF NOT EXISTS scrapbox_pages (
    id               BIGSERIAL PRIMARY KEY,
    log_id           BIGINT REFERENCES logs(id),
    source_id        INT REFERENCES data_sources(id),
    project          TEXT NOT NULL,
    page_title       TEXT NOT NULL,         -- '2026/03/25'（スラッシュ区切り、Scrapboxのタイトルそのまま）
    content          TEXT,                  -- ページ全文（Scrapbox記法含む）
    content_plain    TEXT,                  -- 自分のセクションのみ・記法除去済みプレーンテキスト
    page_date        DATE,                  -- タイトルから解析した日付
    scrapbox_updated BIGINT,               -- Scrapboxのupdatedタイムスタンプ（Unix秒）
    fetched_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project, page_title)
);

-- data_sources に Scrapbox を追加
INSERT INTO data_sources (name, type, base_url, account, is_active)
VALUES ('Cosense stall', 'scrapbox', 'https://scrapbox.io/stall', NULL, TRUE)
ON CONFLICT DO NOTHING;

-- 確認
SELECT id, name, type, is_active FROM data_sources ORDER BY id;
