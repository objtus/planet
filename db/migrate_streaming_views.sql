-- Netflix / Amazon Prime Video 視聴履歴用 streaming_views + data_sources
-- 実行例: sudo -u postgres psql -d planet < /path/to/planet/db/migrate_streaming_views.sql

CREATE TABLE IF NOT EXISTS streaming_views (
    id                   BIGSERIAL PRIMARY KEY,
    log_id               BIGINT NOT NULL UNIQUE REFERENCES logs(id) ON DELETE CASCADE,
    source_id            INT NOT NULL REFERENCES data_sources(id),
    provider             TEXT NOT NULL CHECK (provider IN ('netflix', 'prime')),
    title                TEXT NOT NULL,
    episode_title        TEXT,
    watched_on           DATE NOT NULL,
    watched_at           TIMESTAMPTZ NOT NULL,
    content_kind         TEXT,
    external_series_id   TEXT,
    external_episode_id  TEXT,
    metadata             JSONB
);

CREATE INDEX IF NOT EXISTS idx_streaming_views_watched_at ON streaming_views (watched_at DESC);
CREATE INDEX IF NOT EXISTS idx_streaming_views_provider ON streaming_views (provider);

INSERT INTO data_sources (name, type, base_url, account, is_active, sort_order, short_name)
SELECT 'Netflix', 'netflix', 'https://www.netflix.com', NULL, TRUE,
       COALESCE((SELECT MAX(sort_order) FROM data_sources s2), 0) + 1,
       'netflix'
WHERE NOT EXISTS (SELECT 1 FROM data_sources WHERE type = 'netflix');

INSERT INTO data_sources (name, type, base_url, account, is_active, sort_order, short_name)
SELECT 'Amazon Prime Video', 'prime', 'https://www.primevideo.com', NULL, TRUE,
       COALESCE((SELECT MAX(sort_order) FROM data_sources s2), 0) + 1,
       'prime'
WHERE NOT EXISTS (SELECT 1 FROM data_sources WHERE type = 'prime');

SELECT id, name, type, sort_order, short_name FROM data_sources WHERE type IN ('netflix', 'prime') ORDER BY type;

-- postgres で作成すると所有者が postgres のままになり、アプリユーザーが書けないため
-- （DB ユーザー名が planet でない場合は置き換え）
ALTER TABLE streaming_views OWNER TO planet;
ALTER SEQUENCE streaming_views_id_seq OWNER TO planet;
