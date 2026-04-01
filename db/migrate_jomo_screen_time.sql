-- Jomo（iOS ショートカット）からの1日あたりスクリーンタイム（秒）用
--
-- 実行例（Peer 認証で postgres ユーザーに切り替える場合）:
--   sudo -u postgres psql -d planet < /path/to/planet/db/migrate_jomo_screen_time.sql
-- ※ -f でホーム配下のファイルを渡すと、postgres が読めず Permission denied になることがある。

ALTER TABLE health_daily
  ADD COLUMN IF NOT EXISTS screen_time_seconds INT;

INSERT INTO data_sources (name, type, base_url, account, is_active, sort_order, short_name)
SELECT 'Jomo スクリーンタイム', 'screen_time', NULL, NULL, TRUE,
       COALESCE((SELECT MAX(sort_order) FROM data_sources s2), 0) + 1,
       'jomo'
WHERE NOT EXISTS (SELECT 1 FROM data_sources WHERE type = 'screen_time');

SELECT id, name, type, sort_order, short_name FROM data_sources WHERE type = 'screen_time';
