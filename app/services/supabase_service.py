"""
Supabase Service  —  complete integration layer
------------------------------------------------
• Three separate storage buckets:
    original-files   → Version 1 (original upload)
    cleaned-files    → Version 2 (auto-cleaned)
    agent-files      → Version 3+ (agent-processed)
• dataset_files table tracks every file reference
• is_current unique constraint handled via two-step update
• SUPABASE_URL must be the bare project URL:
    https://<ref>.supabase.co   (NO /rest/v1/ suffix)
• SUPABASE_KEY must be the anon or service_role key from
    Supabase Dashboard → Settings → API → Project API keys
"""

import os
import logging
import json
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── Table names ────────────────────────────────────────────────────────────────
DATASETS_TABLE        = 'datasets'
VERSIONS_TABLE        = 'dataset_versions'
FILES_TABLE           = 'dataset_files'
CLEANING_TABLE        = 'cleaning_operations'
AGENT_ACTIONS_TABLE   = 'agent_actions'
INSIGHTS_TABLE        = 'insights'
REPORTS_TABLE         = 'reports'

# ── Storage bucket names (must match buckets created in Supabase Dashboard) ───
BUCKET_ORIGINAL = 'original-files'
BUCKET_CLEANED  = 'cleaned-files'
BUCKET_AGENT    = 'agent-files'

# Map version_type → bucket
BUCKET_FOR_TYPE = {
    'original':          BUCKET_ORIGINAL,
    'automatic_cleaned': BUCKET_CLEANED,
    'agent_processed':   BUCKET_AGENT,
}


# ══════════════════════════════════════════════════════════════════════════════
# Client factory
# ══════════════════════════════════════════════════════════════════════════════

def _get_client():
    """
    Return an authenticated Supabase client (lazy, thread-safe init).
    Reads SUPABASE_URL and SUPABASE_KEY from environment only.
    """
    from supabase import create_client
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_KEY', '')

    if not url or not key:
        raise RuntimeError(
            'SUPABASE_URL and SUPABASE_KEY environment variables must be set.\n'
            'SUPABASE_URL  → https://<ref>.supabase.co  (no /rest/v1/ suffix)\n'
            'SUPABASE_KEY  → anon or service_role key from Supabase Dashboard → Settings → API'
        )
    # Guard against accidentally including /rest/v1 in the URL
    if '/rest/v1' in url:
        url = url.split('/rest/v1')[0]

    return create_client(url, key)


def _base_url() -> str:
    """Return the clean base Supabase project URL."""
    return os.environ.get('SUPABASE_URL', '').rstrip('/').split('/rest/v1')[0]


# ══════════════════════════════════════════════════════════════════════════════
# DATASETS
# ══════════════════════════════════════════════════════════════════════════════

