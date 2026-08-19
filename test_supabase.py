"""
Supabase Integration Test
Run after updating SUPABASE_KEY in .env:
    python test_supabase.py

Verifies every part of the Supabase integration:
  DB tables, storage buckets, write permissions,
  full upload-clean-agent version lifecycle.
"""

import io
import os
import sys
import uuid
import json
import tempfile
from datetime import datetime, timezone

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(__file__))

PASS  = '\033[92m  PASS\033[0m'
FAIL  = '\033[91m  FAIL\033[0m'
WARN  = '\033[93m  WARN\033[0m'
BLOCK = '\033[93m  BLOCKED\033[0m'

results = []


def check(label: str, ok: bool, detail: str = ''):
    icon = PASS if ok else FAIL
    line = f'{icon}  {label}'
    if detail:
        line += f'\n       {detail}'
    print(line)
    results.append((label, ok))
    return ok


def section(title: str):
    print(f'\n{"─"*60}')
    print(f'  {title}')
    print('─'*60)


# ── 0. Pre-flight ──────────────────────────────────────────────────
section('0. Environment')
url = os.environ.get('SUPABASE_URL', '')
key = os.environ.get('SUPABASE_KEY', '')
groq_key = os.environ.get('GROQ_API_KEY', '')

check('SUPABASE_URL set', bool(url))
check('SUPABASE_URL format (no /rest/v1/)', '/rest/v1' not in url and url.startswith('https://'),
      f'Got: {url}')
check('SUPABASE_KEY set', bool(key))

key_is_jwt = key.startswith('eyJ')
key_is_pub = key.startswith('sb_publishable')
if key_is_jwt:
    check('SUPABASE_KEY is JWT (anon/service_role)', True)
elif key_is_pub:
    check('SUPABASE_KEY is JWT (anon/service_role)', False,
          'Current key is sb_publishable — replace with anon or service_role key')
else:
    check('SUPABASE_KEY type recognisable', False, f'Unknown format: {key[:15]}...')

check('GROQ_API_KEY set', bool(groq_key) and groq_key != 'your_groq_api_key_here')

# ── 1. Client ──────────────────────────────────────────────────────
section('1. Supabase client')
try:
    from app.services.supabase_service import _get_client, BUCKET_ORIGINAL, BUCKET_CLEANED, BUCKET_AGENT
    client = _get_client()
    check('Client created', True)
except Exception as e:
    check('Client created', False, str(e)[:120])
    print('\nCannot continue without a working client.')
    sys.exit(1)

# ── 2. Tables ──────────────────────────────────────────────────────
section('2. Database tables (SELECT)')
for table in ['datasets', 'dataset_versions', 'dataset_files',
              'cleaning_operations', 'agent_actions', 'insights', 'reports']:
    try:
        client.table(table).select('id').limit(1).execute()
        check(f'Table readable: {table}', True)
    except Exception as e:
        check(f'Table readable: {table}', False, str(e)[:100])

# ── 3. Storage buckets ─────────────────────────────────────────────
section('3. Storage buckets (list probe)')
for bucket in [BUCKET_ORIGINAL, BUCKET_CLEANED, BUCKET_AGENT]:
    try:
        client.storage.from_(bucket).list()
        check(f'Bucket exists + readable: {bucket}', True)
    except Exception as e:
        check(f'Bucket exists + readable: {bucket}', False, str(e)[:100])

# ── 4. Write permissions ───────────────────────────────────────────
section('4. Write permissions')

# DB write
test_id = str(uuid.uuid4())
db_write_ok = False
try:
    client.table('datasets').insert({
        'id': test_id,
        'name': '__integration_test__',
        'original_filename': 'test.xlsx',
    }).execute()
    client.table('datasets').delete().eq('id', test_id).execute()
    check('DB INSERT + DELETE (datasets)', True)
    db_write_ok = True
except Exception as e:
    msg = str(e)
    if 'security policy' in msg or '42501' in msg:
        print(f'{BLOCK}  DB INSERT (RLS blocking) — needs anon/service_role key or RLS policies')
    else:
        check('DB INSERT (datasets)', False, msg[:120])

# Storage write — all 3 buckets
storage_ok = {}
for bucket in [BUCKET_ORIGINAL, BUCKET_CLEANED, BUCKET_AGENT]:
    probe_path = f'_integration_test_{uuid.uuid4().hex[:8]}.txt'
    try:
        client.storage.from_(bucket).upload(probe_path, b'probe', {'upsert': 'true'})
        client.storage.from_(bucket).remove([probe_path])
        check(f'Storage write+delete: {bucket}', True)
        storage_ok[bucket] = True
    except Exception as e:
        msg = str(e)
        if 'security policy' in msg or '403' in msg or 'Unauthorized' in msg:
            print(f'{BLOCK}  Storage write ({bucket}) — needs anon/service_role key or storage policies')
        else:
            check(f'Storage write: {bucket}', False, msg[:100])
        storage_ok[bucket] = False

# ── 5. Full pipeline (only when writes work) ──────────────────────
section('5. Full version lifecycle (skipped if writes blocked)')

if not db_write_ok or not all(storage_ok.values()):
    print(f'{WARN}  Skipping lifecycle test — write permissions not available with current key.')
    print('  Update SUPABASE_KEY to anon or service_role, then re-run this script.')
