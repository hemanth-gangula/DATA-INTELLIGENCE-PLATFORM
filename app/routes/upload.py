"""
Upload Route
POST /api/upload/
  - Validates file
  - Detects workbook metadata
  - Analyses data quality
  - Runs safe automatic cleaning
  - Saves original + cleaned versions to Supabase
  - Returns full result to frontend
"""

import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app

from app.services.excel_service import (
    read_excel_file,
    detect_workbook_metadata,
    get_column_metadata,
    analyze_data_quality,
    build_preview,
    build_sample_for_ai,
)
from app.services.cleaning_service import clean_dataframe
from app.services.version_service  import create_original_version, create_cleaned_version
from app.services.insights_service import generate_and_save_insights
from app.services import supabase_service as sb
from app.utils.helpers import allowed_file, sanitize_filename, error_response, success_response

upload_bp = Blueprint('upload', __name__)
logger    = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024   # 50 MB


@upload_bp.route('/', methods=['POST'])
def upload_file():
    """
    Full upload pipeline:
      validate → detect → quality-check → clean → save → insights → respond
    """
    # ── 1. File validation ────────────────────────────────────────────────────
    if 'file' not in request.files:
        return jsonify(error_response('No file provided.', 400)), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify(error_response('Empty filename.', 400)), 400

    filename = sanitize_filename(file.filename)
    allowed  = current_app.config.get('ALLOWED_EXTENSIONS', {'xlsx', 'xls'})
    if not allowed_file(filename, allowed):
        return jsonify(error_response(
            f'File type not supported. Allowed: {", ".join(allowed)}.', 400
        )), 400

    file_bytes = file.read()
    if len(file_bytes) == 0:
        return jsonify(error_response('The uploaded file is empty.', 400)), 400
    if len(file_bytes) > MAX_FILE_SIZE:
        return jsonify(error_response('File exceeds the 50 MB limit.', 400)), 400

    # ── 2. Workbook detection ─────────────────────────────────────────────────
    try:
        workbook_meta = detect_workbook_metadata(file_bytes)
    except ValueError as exc:
        return jsonify(error_response(str(exc), 422)), 422

    # Read the first (or selected) sheet
    sheet_name = request.form.get('sheet_name') or workbook_meta['sheet_names'][0]
    try:
        df_original, sheet_name, all_sheets = read_excel_file(file_bytes, sheet_name)
    except ValueError as exc:
        return jsonify(error_response(str(exc), 422)), 422

    if df_original.empty:
        return jsonify(error_response('The selected sheet is empty.', 422)), 422

    # ── 3. Column metadata & data-quality analysis ────────────────────────────
    col_meta      = get_column_metadata(df_original)
    quality_report = analyze_data_quality(df_original)

    # ── 4. Safe automatic cleaning ────────────────────────────────────────────
    df_cleaned, cleaning_report = clean_dataframe(df_original)

    # ── 5. Create dataset record in Supabase ──────────────────────────────────
    dataset_id = str(uuid.uuid4())
    dataset_name = filename.rsplit('.', 1)[0]

    try:
        dataset_record = sb.create_dataset({
            'id':                dataset_id,
            'name':              dataset_name,
            'original_filename': filename,
            'sheet_name':        sheet_name,
            'total_rows':        len(df_original),
            'total_columns':     len(df_original.columns),
            'created_at':        datetime.now(timezone.utc).isoformat(),
            'updated_at':        datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.error('create_dataset failed: %s', exc)
        return jsonify(error_response(f'Database error: {exc}', 500)), 500

    # ── 6. Save original version (Version 1) ──────────────────────────────────
    try:
        original_version = create_original_version(
            dataset_id=dataset_id,
            df=df_original,
            sheet_name=sheet_name,
            original_filename=filename,
        )
    except Exception as exc:
        logger.error('create_original_version failed: %s', exc)
        return jsonify(error_response(f'Storage error (original): {exc}', 500)), 500

    # ── 7. Save cleaned version (Version 2) ───────────────────────────────────
    try:
        cleaned_version = create_cleaned_version(
            dataset_id=dataset_id,
            parent_version_id=original_version['id'],
            df_original=df_original,
            df_cleaned=df_cleaned,
            sheet_name=sheet_name,
            cleaning_report=cleaning_report,
            original_filename=filename,
        )
    except Exception as exc:
        logger.error('create_cleaned_version failed: %s', exc)
        return jsonify(error_response(f'Storage error (cleaned): {exc}', 500)), 500

    # ── 8. Save cleaning operation record ─────────────────────────────────────
    try:
        sb.save_cleaning_operation({
            'dataset_id':             dataset_id,
            'version_id':             cleaned_version['id'],
            'duplicates_found':       cleaning_report['duplicates_found'],
            'duplicates_removed':     cleaning_report['duplicates_removed'],
            'blank_rows_found':       cleaning_report['blank_rows_found'],
            'blank_rows_removed':     cleaning_report['blank_rows_removed'],
            'empty_columns_removed':  cleaning_report['empty_columns_removed'],
            'whitespace_fixed':       cleaning_report['whitespace_cells_fixed'],
            'columns_modified':       cleaning_report['columns_modified_count'],
            'missing_values_count':   cleaning_report['missing_values_remaining'],
            'cleaning_required':      cleaning_report['cleaning_required'],
            'cleaning_summary':       cleaning_report['status'],
        })
    except Exception as exc:
        logger.warning('Could not save cleaning op: %s', exc)

    # ── 9. Generate AI Insights ────────────────────────────────────────────────
    try:
        insights_result = generate_and_save_insights(
            df=df_cleaned,
            dataset_id=dataset_id,
            version_id=cleaned_version['id'],
            dataset_name=dataset_name,
        )
    except Exception as exc:
        logger.warning('Insights generation failed: %s', exc)
        insights_result = {'stats': {}, 'insight_text': '', 'insight_id': ''}

    # ── 10. Build preview ─────────────────────────────────────────────────────
    preview = build_preview(df_cleaned, max_rows=100)

    # ── 11. Return response ───────────────────────────────────────────────────
    return jsonify({
        'success':          True,
        'dataset_id':       dataset_id,
        'dataset_name':     dataset_name,
        'original_filename': filename,
        'sheet_name':       sheet_name,
        'all_sheets':       all_sheets,
        'workbook_meta':    workbook_meta,
        'column_metadata':  col_meta,
        'quality_report':   quality_report,
        'cleaning_report':  cleaning_report,
        'original_version': {
            'id':             original_version['id'],
            'version_number': original_version['version_number'],
            'label':          original_version['label'],
            'rows':           original_version['rows_after'],
            'download_excel': original_version.get('storage_url_excel'),
            'download_csv':   original_version.get('storage_url_csv'),
        },
        'cleaned_version': {
            'id':             cleaned_version['id'],
            'version_number': cleaned_version['version_number'],
            'label':          cleaned_version['label'],
            'rows':           cleaned_version['rows_after'],
            'download_excel': cleaned_version.get('storage_url_excel'),
            'download_csv':   cleaned_version.get('storage_url_csv'),
        },
        'preview':          preview,
        'insights':         insights_result.get('insight_text', ''),
        'stats':            insights_result.get('stats', {}),
        'message':          cleaning_report['status'],
    }), 200


@upload_bp.route('/sheets', methods=['POST'])
def get_sheets():
    """Return sheet names for a workbook (quick check before full upload)."""
    if 'file' not in request.files:
        return jsonify(error_response('No file provided.', 400)), 400
    file       = request.files['file']
    file_bytes = file.read()
    try:
        meta = detect_workbook_metadata(file_bytes)
        return jsonify({'success': True, 'sheets': meta['sheet_names']}), 200
    except Exception as exc:
        return jsonify(error_response(str(exc), 422)), 422
