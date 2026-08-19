"""
WSGI entry point.
Used by gunicorn locally and by Vercel's Python serverless runtime.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.config import get_config

app = create_app()
app.config.from_object(get_config())

# Vercel / gunicorn look for the name `app`
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
