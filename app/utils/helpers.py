"""
Utility helpers used across the application.
"""
import os
import re
import uuid
import logging
from datetime import datetime
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


# ── File helpers ───────────────────────────────────────────────────────────────

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if file extension is allowed."""
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in allowed_extensions
    )


def sanitize_filename(filename: str) -> str:
    """Return a safe, sanitized filename."""
    name = secure_filename(filename)
    # strip any remaining path separators
    name = os.path.basename(name)
    if not name:
        name = f"upload_{uuid.uuid4().hex[:8]}.xlsx"
    return name


def generate_unique_filename(original: str) -> str:
    """Prefix filename with a UUID to ensure uniqueness in storage."""
    base, ext = os.path.splitext(sanitize_filename(original))
    unique_id = uuid.uuid4().hex[:12]
    return f"{unique_id}_{base}{ext}"


# ── ID / timestamp helpers ─────────────────────────────────────────────────────

def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


# ── Data helpers ───────────────────────────────────────────────────────────────

def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def truncate_string(s: str, max_len: int = 200) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s[:max_len] + '…' if len(s) > max_len else s


def clean_column_name(name: str) -> str:
    """Normalise a column header: strip whitespace and reduce internal spaces."""
    if not isinstance(name, str):
        name = str(name)
    return re.sub(r'\s+', ' ', name.strip())


def serialize_value(v):
    """Convert a value to a JSON-serialisable form."""
    if v is None:
        return None
    if isinstance(v, float):
        import math
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if hasattr(v, 'isoformat'):          # datetime / date
        return v.isoformat()
    if isinstance(v, (int, str, bool)):
        return v
    return str(v)


def dataframe_to_records(df, max_rows: int = 500) -> list:
    """Convert a DataFrame slice to a list of JSON-serialisable dicts."""
    import pandas as pd
    subset = df.head(max_rows)
    records = []
    for _, row in subset.iterrows():
        records.append({col: serialize_value(row[col]) for col in df.columns})
    return records


def success_response(data: dict = None, message: str = 'OK') -> dict:
    resp = {'success': True, 'message': message}
    if data:
        resp.update(data)
    return resp


def error_response(message: str, code: int = 400) -> tuple:
    return {'success': False, 'error': message}, code
