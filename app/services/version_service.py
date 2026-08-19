"""
Version Service
---------------
Manages the full lifecycle of dataset versions.
Each version type is stored in its own Supabase Storage bucket:
  original-files   → version_type = 'original'
  cleaned-files    → version_type = 'auto_cleaned'
  agent-files      → version_type = 'agent_processed'

Every file upload also saves a record to dataset_files table.
Original data is NEVER modified or overwritten.
"""

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from app.services import supabase_service as sb
from app.services.excel_service import df_to_excel_bytes, df_to_csv_bytes

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _storage_paths(dataset_id: str, version_id: str, label: str) -> Tuple[str, str]:
    """Build the storage path pair (excel, csv) for a version."""
    safe = label.replace(' ', '_').replace('/', '-').replace('—', '-')[:40]
    base = f"{dataset_id}/{version_id}_{safe}"
    return f"{base}.xlsx", f"{base}.csv"


def _bucket_for(version_type: str) -> str:
    """Return the correct bucket name for a version type."""
    return sb.BUCKET_FOR_TYPE.get(version_type, sb.BUCKET_ORIGINAL)


def _upload_version_files(
    dataset_id: str,
    version_id: str,
    version_type: str,
    df: pd.DataFrame,
    sheet_name: str,
    label: str,
    original_filename: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Upload Excel + CSV for a version to the correct bucket.
    Returns (excel_path, csv_path, excel_url, csv_url).
    Also saves records to dataset_files table.
    """
    bucket      = _bucket_for(version_type)
    excel_path, csv_path = _storage_paths(dataset_id, version_id, label)

    excel_bytes = df_to_excel_bytes(df, sheet_name=sheet_name)
    csv_bytes   = df_to_csv_bytes(df)

    excel_url = sb.upload_to_bucket(
        bucket, excel_path, excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    csv_url = sb.upload_to_bucket(
        bucket, csv_path, csv_bytes,
        content_type='text/csv',
    )

    # Save file references to dataset_files table
    for ftype, path, url, size in (
        ('excel', excel_path, excel_url, len(excel_bytes)),
        ('csv',   csv_path,   csv_url,   len(csv_bytes)),
    ):
        try:
            sb.save_file_record({
                'id':                str(uuid.uuid4()),
                'dataset_id':        dataset_id,
                'version_id':        version_id,
                'file_type':         ftype,
                'bucket_name':       bucket,
                'storage_path':      path,
                'public_url':        url,
                'file_size_bytes':   size,
                'original_filename': original_filename,
                'version_type':      version_type,
                'created_at':        _now(),
            })
        except Exception as exc:
            logger.warning('Could not save file record (%s): %s', ftype, exc)

    return excel_path, csv_path, excel_url, csv_url


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def create_original_version(
    dataset_id: str,
    df: pd.DataFrame,
    sheet_name: str,
    original_filename: str,
) -> Dict[str, Any]:
    """
    Persist the ORIGINAL unmodified DataFrame as Version 1.
    Bucket: original-files
    This version is NEVER overwritten.
    """
    version_id   = str(uuid.uuid4())
    version_type = 'original'
    label        = 'Original Upload'

    excel_path, csv_path, excel_url, csv_url = _upload_version_files(
        dataset_id, version_id, version_type, df, sheet_name, label, original_filename
    )

    record = {
        'id':                 version_id,
        'dataset_id':         dataset_id,
        'version_number':     1,
        'version_type':       version_type,
        'label':              f'Original Upload — {original_filename}',
        'user_command':       None,
        'agent_action':       None,
        'rows_before':        len(df),
        'rows_after':         len(df),
        'columns_affected':   0,
        'processing_summary': 'Original uploaded file. Unmodified.',
        'storage_path_excel': excel_path,
        'storage_path_csv':   csv_path,
        'storage_url_excel':  excel_url,
        'storage_url_csv':    csv_url,
        'parent_version_id':  None,
        'is_current':         True,
        'created_at':         _now(),
    }
    version = sb.create_version(record)
    sb.update_dataset(dataset_id, {'current_version_id': version_id})
    return version


def create_cleaned_version(
    dataset_id: str,
    parent_version_id: str,
    df_original: pd.DataFrame,
    df_cleaned: pd.DataFrame,
    sheet_name: str,
    cleaning_report: Dict[str, Any],
    original_filename: str = '',
) -> Dict[str, Any]:
    """
    Persist Version 2 — auto_cleaned.
    Bucket: cleaned-files
    If no cleaning was needed df_cleaned == df_original (no data change).
    Parent version (original) is NEVER modified.
    """
    version_id   = str(uuid.uuid4())
    version_type = 'automatic_cleaned'

    if cleaning_report.get('cleaning_required'):
        label   = 'Automatic Cleaning'
        summary = cleaning_report.get('status', 'Automatic cleaning completed.')
    else:
        label   = 'No Cleaning Required'
        summary = 'Data is already clean. No changes were made.'

    excel_path, csv_path, excel_url, csv_url = _upload_version_files(
        dataset_id, version_id, version_type, df_cleaned, sheet_name, label, original_filename
    )

    record = {
        'id':                 version_id,
        'dataset_id':         dataset_id,
        'version_number':     2,
        'version_type':       version_type,
        'label':              label,
        'user_command':       None,
        'agent_action':       'automatic_cleaning',
        'rows_before':        cleaning_report.get('original_rows', len(df_original)),
        'rows_after':         cleaning_report.get('final_rows',    len(df_cleaned)),
        'columns_affected':   cleaning_report.get('columns_modified_count', 0),
        'processing_summary': summary,
        'storage_path_excel': excel_path,
        'storage_path_csv':   csv_path,
        'storage_url_excel':  excel_url,
        'storage_url_csv':    csv_url,
        'parent_version_id':  parent_version_id,
        'is_current':         True,
        'created_at':         _now(),
    }
    version = sb.create_version(record)
    sb.update_dataset(dataset_id, {'current_version_id': version_id})
    return version


def create_agent_version(
    dataset_id: str,
    parent_version_id: str,
    parent_version_number: int,
    df_processed: pd.DataFrame,
    df_before: pd.DataFrame,
    sheet_name: str,
    user_command: str,
    agent_action: str,
    columns_affected: int,
    processing_summary: str,
    original_filename: str = '',
) -> Dict[str, Any]:
    """
    Persist an Agent-processed DataFrame as a new version.
    Bucket: agent-files
    version_number = parent + 1.
    Previous version is NEVER modified.
    """
    version_id     = str(uuid.uuid4())
    version_number = parent_version_number + 1
    version_type   = 'agent_processed'
    label          = f'AI Agent — {user_command[:60]}'

    excel_path, csv_path, excel_url, csv_url = _upload_version_files(
        dataset_id, version_id, version_type,
        df_processed, sheet_name, f'agent_v{version_number}',
        original_filename,
    )

    record = {
        'id':                 version_id,
        'dataset_id':         dataset_id,
        'version_number':     version_number,
        'version_type':       version_type,
        'label':              label,
        'user_command':       user_command,
        'agent_action':       agent_action,
        'rows_before':        len(df_before),
        'rows_after':         len(df_processed),
        'columns_affected':   columns_affected,
        'processing_summary': processing_summary,
        'storage_path_excel': excel_path,
        'storage_path_csv':   csv_path,
        'storage_url_excel':  excel_url,
        'storage_url_csv':    csv_url,
        'parent_version_id':  parent_version_id,
        'is_current':         True,
        'created_at':         _now(),
    }
    version = sb.create_version(record)
    sb.update_dataset(dataset_id, {'current_version_id': version_id})
    return version


# ══════════════════════════════════════════════════════════════════════════════
# LOAD a version's DataFrame from storage
# ══════════════════════════════════════════════════════════════════════════════

def load_version_dataframe(version: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    Download the Excel file for a version from Supabase Storage.
    Tries the version's own bucket first, then falls back to all buckets.
    Returns a DataFrame or None on failure.
    """
    storage_path = version.get('storage_path_excel')
    if not storage_path:
        logger.error('load_version_dataframe: no storage_path_excel in version %s', version.get('id'))
        return None

    # Determine correct bucket from version_type
    version_type   = version.get('version_type', 'original')
    primary_bucket = _bucket_for(version_type)

    # Try primary bucket
    file_bytes = sb.download_from_bucket(primary_bucket, storage_path)

    # Fall back to all three buckets if primary fails
    if file_bytes is None:
        for b in (sb.BUCKET_ORIGINAL, sb.BUCKET_CLEANED, sb.BUCKET_AGENT):
            if b == primary_bucket:
                continue
            file_bytes = sb.download_from_bucket(b, storage_path)
            if file_bytes is not None:
                break

    if file_bytes is None:
        logger.error('load_version_dataframe: file not found in any bucket: %s', storage_path)
        return None

    try:
        buf = io.BytesIO(file_bytes)
        return pd.read_excel(buf, engine='openpyxl', dtype=str)
    except Exception as exc:
        logger.error('load_version_dataframe: parse error: %s', exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def get_version_history(dataset_id: str) -> list:
    """Return all versions for a dataset with rows_delta enrichment."""
    versions = sb.list_versions(dataset_id)
    for v in versions:
        v['rows_delta'] = (v.get('rows_after') or 0) - (v.get('rows_before') or 0)
    return versions