def create_dataset(record: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new dataset record. Returns the inserted row."""
    try:
        client = _get_client()
        res = client.table(DATASETS_TABLE).insert(record).execute()
        if res.data:
            return res.data[0]
        raise RuntimeError('No data returned from dataset insert.')
    except Exception as exc:
        logger.error('create_dataset: %s', exc)
        raise


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    try:
        client = _get_client()
        res = (client.table(DATASETS_TABLE)
               .select('*').eq('id', dataset_id).single().execute())
        return res.data
    except Exception as exc:
        logger.error('get_dataset: %s', exc)
        return None


def list_datasets() -> List[Dict[str, Any]]:
    try:
        client = _get_client()
        res = (client.table(DATASETS_TABLE)
               .select('*').order('created_at', desc=True).execute())
        return res.data or []
    except Exception as exc:
        logger.error('list_datasets: %s', exc)
        return []


def update_dataset(dataset_id: str, updates: Dict[str, Any]) -> bool:
    try:
        _get_client().table(DATASETS_TABLE).update(updates).eq('id', dataset_id).execute()
        return True
    except Exception as exc:
        logger.error('update_dataset: %s', exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DATASET VERSIONS
# ══════════════════════════════════════════════════════════════════════════════

def create_version(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a dataset version.
    Handles the unique constraint on (dataset_id) WHERE is_current=TRUE by
    unsetting all existing current versions first, then inserting the new one.
    """
    try:
        client = _get_client()

        # If the new record wants to be current, clear the flag first so the
        # unique partial index doesn't fire.
        if record.get('is_current'):
            try:
                client.table(VERSIONS_TABLE)\
                    .update({'is_current': False})\
                    .eq('dataset_id', record['dataset_id'])\
                    .execute()
            except Exception as clr_exc:
                logger.warning('create_version: could not clear is_current: %s', clr_exc)

        res = client.table(VERSIONS_TABLE).insert(record).execute()
        if res.data:
            return res.data[0]
        raise RuntimeError('No data returned from version insert.')
    except Exception as exc:
        logger.error('create_version: %s', exc)
        raise


def get_version(version_id: str) -> Optional[Dict[str, Any]]:
    try:
        res = (_get_client().table(VERSIONS_TABLE)
               .select('*').eq('id', version_id).single().execute())
        return res.data
    except Exception as exc:
        logger.error('get_version: %s', exc)
        return None


def list_versions(dataset_id: str) -> List[Dict[str, Any]]:
    try:
        res = (_get_client().table(VERSIONS_TABLE)
               .select('*').eq('dataset_id', dataset_id)
               .order('version_number', desc=False).execute())
        return res.data or []
    except Exception as exc:
        logger.error('list_versions: %s', exc)
        return []


def get_current_version(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Return the version currently marked is_current=True for a dataset."""
    try:
        res = (_get_client().table(VERSIONS_TABLE)
               .select('*')
               .eq('dataset_id', dataset_id)
               .eq('is_current', True)
               .limit(1)
               .execute())
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning('get_current_version: %s', exc)
        return None


def mark_version_current(dataset_id: str, version_id: str) -> bool:
    """
    Atomically switch the current-version pointer.
    Step 1: unset all → Step 2: set target.
    This avoids the unique partial index violation.
    """
    try:
        client = _get_client()
        # Step 1 — clear all
        client.table(VERSIONS_TABLE)\
              .update({'is_current': False})\
              .eq('dataset_id', dataset_id)\
              .execute()
        # Step 2 — set target
        client.table(VERSIONS_TABLE)\
              .update({'is_current': True})\
              .eq('id', version_id)\
              .execute()
        return True
    except Exception as exc:
        logger.error('mark_version_current: %s', exc)
        return False


def update_version(version_id: str, updates: Dict[str, Any]) -> bool:
    try:
        _get_client().table(VERSIONS_TABLE).update(updates).eq('id', version_id).execute()
        return True
    except Exception as exc:
        logger.error('update_version: %s', exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DATASET FILES  (tracks every file stored in Supabase Storage)
# ══════════════════════════════════════════════════════════════════════════════

def save_file_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a record into dataset_files.
    Expected fields:
      id, dataset_id, version_id, file_type ('excel'|'csv'),
      bucket_name, storage_path, public_url, file_size_bytes,
      original_filename, version_type, created_at
    """
    try:
        client = _get_client()
        res = client.table(FILES_TABLE).insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as exc:
        logger.error('save_file_record: %s', exc)
        return {}


def get_file_records(dataset_id: str, version_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return file records for a dataset (optionally filtered by version)."""
    try:
        client = _get_client()
        q = client.table(FILES_TABLE).select('*').eq('dataset_id', dataset_id)
        if version_id:
            q = q.eq('version_id', version_id)
        return (q.order('created_at', desc=False).execute()).data or []
    except Exception as exc:
        logger.error('get_file_records: %s', exc)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# CLEANING OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def save_cleaning_operation(record: Dict[str, Any]) -> Dict[str, Any]:
    try:
        res = _get_client().table(CLEANING_TABLE).insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as exc:
        logger.error('save_cleaning_operation: %s', exc)
        return {}


def get_cleaning_operation(dataset_id: str) -> Optional[Dict[str, Any]]:
    try:
        res = (_get_client().table(CLEANING_TABLE)
               .select('*').eq('dataset_id', dataset_id)
               .order('created_at', desc=True).limit(1).execute())
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.error('get_cleaning_operation: %s', exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AGENT ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def save_agent_action(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save an agent action. tool_params must be JSON-serialisable.
    """
    try:
        # Ensure tool_params is serialisable
        if 'tool_params' in record and not isinstance(record['tool_params'], (dict, list)):
            record['tool_params'] = {}
        client = _get_client()
        res = client.table(AGENT_ACTIONS_TABLE).insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as exc:
        logger.error('save_agent_action: %s', exc)
        return {}


def list_agent_actions(dataset_id: str) -> List[Dict[str, Any]]:
    try:
        res = (_get_client().table(AGENT_ACTIONS_TABLE)
               .select('*').eq('dataset_id', dataset_id)
               .order('created_at', desc=False).execute())
        return res.data or []
    except Exception as exc:
        logger.error('list_agent_actions: %s', exc)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# INSIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def save_insight(record: Dict[str, Any]) -> Dict[str, Any]:
    try:
        res = _get_client().table(INSIGHTS_TABLE).insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as exc:
        logger.error('save_insight: %s', exc)
        return {}


def get_insights(dataset_id: str, version_id: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        client = _get_client()
        q = client.table(INSIGHTS_TABLE).select('*').eq('dataset_id', dataset_id)
        if version_id:
            q = q.eq('version_id', version_id)
        res = q.order('created_at', desc=True).limit(1).execute()
        return res.data or []
    except Exception as exc:
        logger.error('get_insights: %s', exc)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def save_report(record: Dict[str, Any]) -> Dict[str, Any]:
    try:
        res = _get_client().table(REPORTS_TABLE).insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as exc:
        logger.error('save_report: %s', exc)
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# STORAGE  —  three-bucket model
# ══════════════════════════════════════════════════════════════════════════════

def upload_to_bucket(
    bucket: str,
    storage_path: str,
    file_bytes: bytes,
    content_type: str = 'application/octet-stream',
) -> Optional[str]:
    """
    Upload file_bytes to the named bucket at storage_path.
    Returns the public URL on success, None on failure.
    """
    try:
        client = _get_client()
        client.storage.from_(bucket).upload(
            path=storage_path,
            file=file_bytes,
            file_options={'content-type': content_type, 'upsert': 'true'},
        )
        return _public_url(bucket, storage_path)
    except Exception as exc:
        logger.error('upload_to_bucket [%s/%s]: %s', bucket, storage_path, exc)
        return None


def download_from_bucket(bucket: str, storage_path: str) -> Optional[bytes]:
    """Download a file from the named bucket. Returns bytes or None."""
    try:
        return _get_client().storage.from_(bucket).download(storage_path)
    except Exception as exc:
        logger.error('download_from_bucket [%s/%s]: %s', bucket, storage_path, exc)
        return None


def upload_file_to_storage(
    file_bytes: bytes,
    storage_path: str,
    content_type: str = 'application/octet-stream',
    bucket: Optional[str] = None,
) -> Optional[str]:
    """
    Legacy-compatible upload helper.
    If bucket is provided use it; otherwise default to BUCKET_ORIGINAL.
    """
    target_bucket = bucket or BUCKET_ORIGINAL
    return upload_to_bucket(target_bucket, storage_path, file_bytes, content_type)


def download_file_from_storage(storage_path: str, bucket: Optional[str] = None) -> Optional[bytes]:
    """
    Legacy-compatible download helper.
    Tries buckets in order until one succeeds.
    """
    if bucket:
        return download_from_bucket(bucket, storage_path)
    # Try all three buckets in order
    for b in (BUCKET_ORIGINAL, BUCKET_CLEANED, BUCKET_AGENT):
        data = download_from_bucket(b, storage_path)
        if data is not None:
            return data
    return None


def get_public_url(storage_path: str, bucket: Optional[str] = None) -> str:
    """Return the public URL for a stored file."""
    b = bucket or BUCKET_ORIGINAL
    return _public_url(b, storage_path)


def _public_url(bucket: str, storage_path: str) -> str:
    base = _base_url()
    return f"{base}/storage/v1/object/public/{bucket}/{storage_path}"


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

def health_check() -> Dict[str, Any]:
    """
    Comprehensive connectivity check.
    Returns dict with keys: db, storage_original, storage_cleaned,
    storage_agent, overall_ok, errors.
    """
    result: Dict[str, Any] = {
        'db':               False,
        'storage_original': False,
        'storage_cleaned':  False,
        'storage_agent':    False,
        'overall_ok':       False,
        'errors':           [],
        'project_url':      _base_url(),
    }

    # DB check
    try:
        _get_client().table(DATASETS_TABLE).select('id').limit(1).execute()
        result['db'] = True
    except Exception as exc:
        result['errors'].append(f'DB: {exc}')

    # Storage checks — probe each bucket with a tiny file
    probe = b'healthcheck'
    probe_path = '_health_probe.txt'
    for bucket, key in (
        (BUCKET_ORIGINAL, 'storage_original'),
        (BUCKET_CLEANED,  'storage_cleaned'),
        (BUCKET_AGENT,    'storage_agent'),
    ):
        try:
            client = _get_client()
            client.storage.from_(bucket).upload(
                probe_path, probe, {'content-type': 'text/plain', 'upsert': 'true'}
            )
            client.storage.from_(bucket).remove([probe_path])
            result[key] = True
        except Exception as exc:
            result['errors'].append(f'{bucket}: {exc}')

    result['overall_ok'] = result['db'] and all(
        result[k] for k in ('storage_original', 'storage_cleaned', 'storage_agent')
    )
    return result
