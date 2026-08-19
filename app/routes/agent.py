"""
Agent Routes  —  /api/agent/
Handles AI Agent command execution and conversation history.
"""

import logging
from flask import Blueprint, request, jsonify

from app.agents.excel_agent import run_agent
from app.services import supabase_service as sb
from app.utils.helpers import error_response

agent_bp = Blueprint('agent', __name__)
logger   = logging.getLogger(__name__)

MAX_COMMAND_LEN = 1000


@agent_bp.route('/run', methods=['POST'])
def run():
    """
    Execute a natural-language agent command on the current dataset version.

    Body (JSON):
      dataset_id   : str  — required
      command      : str  — natural-language command
      version_id   : str  — optional; defaults to current version
    """
    body = request.get_json(silent=True) or {}

    dataset_id = body.get('dataset_id', '').strip()
    command    = body.get('command', '').strip()
    version_id = body.get('version_id', '').strip() or None

    if not dataset_id:
        return jsonify(error_response('dataset_id is required.', 400)), 400
    if not command:
        return jsonify(error_response('command is required.', 400)), 400
    if len(command) > MAX_COMMAND_LEN:
        return jsonify(error_response(
            f'Command too long (max {MAX_COMMAND_LEN} chars).', 400
        )), 400

    # Verify dataset exists
    dataset = sb.get_dataset(dataset_id)
    if not dataset:
        return jsonify(error_response('Dataset not found.', 404)), 404

    # Execute the full agent pipeline (Brain → Hands → Version → Storage)
    result = run_agent(
        dataset_id=dataset_id,
        user_command=command,
        version_id=version_id,
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'error':   result.get('error', 'Agent execution failed.'),
        }), 500

    return jsonify({'success': True, 'result': result}), 200


@agent_bp.route('/history/<dataset_id>', methods=['GET'])
def get_agent_history(dataset_id: str):
    """Return all agent actions for a dataset."""
    actions = sb.list_agent_actions(dataset_id)
    return jsonify({'success': True, 'actions': actions}), 200


@agent_bp.route('/tools', methods=['GET'])
def list_tools():
    """Return the list of available agent tools."""
    from app.agents.tools import list_tools as _list
    return jsonify({'success': True, 'tools': _list()}), 200