else:
    import pandas as pd
    from app.services.version_service import (
        create_original_version, create_cleaned_version,
        create_agent_version, load_version_dataframe,
    )
    from app.services import supabase_service as sb

    dataset_id = str(uuid.uuid4())
    df = pd.DataFrame({
        'Name':   ['Alice', 'Bob', 'Alice', '', None],
        'Sales':  [100, 200, 100, 0, 300],
        'Region': ['North', 'South', 'North', '', 'East'],
    })

    # Create dataset record
    try:
        sb.create_dataset({
            'id':                dataset_id,
            'name':              'integration_test',
            'original_filename': 'test.xlsx',
            'sheet_name':        'Sheet1',
            'total_rows':        len(df),
            'total_columns':     len(df.columns),
            'status':            'active',
            'created_at':        datetime.now(timezone.utc).isoformat(),
            'updated_at':        datetime.now(timezone.utc).isoformat(),
        })
        check('Create dataset record', True)
    except Exception as e:
        check('Create dataset record', False, str(e)[:120])
        sys.exit(1)

    # Version 1 — original
    try:
        v1 = create_original_version(dataset_id, df, 'Sheet1', 'test.xlsx')
        check('Create original version (v1) → original-files', True,
              f'id={v1["id"][:8]}... url={str(v1.get("storage_url_excel",""))[:60]}')
    except Exception as e:
        check('Create original version', False, str(e)[:120])
        sys.exit(1)

    # Version 2 — cleaned
    try:
        cleaning_report = {
            'cleaning_required': True, 'original_rows': 5, 'final_rows': 3,
            'columns_modified_count': 1, 'status': 'Automatic cleaning completed.'
        }
        df_clean = df.dropna().drop_duplicates().reset_index(drop=True)
        v2 = create_cleaned_version(dataset_id, v1['id'], df, df_clean, 'Sheet1',
                                    cleaning_report, 'test.xlsx')
        check('Create cleaned version (v2) → cleaned-files', True,
              f'id={v2["id"][:8]}... rows={v2["rows_after"]}')
    except Exception as e:
        check('Create cleaned version', False, str(e)[:120])

    # Version 3 — agent
    try:
        v3 = create_agent_version(
            dataset_id, v2['id'], 2, df_clean, df_clean,
            'Sheet1', 'Remove duplicates', 'remove_duplicates',
            0, 'Removed 2 duplicates.', 'test.xlsx'
        )
        check('Create agent version (v3) → agent-files', True,
              f'id={v3["id"][:8]}...')
    except Exception as e:
        check('Create agent version', False, str(e)[:120])

    # Load back from storage
    try:
        v1_loaded = load_version_dataframe(v1)
        check('Load v1 DataFrame from storage', v1_loaded is not None,
              f'shape={v1_loaded.shape if v1_loaded is not None else "None"}')
    except Exception as e:
        check('Load v1 DataFrame from storage', False, str(e)[:120])

    # Verify original unchanged
    try:
        v1_back = sb.get_version(v1['id'])
        original_still_v1 = v1_back['version_type'] == 'original' and v1_back['version_number'] == 1
        check('Original version (v1) still intact and unchanged', original_still_v1)
    except Exception as e:
        check('Original version intact', False, str(e)[:100])

    # Verify current version pointer updated to v3
    try:
        current = sb.get_current_version(dataset_id)
        check('Current version updated to v3', current and current['id'] == v3['id'])
    except Exception as e:
        check('Current version updated', False, str(e)[:100])

    # Cleanup test data
    try:
        client.table('datasets').delete().eq('id', dataset_id).execute()
    except Exception:
        pass

# ── 6. Groq connectivity ───────────────────────────────────────────
section('6. Groq AI connectivity')
if groq_key and groq_key != 'your_groq_api_key_here':
    try:
        from groq import Groq
        gc = Groq(api_key=groq_key)
        resp = gc.chat.completions.create(
            model='llama3-70b-8192',
            messages=[{'role':'user','content':'Reply with the single word: OK'}],
            max_tokens=5,
        )
        reply = resp.choices[0].message.content.strip()
        check('Groq API call succeeds', True, f'Response: {reply}')
    except Exception as e:
        check('Groq API call succeeds', False, str(e)[:120])
else:
    print(f'{WARN}  Groq key not configured — skipping.')

# ── Final summary ──────────────────────────────────────────────────
print(f'\n{"="*60}')
print('FINAL RESULTS')
print('='*60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f'  Passed: {passed}')
print(f'  Failed: {failed}')
print(f'  Total:  {len(results)}')

if failed > 0 and key_is_pub:
    print()
    print('─'*60)
    print('REQUIRED ACTION TO COMPLETE INTEGRATION:')
    print('─'*60)
    print()
    print('1. Open your Supabase project:')
    print('   https://supabase.com/dashboard/project/rpzjuqdkswaaalxmamjr')
    print()
    print('2. Go to:  Settings → API → Project API keys')
    print()
    print('3. Copy the "anon" key (or "service_role" for full access)')
    print('   It starts with: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...')
    print()
    print('4. Update .env:')
    print('   SUPABASE_KEY=eyJhbGci...your-actual-key...')
    print()
    print('5. Restart the server:  python wsgi.py')
    print()
    print('6. Re-run this test:    python test_supabase.py')
    print()
    print('7. Verify live:         http://localhost:5000/api/health')

sys.exit(0 if failed == 0 else 1)
