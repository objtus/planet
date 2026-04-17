-- サマライザー品質向上: summary_type 列の追加と UNIQUE 制約の張替え
-- 実行: psql -U <user> -d <dbname> -f db/migrate_summary_type.sql
--
-- 既存行は summary_type = 'full' として扱われる（DEFAULT 値）
-- ON CONFLICT 節も (period_type, period_start, summary_type) に更新が必要

ALTER TABLE summaries
    ADD COLUMN IF NOT EXISTS summary_type TEXT NOT NULL DEFAULT 'full';

-- 既存制約を削除して新しい 3 列 UNIQUE に張り替える
ALTER TABLE summaries
    DROP CONSTRAINT IF EXISTS summaries_period_type_period_start_key;

ALTER TABLE summaries
    DROP CONSTRAINT IF EXISTS summaries_unique;

ALTER TABLE summaries
    ADD CONSTRAINT summaries_unique
    UNIQUE (period_type, period_start, summary_type);
