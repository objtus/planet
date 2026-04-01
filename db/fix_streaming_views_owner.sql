-- 既に migrate_streaming_views.sql を適用済みで
-- 「permission denied for table streaming_views」が出る場合に一度だけ実行。
-- 例: sudo -u postgres psql -d planet < db/fix_streaming_views_owner.sql
--
-- DB 接続ユーザー名が planet でない場合は planet を置き換える。

ALTER TABLE streaming_views OWNER TO planet;
ALTER SEQUENCE streaming_views_id_seq OWNER TO planet;
