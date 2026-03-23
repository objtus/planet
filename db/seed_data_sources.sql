-- data_sources 初期データ
-- pon.icuは登録しない（next_tasks.md記載）

INSERT INTO data_sources (name, type, base_url, account, is_active) VALUES
    ('misskey.io @yuinoid',          'misskey',  'https://misskey.io',       '@yuinoid',           TRUE),
    ('tanoshii.site @health',        'misskey',  'https://tanoshii.site',    '@health',            TRUE),
    ('mistodon.cloud @healthcare',   'mastodon', 'https://mistodon.cloud',   '@healthcare',        TRUE),
    ('Last.fm objtus',               'lastfm',   NULL,                       'objtus',             TRUE),
    ('yuinoid.neocities.org RSS',    'rss',      NULL,                       'yuinoid.neocities.org/rss.xml', TRUE),
    ('YouTube',                      'youtube',  NULL,                       NULL,                 TRUE),
    ('OpenWeatherMap',               'weather',  NULL,                       NULL,                 TRUE),
    ('GitHub',                       'github',   NULL,                       NULL,                 TRUE),
    ('iPhone ヘルス',                'health',   NULL,                       NULL,                 TRUE),
    ('iPhone 写真',                  'photo',    NULL,                       NULL,                 TRUE);
