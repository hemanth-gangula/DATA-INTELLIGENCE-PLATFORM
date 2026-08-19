"""
Reports Routes  —  /api/reports/
Generates and returns comprehensive dataset reports.
"""

import logging
from flask import Blueprint, request, jsonify

from app.services import supabase_service as sb
from app.services.version_service  import load_version_dataframe, get_version_history
from app.services.insights_service import compute_statistics, get_latest_insights
from app.services.dashboard_service import compute_dashboard
from app.utils.helpers import error_response

reports_bp = Blueprint('reports', __name__)
logger     = logging.getLogger(__name__)


@reports_bp.route('/<dataset_id>', methods=['GET'])
def get_report(dataset_id: str):
    """
    Build a comprehensive report for the current/selected dataset version.
    Includes: dataset summary, cleaning summary, agent history,
              KPIs, stats, AI insights, version history.
    """
    version_id = request.args.get('version_id')

    dataset = sb.get_dataset(dataset_id)
    if not dataset:
        return jsonify(error_response('Dataset not found.', 404)), 404

    version = _get_version(dataset_id, version_id)
    if not version:
        return jsonify(error_response('No version found.', 404)), 404

    df = load_version_dataframe(version)
    if df is None:
        return jsonify(error_response('Could not load dataset.', 500)), 500

    # Compute all report components
    stats     = compute_statistics(df)
    dashboard = compute_dashboard(df, version_label=version.get('label', ''))
    insights  = get_latest_insights(dataset_id, version['id'])
    history   = get_version_history(dataset_id)
    cleaning  = sb.get_cleaning_operation(dataset_id) or {}
    agent_actions = sb.list_agent_actions(dataset_id)

    report = {
        'dataset': {
            'id':               dataset_id,
            'name':             dataset.get('name', ''),
            'original_filename': dataset.get('original_filename', ''),
            'sheet_name':       dataset.get('sheet_name', ''),
            'created_at':       dataset.get('created_at', ''),
        },
        'current_version': {
            'id':             version['id'],
            'version_number': version['version_number'],
            'label':          version.get('label', ''),
            'version_type':   version.get('version_type', ''),
            'created_at':     version.get('created_at', ''),
            'rows':           version.get('rows_after', 0),
            'download_excel': version.get('storage_url_excel'),
            'download_csv':   version.get('storage_url_csv'),
        },
        'data_summary': {
            'total_rows':            stats['total_rows'],
            'total_columns':         stats['total_columns'],
            'missing_values':        stats['missing_values_total'],
            'duplicate_rows':        stats['duplicate_rows'],
            'numeric_columns':       len(stats['numeric_summaries']),
            'categorical_columns':   len(stats['categorical_summaries']),
        },
        'cleaning_summary': {
            'cleaning_required':     cleaning.get('cleaning_required', False),
            'duplicates_removed':    cleaning.get('duplicates_removed', 0),
            'blank_rows_removed':    cleaning.get('blank_rows_removed', 0),
            'empty_columns_removed': cleaning.get('empty_columns_removed', 0),
            'whitespace_fixed':      cleaning.get('whitespace_fixed', 0),
            'columns_modified':      cleaning.get('columns_modified', 0),
            'cleaning_summary':      cleaning.get('cleaning_summary', ''),
        },
        'agent_summary': {
            'total_operations': len(agent_actions),
            'operations': [
                {
                    'command':    a.get('user_command', ''),
                    'tool':       a.get('tool_used', ''),
                    'rows_before': a.get('rows_before', 0),
                    'rows_after': a.get('rows_after', 0),
                    'created_at': a.get('created_at', ''),
                }
                for a in agent_actions
            ],
        },
        'kpis':     dashboard.get('kpis', []),
        'charts':   dashboard.get('charts', []),
        'stats':    stats,
        'insights': insights.get('insight_text', ''),
        'version_history': history,
    }

    # Optionally save report snapshot to Supabase
    try:
        sb.save_report({
            'dataset_id':  dataset_id,
            'version_id':  version['id'],
            'report_name': f"Report — {dataset.get('name', '')}",
            'report_data': report,
        })
    except Exception as exc:
        logger.warning('Could not save report to Supabase: %s', exc)

    return jsonify({'success': True, 'report': report}), 200


def _get_version(dataset_id: str, version_id):
    if version_id:
        return sb.get_version(version_id)
    return sb.get_current_version(dataset_id)
