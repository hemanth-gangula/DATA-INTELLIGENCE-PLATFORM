"""
Application Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024   # 50 MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

    # API Keys (server-side only — never exposed to frontend)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

    # Groq model
    GROQ_MODEL = os.environ.get('GROQ_MODEL', 'groq/compound')

    # Tmp directory (Vercel uses /tmp; local dev uses ./tmp)
    TMP_DIR = os.environ.get('TMP_DIR', '/tmp')

    # Supabase storage bucket names
    SUPABASE_FILES_BUCKET = 'dataset-files'

    # Max rows to send to Groq for context (avoid token overflow)
    GROQ_SAMPLE_ROWS = 20
    GROQ_MAX_CONTEXT_CHARS = 6000


class DevelopmentConfig(Config):
    DEBUG = True
    TMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp')


class ProductionConfig(Config):
    DEBUG = False
    TMP_DIR = '/tmp'


config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)
