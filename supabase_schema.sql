-- ============================================================
-- AI-Powered Excel Data Intelligence Platform
-- Supabase Database Schema
-- Run this in the Supabase SQL editor to initialise the schema.
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ────────────────────────────────────────────────────────────
-- 1. datasets
--    One record per uploaded Excel workbook.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS datasets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                TEXT NOT NULL,
    original_filename   TEXT NOT NULL,
    sheet_name          TEXT,
    total_rows          INTEGER DEFAULT 0,
    total_columns       INTEGER DEFAULT 0,
    current_version_id  UUID,                 -- FK filled after first version created
    status              TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 2. dataset_versions
--    One record per state of the data (original, cleaned, agent-processed).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dataset_versions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id          UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_number      INTEGER NOT NULL,
    version_type        TEXT NOT NULL CHECK (version_type IN ('original', 'auto_cleaned', 'agent_processed')),
    label               TEXT NOT NULL,
    user_command        TEXT,
    agent_action        TEXT,
    rows_before         INTEGER DEFAULT 0,
    rows_after          INTEGER DEFAULT 0,
    columns_affected    INTEGER DEFAULT 0,
    processing_summary  TEXT,
    -- Supabase Storage paths (relative path within the bucket)
    storage_path_excel  TEXT,
    storage_path_csv    TEXT,
    -- Full public URLs (convenient for direct downloads)
    storage_url_excel   TEXT,
    storage_url_csv     TEXT,
    parent_version_id   UUID REFERENCES dataset_versions(id),
    is_current          BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure only one current version per dataset at DB level
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_current_version
    ON dataset_versions(dataset_id)
    WHERE is_current = TRUE;

-- ────────────────────────────────────────────────────────────
-- 3. cleaning_operations
--    Records what was found and fixed during automatic cleaning.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cleaning_operations (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id              UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_id              UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    duplicates_found        INTEGER DEFAULT 0,
    duplicates_removed      INTEGER DEFAULT 0,
    blank_rows_found        INTEGER DEFAULT 0,
    blank_rows_removed      INTEGER DEFAULT 0,
    empty_columns_removed   INTEGER DEFAULT 0,
    whitespace_fixed        INTEGER DEFAULT 0,
    columns_modified        INTEGER DEFAULT 0,
    missing_values_count    INTEGER DEFAULT 0,
    issues_remaining        INTEGER DEFAULT 0,
    cleaning_required       BOOLEAN DEFAULT FALSE,
    cleaning_summary        TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 4. agent_actions
--    Records every AI Agent command and what tool it invoked.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_actions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id      UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    user_command    TEXT NOT NULL,
    intent          TEXT,
    tool_used       TEXT NOT NULL,
    tool_params     JSONB DEFAULT '{}',
    result_summary  TEXT,
    rows_before     INTEGER DEFAULT 0,
    rows_after      INTEGER DEFAULT 0,
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 5. insights
--    AI-generated insights per dataset version.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS insights (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id      UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    insight_text    TEXT NOT NULL,
    insight_type    TEXT DEFAULT 'general',
    stats_snapshot  JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 6. reports
--    Saved report metadata (the full report is generated on demand).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id      UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    report_name     TEXT,
    report_data     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- Helpful indexes
-- ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_versions_dataset    ON dataset_versions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_cleaning_dataset    ON cleaning_operations(dataset_id);
CREATE INDEX IF NOT EXISTS idx_agent_dataset       ON agent_actions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_insights_dataset    ON insights(dataset_id);
CREATE INDEX IF NOT EXISTS idx_reports_dataset     ON reports(dataset_id);

-- ────────────────────────────────────────────────────────────
-- updated_at trigger for datasets
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_datasets_updated_at ON datasets;
CREATE TRIGGER set_datasets_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ────────────────────────────────────────────────────────────
-- Storage bucket
-- (Create the bucket via Supabase Dashboard or the Storage API;
--  the name used by the application is: dataset-files)
-- ────────────────────────────────────────────────────────────
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('dataset-files', 'dataset-files', true)
-- ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- END OF SCHEMA
-- ============================================================
