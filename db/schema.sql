-- Planet DB Schema
-- Section 5 of docs/design.md

-- 5-0. data_sources
CREATE TABLE data_sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    base_url    TEXT,
    account     TEXT,
    config      JSONB,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 5-1. logs（統合タイムライン）
CREATE TABLE logs (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INT REFERENCES data_sources(id),
    original_id   TEXT,
    content       TEXT,
    url           TEXT,
    metadata      JSONB,
    is_deleted    BOOLEAN DEFAULT FALSE,
    timestamp     TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source_id, original_id)
);

CREATE INDEX idx_logs_timestamp   ON logs (timestamp DESC);
CREATE INDEX idx_logs_source_id   ON logs (source_id);
CREATE INDEX idx_logs_metadata    ON logs USING GIN (metadata);
CREATE INDEX idx_logs_content_fts ON logs USING GIN (content gin_bigm_ops);

-- 5-2. misskey_posts
CREATE TABLE misskey_posts (
    id             BIGSERIAL PRIMARY KEY,
    log_id         BIGINT REFERENCES logs(id),
    source_id      INT REFERENCES data_sources(id),
    post_id        TEXT NOT NULL,
    text           TEXT,
    cw             TEXT,
    url            TEXT,
    reply_count    INT DEFAULT 0,
    renote_count   INT DEFAULT 0,
    reaction_count INT DEFAULT 0,
    has_files      BOOLEAN DEFAULT FALSE,
    visibility     TEXT,
    is_deleted     BOOLEAN DEFAULT FALSE,
    posted_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, post_id)
);

-- 5-3. mastodon_posts
CREATE TABLE mastodon_posts (
    id              BIGSERIAL PRIMARY KEY,
    log_id          BIGINT REFERENCES logs(id),
    source_id       INT REFERENCES data_sources(id),
    post_id         TEXT NOT NULL,
    content         TEXT,
    spoiler_text    TEXT,
    url             TEXT,
    reply_count     INT DEFAULT 0,
    reblog_count    INT DEFAULT 0,
    favourite_count INT DEFAULT 0,
    visibility      TEXT,
    is_deleted      BOOLEAN DEFAULT FALSE,
    posted_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, post_id)
);

-- 5-4. lastfm_plays
CREATE TABLE lastfm_plays (
    id          BIGSERIAL PRIMARY KEY,
    log_id      BIGINT REFERENCES logs(id),
    track_id    TEXT UNIQUE NOT NULL,
    artist      TEXT NOT NULL,
    track       TEXT NOT NULL,
    album       TEXT,
    url         TEXT,
    played_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_lastfm_artist ON lastfm_plays (artist);

-- 5-5. youtube_videos
CREATE TABLE youtube_videos (
    id             BIGSERIAL PRIMARY KEY,
    log_id         BIGINT REFERENCES logs(id),
    video_id       TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT,
    url            TEXT,
    duration_sec   INT,
    view_count     BIGINT DEFAULT 0,
    like_count     BIGINT DEFAULT 0,
    comment_count  BIGINT DEFAULT 0,
    published_at   TIMESTAMPTZ NOT NULL
);

-- 5-6. weather_daily
CREATE TABLE weather_daily (
    id            BIGSERIAL PRIMARY KEY,
    log_id        BIGINT REFERENCES logs(id),
    date          DATE UNIQUE NOT NULL,
    temp_max      NUMERIC(4,1),
    temp_min      NUMERIC(4,1),
    temp_avg      NUMERIC(4,1),
    weather_main  TEXT,
    weather_desc  TEXT,
    humidity      INT,
    location      TEXT
);

-- 5-7. github_activity
CREATE TABLE github_activity (
    id           BIGSERIAL PRIMARY KEY,
    log_id       BIGINT REFERENCES logs(id),
    event_id     TEXT UNIQUE NOT NULL,
    event_type   TEXT,
    repo_name    TEXT,
    url          TEXT,
    commit_count INT DEFAULT 0,
    summary      TEXT,
    occurred_at  TIMESTAMPTZ NOT NULL
);

-- 5-8. health_daily
CREATE TABLE health_daily (
    id                  BIGSERIAL PRIMARY KEY,
    log_id              BIGINT REFERENCES logs(id),
    date                DATE UNIQUE NOT NULL,
    steps               INT,
    active_calories     INT,
    heart_rate_avg      INT,
    heart_rate_max      INT,
    heart_rate_min      INT,
    exercise_minutes    INT,
    stand_hours         INT,
    photo_count         INT DEFAULT 0,
    photo_locations     JSONB
);

-- 5-9. rss_entries
CREATE TABLE rss_entries (
    id           BIGSERIAL PRIMARY KEY,
    log_id       BIGINT REFERENCES logs(id),
    entry_id     TEXT UNIQUE NOT NULL,
    title        TEXT,
    url          TEXT,
    summary      TEXT,
    published_at TIMESTAMPTZ NOT NULL
);

-- 5-10. url_metadata
CREATE TABLE url_metadata (
    id           BIGSERIAL PRIMARY KEY,
    url          TEXT UNIQUE NOT NULL,
    site_name    TEXT,
    title        TEXT,
    description  TEXT,
    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
    fetch_status INT DEFAULT 0,
    retry_count  INT DEFAULT 0
);

-- 5-11. summaries
CREATE TABLE summaries (
    id           BIGSERIAL PRIMARY KEY,
    period_type  TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end   DATE NOT NULL,
    week_number  INT,
    content      TEXT NOT NULL,
    model        TEXT,
    prompt_style TEXT DEFAULT 'hybrid',
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (period_type, period_start)
);
