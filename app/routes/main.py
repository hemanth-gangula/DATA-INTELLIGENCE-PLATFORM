"""
Main route — SPA shell + health check endpoint.
"""
import os
from flask import Blueprint, render_template, jsonify

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@main_bp.route('/dashboard')
@main_bp.route('/data')
@main_bp.route('/agent')
@main_bp.route('/insights')
@main_bp.route('/reports')
@main_bp.route('/history')
@main_bp.route('/settings')
def index():
    """Serve the SPA shell for all frontend routes."""
    return render_template('index.html')


@main_bp.route('/api/health', methods=['GET'])
def health():
    """
    Live Supabase connectivity check.
    Tests: DB access, storage write to all 3 buckets.
    Returns JSON with per-component status.
    """
    from app.services.supabase_service import health_check

    result = health_check()

    # Never leak credentials in the response
    result.pop('project_url', None)

    status_code = 200 if result.get('overall_ok') else 503

    # Add configuration guidance when storage fails
    if not result.get('overall_ok'):
        key = os.environ.get('SUPABASE_KEY', '')
        if key.startswith('sb_publishable'):
            result['key_warning'] = (
                'The SUPABASE_KEY appears to be a publishable key which has restricted '
                'permissions. Please use the anon or service_role key from: '
                'Supabase Dashboard → Settings → API → Project API keys'
            )

    return jsonify(result), status_code
