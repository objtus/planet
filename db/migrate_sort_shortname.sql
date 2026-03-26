-- data_sources に sort_order・short_name 列を追加
ALTER TABLE data_sources
  ADD COLUMN IF NOT EXISTS sort_order integer,
  ADD COLUMN IF NOT EXISTS short_name  varchar(32);

-- sort_order を id 順の連番で初期化
WITH ranked AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
  FROM data_sources
)
UPDATE data_sources
   SET sort_order = ranked.rn
  FROM ranked
 WHERE data_sources.id = ranked.id
   AND data_sources.sort_order IS NULL;

ALTER TABLE data_sources ALTER COLUMN sort_order SET NOT NULL;
ALTER TABLE data_sources ALTER COLUMN sort_order SET DEFAULT 999;

-- 確認
SELECT id, name, sort_order, short_name FROM data_sources ORDER BY sort_order;
