"""
Excel Service
-------------
Handles reading, introspecting and previewing Excel files using
pandas + openpyxl.  No data is modified here — this service is
purely read-only / detection.
"""

import io
import logging
import math
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Suppress pandas UserWarning about date format inference - expected behaviour
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
PREVIEW_ROWS   = 100          # rows returned in the table preview
SAMPLE_ROWS    = 20           # rows sent to the AI for context
MAX_COLS_SCAN  = 200          # safety limit on column count


# ══════════════════════════════════════════════════════════════════════════════
# Core read helpers
# ══════════════════════════════════════════════════════════════════════════════

def read_excel_file(file_bytes: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Read an Excel file from raw bytes.
    Returns the first sheet (or the named sheet) as a DataFrame.
    Raises ValueError on unreadable/corrupt files.
    """
    try:
        buf = io.BytesIO(file_bytes)
        xf  = pd.ExcelFile(buf, engine='openpyxl')
        sheets = xf.sheet_names
        if not sheets:
            raise ValueError('Workbook contains no sheets.')
        target = sheet_name if (sheet_name and sheet_name in sheets) else sheets[0]
        df = pd.read_excel(buf, sheet_name=target, engine='openpyxl', dtype=str)
        # Keep original dtypes for numeric detection but start with str to avoid
        # pandas mis-typing mixed columns
        return df, target, sheets
    except ValueError:
        raise
    except Exception as exc:
        logger.error('read_excel_file failed: %s', exc)
        raise ValueError(f'Cannot read Excel file: {exc}')


def read_excel_as_typed(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    """
    Re-read the Excel keeping pandas' inferred types (for stats).
    """
    buf = io.BytesIO(file_bytes)
    return pd.read_excel(buf, sheet_name=sheet_name, engine='openpyxl')


# ══════════════════════════════════════════════════════════════════════════════
# Metadata / detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_workbook_metadata(file_bytes: bytes) -> Dict[str, Any]:
    """
    Return metadata about the workbook without modifying anything.
    """
    try:
        buf = io.BytesIO(file_bytes)
        xf  = pd.ExcelFile(buf, engine='openpyxl')
        sheets = xf.sheet_names

        sheet_info = []
        for sn in sheets:
            try:
                df = pd.read_excel(buf, sheet_name=sn, engine='openpyxl', dtype=str)
                sheet_info.append({
                    'name':    sn,
                    'rows':    len(df),
                    'columns': len(df.columns),
                    'headers': list(df.columns),
                })
            except Exception:
                sheet_info.append({'name': sn, 'rows': 0, 'columns': 0, 'headers': []})

        return {
            'total_sheets': len(sheets),
            'sheet_names':  sheets,
            'sheets':       sheet_info,
        }
    except Exception as exc:
        raise ValueError(f'Cannot inspect workbook: {exc}')


def get_column_metadata(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    For each column return name, inferred type, null count, unique count, sample values.
    Uses the string-typed DataFrame for safe inspection.
    """
    cols_meta = []
    for col in df.columns[:MAX_COLS_SCAN]:
        series = df[col]
        non_null  = series.dropna()
        non_empty = non_null[non_null.astype(str).str.strip() != '']

        # Attempt to infer a sensible type from the cell values
        inferred = _infer_column_type(non_empty)

        sample = non_empty.head(5).tolist()

        cols_meta.append({
            'name':         str(col),
            'inferred_type': inferred,
            'null_count':   int(series.isna().sum()),
            'empty_count':  int((series.astype(str).str.strip() == '').sum()),
            'unique_count': int(series.nunique(dropna=True)),
            'total_count':  len(series),
            'sample_values': [str(v)[:100] for v in sample],
        })
    return cols_meta


def _infer_column_type(series: pd.Series) -> str:
    """Heuristic: attempt to classify a series as numeric / date / boolean / text."""
    if series.empty:
        return 'unknown'
    sample = series.head(50).astype(str)
    # Try numeric
    numeric_ok = pd.to_numeric(sample, errors='coerce').notna().sum()
    if numeric_ok / max(len(sample), 1) >= 0.8:
        return 'numeric'
    # Try date
    date_ok = pd.to_datetime(sample, errors='coerce').notna().sum()
    if date_ok / max(len(sample), 1) >= 0.8:
        return 'date'
    # Boolean-like
    unique_lower = set(sample.str.lower().unique())
    if unique_lower <= {'true', 'false', 'yes', 'no', '1', '0', 'y', 'n'}:
        return 'boolean'
    return 'text'


# ══════════════════════════════════════════════════════════════════════════════
# Data-quality analysis (READ-ONLY — no modifications)
# ══════════════════════════════════════════════════════════════════════════════

def analyze_data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Inspect the DataFrame and report quality issues WITHOUT modifying any data.
    """
    total_rows    = len(df)
    total_columns = len(df.columns)

    # Duplicate rows (exact)
    duplicate_mask = df.duplicated(keep=False)
    duplicate_count = int(df.duplicated().sum())   # number that WOULD be removed

    # Completely blank rows (all cells are NaN or empty string)
    blank_row_mask = df.apply(
        lambda row: row.isna().all() or (row.astype(str).str.strip() == '').all(),
        axis=1
    )
    blank_row_count = int(blank_row_mask.sum())

    # Completely empty columns
    empty_cols = [
        col for col in df.columns
        if df[col].isna().all() or (df[col].astype(str).str.strip() == '').all()
    ]

    # Missing values (NaN / empty string per column)
    missing_per_col = {}
    total_missing   = 0
    for col in df.columns:
        m = int(df[col].isna().sum()) + int((df[col].astype(str).str.strip() == '').sum())
        # Avoid double-counting fully-blank columns in missing tally
        if col not in empty_cols:
            missing_per_col[col] = m
            total_missing += m

    # Columns with leading/trailing whitespace in values
    whitespace_cols = []
    for col in df.columns:
        str_vals = df[col].dropna().astype(str)
        if (str_vals != str_vals.str.strip()).any():
            whitespace_cols.append(col)

    # Invalid / empty headers
    invalid_headers = [
        str(col) for col in df.columns
        if not str(col).strip() or str(col).startswith('Unnamed:')
    ]

    # Date inconsistencies (columns likely to be dates with mixed formats)
    date_inconsistency_cols = []
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(50)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors='coerce')
        parse_ratio = parsed.notna().sum() / max(len(sample), 1)
        if 0.5 < parse_ratio < 1.0:
            date_inconsistency_cols.append(col)

    issues_count = (
        duplicate_count +
        blank_row_count +
        len(empty_cols) +
        total_missing +
        len(whitespace_cols) +
        len(invalid_headers) +
        len(date_inconsistency_cols)
    )

    cleaning_required = issues_count > 0

    return {
        'total_rows':               total_rows,
        'total_columns':            total_columns,
        'duplicate_rows':           duplicate_count,
        'blank_rows':               blank_row_count,
        'empty_columns':            empty_cols,
        'empty_column_count':       len(empty_cols),
        'missing_values_total':     total_missing,
        'missing_per_column':       missing_per_col,
        'whitespace_columns':       whitespace_cols,
        'invalid_headers':          invalid_headers,
        'date_inconsistency_cols':  date_inconsistency_cols,
        'issues_count':             issues_count,
        'cleaning_required':        cleaning_required,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Preview helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_preview(df: pd.DataFrame, max_rows: int = PREVIEW_ROWS) -> Dict[str, Any]:
    """
    Build a safe, JSON-serialisable preview of a DataFrame.
    """
    subset = df.head(max_rows)
    columns = list(df.columns)
    rows = []
    for _, row in subset.iterrows():
        rows.append({col: _safe_cell(row[col]) for col in columns})

    return {
        'columns':     columns,
        'rows':        rows,
        'total_rows':  len(df),
        'preview_rows': len(rows),
        'total_columns': len(columns),
    }


def _safe_cell(v: Any) -> Any:
    """Convert a single cell value to a JSON-serialisable form."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, float):
        return v
    return str(v)


def build_sample_for_ai(df: pd.DataFrame, n_rows: int = SAMPLE_ROWS) -> str:
    """
    Return a compact text summary of the DataFrame suitable for AI context.
    Avoids dumping thousands of rows to the LLM.
    """
    lines = []
    lines.append(f"Dataset: {len(df)} rows × {len(df.columns)} columns")
    lines.append(f"Columns: {', '.join(str(c) for c in df.columns)}")
    lines.append("")
    lines.append(f"Sample ({min(n_rows, len(df))} rows):")
    sample_df = df.head(n_rows)
    lines.append(sample_df.to_string(index=False, max_colwidth=40))
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# DataFrame ↔ bytes helpers
# ══════════════════════════════════════════════════════════════════════════════

def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = 'Sheet1') -> bytes:
    """Serialise a DataFrame to .xlsx bytes (in memory)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buf.getvalue()


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to UTF-8 CSV bytes."""
    return df.to_csv(index=False).encode('utf-8')


def df_from_bytes(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    """Deserialise a DataFrame from .xlsx bytes."""
    buf = io.BytesIO(file_bytes)
    return pd.read_excel(buf, sheet_name=sheet_name, engine='openpyxl', dtype=str)
