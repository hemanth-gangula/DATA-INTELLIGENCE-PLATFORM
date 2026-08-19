-- ================================================================
-- FIX: Row Level Security policies for DATA-INTLLIGENCE-PLATFORM
-- Run this ONCE in your Supabase SQL Editor:
-- https://supabase.com/dashboard/project/rpzjuqdkswaaalxmamjr/sql
-- ================================================================

-- Enable RLS on all tables (safe - no-op if already enabled)
ALTER TABLE datasets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_versions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_files       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cleaning_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_actions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights            ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports             ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (avoid duplicates)
DROP POLICY IF EXISTS "allow_all_datasets"   ON datasets;
DROP POLICY IF EXISTS "allow_all_versions"   ON dataset_versions;
DROP POLICY IF EXISTS "allow_all_files"      ON dataset_files;
DROP POLICY IF EXISTS "allow_all_cleaning"   ON cleaning_operations;
DROP POLICY IF EXISTS "allow_all_agent"      ON agent_actions;
DROP POLICY IF EXISTS "allow_all_insights"   ON insights;
DROP POLICY IF EXISTS "allow_all_reports"    ON reports;

-- Create permissive policies (allow all operations for the anon role)
CREATE POLICY "allow_all_datasets"   ON datasets            FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_versions"   ON dataset_versions    FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_files"      ON dataset_files       FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_cleaning"   ON cleaning_operations FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_agent"      ON agent_actions       FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_insights"   ON insights            FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_reports"    ON reports             FOR ALL TO anon USING (true) WITH CHECK (true);

-- Storage bucket policies (allow anon to upload/download)
INSERT INTO storage.buckets (id, name, public)
VALUES
  ('original-files', 'original-files', true),
  ('cleaned-files',  'cleaned-files',  true),
  ('agent-files',    'agent-files',    true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Storage RLS policies
DROP POLICY IF EXISTS "allow_all_original" ON storage.objects;
DROP POLICY IF EXISTS "allow_all_cleaned"  ON storage.objects;
DROP POLICY IF EXISTS "allow_all_agent"    ON storage.objects;

CREATE POLICY "allow_all_storage" ON storage.objects
  FOR ALL TO anon
  USING (bucket_id IN ('original-files','cleaned-files','agent-files'))
  WITH CHECK (bucket_id IN ('original-files','cleaned-files','agent-files'));

-- ================================================================
-- After running this SQL:
-- 1. Restart server: python wsgi.py
-- 2. Open:  http://localhost:5000/api/health  -> "overall_ok": true
-- 3. Open:  http://localhost:5000
-- ================================================================
