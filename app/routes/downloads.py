"""
Downloads Routes  —  /api/downloads/
Serves Excel and CSV file downloads for any dataset version.
"""

import logging
from flask import Blueprint, request, jsonify, send_file, Response
import io

from app.services.export_service import (
    get_excel_bytes_for_version,
    get_csv_bytes_for_version,
    get_download_urls_for_version,
)
from app.utils.helpers import error_response

downloads_bp = Blueprint('downloads', __name__)
logger       = logging.getLogger(__name__)


@downloads_bp.route('/excel/<dataset_id>', methods=['GET'])
def download_excel(dataset_id: str):
    """Download the Excel file for the current or specified version."""
    version_id = request.args.get('version_id') or None

    file_bytes, filename = get_excel_bytes_for_version(dataset_id, version_id)
    if file_bytes is None:
        return jsonify(error_response('File not found or could not be generated.', 404)), 404

    return send_file(
        io.BytesIO(file_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )


@downloads_bp.route('/csv/<dataset_id>', methods=['GET'])
def download_csv(dataset_id: str):
    """Download the CSV file for the current or specified version."""
    version_id = request.args.get('version_id') or None

    file_bytes, filename = get_csv_bytes_for_version(dataset_id, version_id)
    if file_bytes is None:
        return jsonify(error_response('File not found or could not be generated.', 404)), 404

    return send_file(
        io.BytesIO(file_bytes),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )


@downloads_bp.route('/urls/<dataset_id>', methods=['GET'])
def get_urls(dataset_id: str):
    """Return the Supabase public download URLs for a version."""
    version_id = request.args.get('version_id') or None
    urls = get_download_urls_for_version(dataset_id, version_id)
    return jsonify({'success': True, **urls}), 200
