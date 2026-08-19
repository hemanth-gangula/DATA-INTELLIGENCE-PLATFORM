"""
Dashboard Routes  —  /api/dashboard/
Returns KPIs, charts, and filter specs for the current dataset version.
"""

import logging
from flask import Blueprint, request, jsonify

from app.services import supabase_service as sb
from app.services.version_service  import load_version_dataframe
from app.services.dashboard_service import compute_dashboard
from app.utils.helpers import error_response

dashboard_bp = Blueprint('dashboard', __name__)
logger       = logging.getLogger(__name__)


@dashboard_bp.route('/<dataset_id>', methods=['GET'])
def get_dashboard(dataset_id: str):
    """
    Return the full dashboard payload for the current (or selected) version.
    Applies optional column filters passed as query params.
    """
    version_id  = request.args.get('version_id')
    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('No data found. Please upload a file first.', 404)), 404

    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset from storage.', 500)), 500

    # Apply any query-param filters before computing the dashboard
    filter_col = request.args.get('filter_col', '')
    filter_val = request.args.get('filter_val', '')
    if filter_col and filter_col in df.columns and filter_val:
        df = df[df[filter_col].astype(str).str.lower().str.contains(
            filter_val.lower(), na=False
        )]

    dashboard = compute_dashboard(df, version_label=version.get('label', ''))
    dashboard['version_id']     = version['id']
    dashboard['version_number'] = version['version_number']
    dashboard['version_type']   = version.get('version_type', '')
    dashboard['download_excel'] = version.get('storage_url_excel')
    dashboard['download_csv']   = version.get('storage_url_csv')

    return jsonify({'success': True, 'dashboard': dashboard}), 200


def _get_version(dataset_id: str, version_id):
    if version_id:
        return sb.get_version(version_id)
    return sb.get_current_version(dataset_id)
