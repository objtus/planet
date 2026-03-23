-- 追加アカウント（next_tasks.md・decisions.md より）
INSERT INTO data_sources (name, type, base_url, account, is_active) VALUES
    ('misskey.io @vknsq',        'misskey',  'https://misskey.io',     '@vknsq',   TRUE),
    ('msk.ilnk.info @google',    'misskey',  'https://msk.ilnk.info',  '@google',  TRUE),
    ('sushi.ski @idoko',         'misskey',  'https://sushi.ski',      '@idoko',   TRUE),
    ('mastodon.cloud @objtus',   'mastodon', 'https://mastodon.cloud', '@objtus',  TRUE);
