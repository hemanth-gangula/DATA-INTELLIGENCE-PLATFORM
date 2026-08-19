"""
AI-Powered Excel Data Intelligence Platform
Flask Application Factory
"""

import os
import logging
from flask import Flask
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Application factory pattern."""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')

    # ── Configuration ──────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024   # 50 MB upload limit
    app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls'}
    app.config['GROQ_API_KEY'] = os.environ.get('GROQ_API_KEY', '')
    app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL', '')
    app.config['SUPABASE_KEY'] = os.environ.get('SUPABASE_KEY', '')
    app.config['TMP_DIR'] = os.environ.get('TMP_DIR', '/tmp')

    # Enable CORS for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Register Blueprints ────────────────────────────────────────────────────
    from app.routes.upload   import upload_bp
    from app.routes.data     import data_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.agent    import agent_bp
    from app.routes.insights import insights_bp
    from app.routes.reports  import reports_bp
    from app.routes.history  import history_bp
    from app.routes.downloads import downloads_bp
    from app.routes.main     import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp,    url_prefix='/api/upload')
    app.register_blueprint(data_bp,      url_prefix='/api/data')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(agent_bp,     url_prefix='/api/agent')
    app.register_blueprint(insights_bp,  url_prefix='/api/insights')
    app.register_blueprint(reports_bp,   url_prefix='/api/reports')
    app.register_blueprint(history_bp,   url_prefix='/api/history')
    app.register_blueprint(downloads_bp, url_prefix='/api/downloads')

    logger.info("Flask application created successfully.")
    return app
