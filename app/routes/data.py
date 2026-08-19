"""
Data Routes  —  /api/data/
Provides data preview, table data with pagination/sort/filter,
column metadata, and quality reports.
"""

import logging
from flask import Blueprint, request, jsonify

from app.services import supabase_service as sb
from app.services.version_service import load_version_dataframe
from app.services.excel_service   import build_preview, get_column_metadata, analyze_data_quality
from app.utils.helpers import error_response, serialize_value

data_bp = Blueprint('data', __name__)
logger  = logging.getLogger(__name__)


@data_bp.route('/preview/<dataset_id>', methods=['GET'])
def get_preview(dataset_id: str):
    """Return a paginated, searchable view of the current version data."""
    version_id = request.args.get('version_id')
    page       = max(1, int(request.args.get('page', 1)))
    per_page   = min(500, max(10, int(request.args.get('per_page', 50))))
    search     = request.args.get('search', '').strip()
    sort_col   = request.args.get('sort_col', '')
    sort_dir   = request.args.get('sort_dir', 'asc').lower()
    filter_col = request.args.get('filter_col', '')
    filter_val = request.args.get('filter_val', '')

    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('Version not found.', 404)), 404

    import pandas as pd
    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    # Apply search across all string columns
    if search:
        mask = df.apply(
            lambda col: col.astype(str).str.lower().str.contains(search.lower(), na=False)
        ).any(axis=1)
        df = df[mask]

    # Apply column filter
    if filter_col and filter_col in df.columns and filter_val:
        df = df[df[filter_col].astype(str).str.lower().str.contains(filter_val.lower(), na=False)]

    # Apply sort
    if sort_col and sort_col in df.columns:
        import pandas as pd
        numeric = pd.to_numeric(df[sort_col], errors='coerce')
        ascending = sort_dir != 'desc'
        if numeric.notna().sum() / max(len(df), 1) > 0.8:
            df = df.assign(__sk=numeric).sort_values('__sk', ascending=ascending).drop(columns='__sk')
        else:
            df = df.sort_values(sort_col, ascending=ascending)
        df = df.reset_index(drop=True)

    total_filtered = len(df)
    start = (page - 1) * per_page
    end   = start + per_page
    page_df = df.iloc[start:end]

    columns = list(page_df.columns)
    rows = [
        {col: serialize_value(row[col]) for col in columns}
        for _, row in page_df.iterrows()
    ]

    return jsonify({
        'success':       True,
        'columns':       columns,
        'rows':          rows,
        'total_rows':    total_filtered,
        'total_columns': len(columns),
        'page':          page,
        'per_page':      per_page,
        'total_pages':   max(1, -(-total_filtered // per_page)),
        'version_id':    version['id'],
        'version_label': version.get('label', ''),
        'version_type':  version.get('version_type', ''),
    }), 200


@data_bp.route('/columns/<dataset_id>', methods=['GET'])
def get_columns(dataset_id: str):
    """Return column metadata for the current/selected version."""
    version_id = request.args.get('version_id')
    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('Version not found.', 404)), 404

    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    col_meta = get_column_metadata(df)
    return jsonify({'success': True, 'columns': col_meta}), 200


@data_bp.route('/quality/<dataset_id>', methods=['GET'])
def get_quality_report(dataset_id: str):
    """Return a fresh data-quality analysis for the selected version."""
    version_id = request.args.get('version_id')
    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('Version not found.', 404)), 404

    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    quality = analyze_data_quality(df)
    return jsonify({'success': True, 'quality': quality}), 200


@data_bp.route('/datasets', methods=['GET'])
def list_datasets():
    """List all uploaded datasets."""
    datasets = sb.list_datasets()
    return jsonify({'success': True, 'datasets': datasets}), 200


@data_bp.route('/datasets/<dataset_id>', methods=['GET'])
def get_dataset(dataset_id: str):
    """Return a single dataset record."""
    dataset = sb.get_dataset(dataset_id)
    if not dataset:
        return jsonify(error_response('Dataset not found.', 404)), 404
    return jsonify({'success': True, 'dataset': dataset}), 200


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_version(dataset_id: str, version_id):
    if version_id:
        return sb.get_version(version_id)
    return sb.get_current_version(dataset_id)
