"""
Export Service
--------------
Handles generating Excel and CSV downloads from version storage.
Supports both direct Supabase URL redirects and in-memory generation
as fallback when the storage URL is not yet available.
"""

import io
import logging
from typing import Optional, Tuple

import pandas as pd

from app.services import supabase_service as sb
from app.services.excel_service import df_to_excel_bytes, df_to_csv_bytes
from app.services.version_service import load_version_dataframe

logger = logging.getLogger(__name__)


def get_excel_bytes_for_version(
    dataset_id: str,
    version_id: Optional[str] = None,
) -> Tuple[Optional[bytes], str]:
    """
    Return (excel_bytes, filename) for a given version.
    Tries Supabase storage first; falls back to in-memory generation.
    """
    version = _resolve_version(dataset_id, version_id)
    if not version:
        return None, 'download.xlsx'

    filename = _make_filename(version, 'xlsx')

    # Try storage path — use bucket-aware download
    storage_path = version.get('storage_path_excel')
    if storage_path:
        bucket     = sb.BUCKET_FOR_TYPE.get(version.get('version_type', 'original'), sb.BUCKET_ORIGINAL)
        file_bytes = sb.download_from_bucket(bucket, storage_path)
        if not file_bytes:
            # Fall back: try all buckets
            file_bytes = sb.download_file_from_storage(storage_path)
        if file_bytes:
            return file_bytes, filename

    # Fallback: regenerate from DataFrame
    df = load_version_dataframe(version)
    if df is None:
        return None, filename

    return df_to_excel_bytes(df), filename


def get_csv_bytes_for_version(
    dataset_id: str,
    version_id: Optional[str] = None,
) -> Tuple[Optional[bytes], str]:
    """
    Return (csv_bytes, filename) for a given version.
    """
    version = _resolve_version(dataset_id, version_id)
    if not version:
        return None, 'download.csv'

    filename = _make_filename(version, 'csv')

    # Try storage path — use bucket-aware download
    storage_path = version.get('storage_path_csv')
    if storage_path:
        bucket     = sb.BUCKET_FOR_TYPE.get(version.get('version_type', 'original'), sb.BUCKET_ORIGINAL)
        file_bytes = sb.download_from_bucket(bucket, storage_path)
        if not file_bytes:
            file_bytes = sb.download_file_from_storage(storage_path)
        if file_bytes:
            return file_bytes, filename

    # Fallback: regenerate from DataFrame
    df = load_version_dataframe(version)
    if df is None:
        return None, filename

    return df_to_csv_bytes(df), filename


def get_download_urls_for_version(
    dataset_id: str,
    version_id: Optional[str] = None,
) -> dict:
    """Return the Supabase public URLs for a version's Excel and CSV files."""
    version = _resolve_version(dataset_id, version_id)
    if not version:
        return {'excel_url': None, 'csv_url': None}
    return {
        'excel_url': version.get('storage_url_excel'),
        'csv_url':   version.get('storage_url_csv'),
        'version_id': version.get('id'),
        'version_number': version.get('version_number'),
        'label': version.get('label'),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_version(dataset_id: str, version_id: Optional[str]):
    if version_id:
        return sb.get_version(version_id)
    return sb.get_current_version(dataset_id)


def _make_filename(version: dict, ext: str) -> str:
    label = version.get('label', 'data')
    safe  = ''.join(c if c.isalnum() or c in '-_' else '_' for c in label)[:50]
    v_num = version.get('version_number', 1)
    return f"v{v_num}_{safe}.{ext}"
