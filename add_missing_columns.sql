-- ================================================================
-- ADD MISSING COLUMNS
-- Your tables exist but are missing some columns the app needs.
-- Run this ONCE in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/rpzjuqdkswaaalxmamjr/sql
-- Safe to run multiple times (IF NOT EXISTS).
-- ================================================================

-- datasets
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS sheet_name          TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS total_rows          INTEGER DEFAULT 0;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS total_columns       INTEGER DEFAULT 0;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS current_version_id  UUID;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS status              TEXT DEFAULT 'active';
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();

-- dataset_versions
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS version_number      INTEGER DEFAULT 1;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS version_type        TEXT DEFAULT 'original';
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS label               TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS user_command        TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS agent_action        TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS rows_before         INTEGER DEFAULT 0;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS rows_after          INTEGER DEFAULT 0;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS columns_affected    INTEGER DEFAULT 0;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS processing_summary  TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS storage_path_excel  TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS storage_path_csv    TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS storage_url_excel   TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS storage_url_csv     TEXT;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS parent_version_id   UUID;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS is_current          BOOLEAN DEFAULT FALSE;
ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();

-- dataset_files
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS version_id         UUID;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS file_type          TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS bucket_name        TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS storage_path       TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS public_url         TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS file_size_bytes    INTEGER DEFAULT 0;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS original_filename  TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS version_type       TEXT;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS created_at         TIMESTAMPTZ DEFAULT NOW();

-- cleaning_operations
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS version_id              UUID;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS duplicates_found        INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS duplicates_removed      INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS blank_rows_found        INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS blank_rows_removed      INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS empty_columns_removed   INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS whitespace_fixed        INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS columns_modified        INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS missing_values_count    INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS issues_remaining        INTEGER DEFAULT 0;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS cleaning_required       BOOLEAN DEFAULT FALSE;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS cleaning_summary        TEXT;
ALTER TABLE cleaning_operations ADD COLUMN IF NOT EXISTS created_at              TIMESTAMPTZ DEFAULT NOW();

-- agent_actions
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS version_id      UUID;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS intent          TEXT;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS tool_used       TEXT;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS tool_params     JSONB DEFAULT '{}'::jsonb;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS result_summary  TEXT;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rows_before     INTEGER DEFAULT 0;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rows_after      INTEGER DEFAULT 0;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS success         BOOLEAN DEFAULT TRUE;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS error_message   TEXT;
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ DEFAULT NOW();

-- insights
ALTER TABLE insights ADD COLUMN IF NOT EXISTS version_id      UUID;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS insight_text    TEXT;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS insight_type    TEXT DEFAULT 'auto';
ALTER TABLE insights ADD COLUMN IF NOT EXISTS stats_snapshot  JSONB DEFAULT '{}'::jsonb;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ DEFAULT NOW();

-- reports
ALTER TABLE reports ADD COLUMN IF NOT EXISTS version_id    UUID;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_name   TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_data   JSONB DEFAULT '{}'::jsonb;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ DEFAULT NOW();

-- ================================================================
-- After running: come back and say "done" - app will start
-- ================================================================
