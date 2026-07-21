-- Planet MCP 読取専用ユーザー（手動実行: sudo -u postgres psql -d planet -f db/migrate_planet_mcp_user.sql）
-- パスワードは実行前に変更すること。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'planet_mcp') THEN
    CREATE ROLE planet_mcp LOGIN PASSWORD 'CHANGE_ME_planet_mcp';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE planet TO planet_mcp;
GRANT USAGE ON SCHEMA public TO planet_mcp;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO planet_mcp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO planet_mcp;
