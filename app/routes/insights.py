"""
Insights Routes  —  /api/insights/
Returns AI-generated insights for the current dataset version.
"""

import logging
from flask import Blueprint, request, jsonify

from app.services import supabase_service as sb
from app.services.version_service  import load_version_dataframe
from app.services.insights_service import (
    generate_and_save_insights,
    get_latest_insights,
    compute_statistics,
)
from app.utils.helpers import error_response

insights_bp = Blueprint('insights', __name__)
logger      = logging.getLogger(__name__)


@insights_bp.route('/<dataset_id>', methods=['GET'])
def get_insights(dataset_id: str):
    """
    Return the most recent AI insights for the current/selected version.
    Pass ?refresh=true to force regeneration.
    """
    version_id = request.args.get('version_id')
    refresh    = request.args.get('refresh', 'false').lower() == 'true'

    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('No version found.', 404)), 404

    if not refresh:
        # Try cached first
        saved = get_latest_insights(dataset_id, version['id'])
        if saved.get('insight_text'):
            return jsonify({
                'success':      True,
                'insight_text': saved['insight_text'],
                'stats':        saved.get('stats_snapshot', {}),
                'version_id':   version['id'],
                'version_label': version.get('label', ''),
                'cached':       True,
            }), 200

    # Generate fresh insights
    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    dataset    = sb.get_dataset(dataset_id) or {}
    result = generate_and_save_insights(
        df=df,
        dataset_id=dataset_id,
        version_id=version['id'],
        dataset_name=dataset.get('name', 'Dataset'),
    )

    return jsonify({
        'success':       True,
        'insight_text':  result['insight_text'],
        'stats':         result['stats'],
        'version_id':    version['id'],
        'version_label': version.get('label', ''),
        'cached':        False,
    }), 200


@insights_bp.route('/stats/<dataset_id>', methods=['GET'])
def get_stats(dataset_id: str):
    """Return raw computed statistics (no AI) for the current version."""
    version_id = request.args.get('version_id')
    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('No version found.', 404)), 404

    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    stats = compute_statistics(df)
    return jsonify({'success': True, 'stats': stats, 'version_id': version['id']}), 200


def _get_version(dataset_id: str, version_id):
    if version_id:
        return sb.get_version(version_id)
    return sb.get_current_version(dataset_id)
