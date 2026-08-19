"""
Check which expected columns actually exist in each table.
Uses SELECT to detect missing columns precisely (no writes needed).
"""
import sys, re, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from app.services.supabase_service import _get_client

client = _get_client()

expected = {
    'datasets':            ['id','name','original_filename','sheet_name','total_rows',
                            'total_columns','current_version_id','status','created_at','updated_at'],
    'dataset_versions':    ['id','dataset_id','version_number','version_type','label',
                            'user_command','agent_action','rows_before','rows_after',
                            'columns_affected','processing_summary','storage_path_excel',
                            'storage_path_csv','storage_url_excel','storage_url_csv',
                            'parent_version_id','is_current','created_at'],
    'dataset_files':       ['id','dataset_id','version_id','file_type','bucket_name',
                            'storage_path','public_url','file_size_bytes',
                            'original_filename','version_type','created_at'],
    'cleaning_operations': ['id','dataset_id','version_id','duplicates_found',
                            'duplicates_removed','blank_rows_found','blank_rows_removed',
                            'empty_columns_removed','whitespace_fixed','columns_modified',
                            'missing_values_count','issues_remaining','cleaning_required',
                            'cleaning_summary','created_at'],
    'agent_actions':       ['id','dataset_id','version_id','user_command','intent',
                            'tool_used','tool_params','result_summary','rows_before',
                            'rows_after','success','error_message','created_at'],
    'insights':            ['id','dataset_id','version_id','insight_text','insight_type',
                            'stats_snapshot','created_at'],
    'reports':             ['id','dataset_id','version_id','report_name','report_data','created_at'],
}

print("Checking columns in each table...\n")
all_missing = {}

for table, cols in expected.items():
    missing = []
    present = []
    for col in cols:
        try:
            client.table(table).select(col).limit(1).execute()
            present.append(col)
        except Exception as e:
            msg = str(e)
            if '42703' in msg or 'does not exist' in msg or 'PGRST204' in msg:
                missing.append(col)
            else:
                present.append(col + '(?)')

    if missing:
        all_missing[table] = missing
        print(f"  {table}:")
        print(f"    present : {present}")
        print(f"    MISSING : {missing}")
    else:
        print(f"  {table}: OK ({len(present)} columns)")
    print()

print("=" * 55)
if not all_missing:
    print("ALL COLUMNS PRESENT. Schema is complete.")
    print("\nRun: python check_conn.py  then  python wsgi.py")
else:
    total_missing = sum(len(v) for v in all_missing.values())
    print(f"MISSING: {total_missing} columns across {len(all_missing)} tables")
    print("\nPlease run add_missing_columns.sql in:")
    print("https://supabase.com/dashboard/project/rpzjuqdkswaaalxmamjr/sql")
