"""
History Routes  —  /api/history/
Returns version history, supports reverting to a previous version.
"""

import logging
from flask import Blueprint, request, jsonify

from app.services import supabase_service as sb
from app.services.version_service import get_version_history
from app.utils.helpers import error_response

history_bp = Blueprint('history', __name__)
logger     = logging.getLogger(__name__)


@history_bp.route('/<dataset_id>', methods=['GET'])
def get_history(dataset_id: str):
    """Return all versions for a dataset with full metadata."""
    dataset = sb.get_dataset(dataset_id)
    if not dataset:
        return jsonify(error_response('Dataset not found.', 404)), 404

    history = get_version_history(dataset_id)
    agent_actions = sb.list_agent_actions(dataset_id)

    # Enrich history with agent action details where applicable
    action_map = {a['version_id']: a for a in agent_actions}
    for v in history:
        vid = v.get('id', '')
        if vid in action_map:
            v['agent_action_detail'] = action_map[vid]

    return jsonify({
        'success':  True,
        'dataset':  dataset,
        'history':  history,
        'total_versions': len(history),
    }), 200


@history_bp.route('/revert', methods=['POST'])
def revert_to_version():
    """
    Mark a specific version as current.
    Does NOT delete any versions — merely changes the active pointer.

    Body: { dataset_id: str, version_id: str }
    """
    body       = request.get_json(silent=True) or {}
    dataset_id = body.get('dataset_id', '').strip()
    version_id = body.get('version_id', '').strip()

    if not dataset_id or not version_id:
        return jsonify(error_response('dataset_id and version_id are required.', 400)), 400

    version = sb.get_version(version_id)
    if not version or version.get('dataset_id') != dataset_id:
        return jsonify(error_response('Version not found for this dataset.', 404)), 404

    ok = sb.mark_version_current(dataset_id, version_id)
    if not ok:
        return jsonify(error_response('Could not revert version.', 500)), 500

    sb.update_dataset(dataset_id, {'current_version_id': version_id})

    return jsonify({
        'success':       True,
        'message':       f"Reverted to version {version['version_number']}: {version.get('label', '')}",
        'version_id':    version_id,
        'version_number': version['version_number'],
        'label':         version.get('label', ''),
    }), 200
