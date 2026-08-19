"""
Insights Service
----------------
1. Computes factual statistics from the DataFrame (no AI involvement).
2. Sends the stats summary to Groq for natural-language explanation.
3. Saves the result to Supabase.

The AI NEVER invents numbers — it only explains pre-computed facts.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

from app.services import groq_service, supabase_service as sb

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def generate_and_save_insights(
    df: pd.DataFrame,
    dataset_id: str,
    version_id: str,
    dataset_name: str = 'Dataset',
) -> Dict[str, Any]:
    """
    Compute statistics → format text summary → call Groq → save to Supabase.
    Returns {'stats': {...}, 'insight_text': '...', 'insight_id': '...'}
    """
    # Step 1 — compute factual statistics (deterministic, no AI)
    stats = compute_statistics(df)

    # Step 2 — format a compact stats string for Groq context
    stats_text = format_stats_for_ai(stats, dataset_name)

    # Step 3 — call Groq (brain explains the pre-computed numbers)
    try:
        insight_text = groq_service.generate_insights(stats_text, dataset_name)
    except Exception as exc:
        logger.error('Groq insight generation failed: %s', exc)
        insight_text = _fallback_insight(stats)

    # Step 4 — save to Supabase
    record = {
        'dataset_id':    dataset_id,
        'version_id':    version_id,
        'insight_text':  insight_text,
        'insight_type':  'auto',
        'stats_snapshot': stats,
    }
    try:
        saved = sb.save_insight(record)
        insight_id = saved.get('id', '')
    except Exception as exc:
        logger.warning('Could not save insight: %s', exc)
        insight_id = ''

    return {
        'stats':        stats,
        'insight_text': insight_text,
        'insight_id':   insight_id,
    }


def get_latest_insights(dataset_id: str, version_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the most recent saved insight for a dataset/version."""
    rows = sb.get_insights(dataset_id, version_id)
    if rows:
        return rows[0]
    return {'insight_text': '', 'stats_snapshot': {}}


# ══════════════════════════════════════════════════════════════════════════════
# Statistics computation (factual, deterministic)
# ══════════════════════════════════════════════════════════════════════════════

def compute_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute a comprehensive statistics dictionary from a DataFrame.
    All values are serialisable (no numpy types).
    """
    total_rows    = len(df)
    total_columns = len(df.columns)
    missing_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    column_stats: List[Dict[str, Any]] = []
    for col in df.columns:
        series   = df[col]
        null_cnt = int(series.isna().sum())
        unique_n = int(series.nunique(dropna=True))
        numeric  = pd.to_numeric(series, errors='coerce')
        is_num   = bool(numeric.notna().sum() / max(len(series), 1) > 0.5)

        col_stat: Dict[str, Any] = {
            'name':       col,
            'null_count': null_cnt,
            'unique':     unique_n,
            'is_numeric': is_num,
        }

        if is_num:
            valid = numeric.dropna()
            col_stat.update({
                'min':   _s(valid.min()),
                'max':   _s(valid.max()),
                'mean':  _s(valid.mean()),
                'sum':   _s(valid.sum()),
                'std':   _s(valid.std()),
                'median': _s(valid.median()),
            })
        else:
            top_vals = series.value_counts(dropna=True).head(5)
            col_stat['top_values'] = {
                str(k): int(v) for k, v in top_vals.items()
            }

        column_stats.append(col_stat)

    # Numeric column aggregate KPIs
    numeric_summaries: List[Dict[str, Any]] = []
    for cs in column_stats:
        if cs['is_numeric']:
            numeric_summaries.append({
                'column': cs['name'],
                'total':  cs.get('sum',  0),
                'mean':   cs.get('mean', 0),
                'min':    cs.get('min',  0),
                'max':    cs.get('max',  0),
            })

    # Top categorical distributions
    categorical_summaries: List[Dict[str, Any]] = []
    for cs in column_stats:
        if not cs['is_numeric'] and 'top_values' in cs:
            categorical_summaries.append({
                'column':     cs['name'],
                'unique':     cs['unique'],
                'top_values': cs['top_values'],
            })

    return {
        'total_rows':              total_rows,
        'total_columns':           total_columns,
        'missing_values_total':    missing_total,
        'duplicate_rows':          duplicate_rows,
        'column_stats':            column_stats,
        'numeric_summaries':       numeric_summaries,
        'categorical_summaries':   categorical_summaries,
    }


def format_stats_for_ai(stats: Dict[str, Any], dataset_name: str) -> str:
    """Format statistics into a compact text summary for Groq."""
    lines = [
        f"Dataset: {dataset_name}",
        f"Total Rows: {stats['total_rows']:,}",
        f"Total Columns: {stats['total_columns']}",
        f"Missing Values: {stats['missing_values_total']:,}",
        f"Duplicate Rows: {stats['duplicate_rows']:,}",
        "",
    ]

    if stats['numeric_summaries']:
        lines.append("Numeric Column Summaries:")
        for ns in stats['numeric_summaries'][:6]:
            lines.append(
                f"  {ns['column']}: total={ns['total']:,.2f}, "
                f"mean={ns['mean']:,.2f}, min={ns['min']:,.2f}, max={ns['max']:,.2f}"
            )
        lines.append("")

    if stats['categorical_summaries']:
        lines.append("Categorical Column Summaries:")
        for cs in stats['categorical_summaries'][:4]:
            top = ', '.join(f"{k}({v})" for k, v in list(cs['top_values'].items())[:5])
            lines.append(f"  {cs['column']}: {cs['unique']} unique — top: {top}")

    return "\n".join(lines)


def _fallback_insight(stats: Dict[str, Any]) -> str:
    """Generate a plain-text insight without Groq (fallback)."""
    lines = [
        f"The dataset contains {stats['total_rows']:,} rows and "
        f"{stats['total_columns']} columns.",
    ]
    if stats['missing_values_total']:
        lines.append(f"There are {stats['missing_values_total']:,} missing values.")
    if stats['duplicate_rows']:
        lines.append(f"There are {stats['duplicate_rows']:,} duplicate rows.")
    if stats['numeric_summaries']:
        ns = stats['numeric_summaries'][0]
        lines.append(
            f"The column '{ns['column']}' has a total of {ns['total']:,.2f} "
            f"and a mean of {ns['mean']:,.2f}."
        )
    return " ".join(lines)


def _s(v) -> float:
    """Convert numpy scalar to Python float, handling NaN/inf."""
    try:
        f = float(v)
        if f != f or f == float('inf') or f == float('-inf'):
            return 0.0
        return round(f, 4)
    except (TypeError, ValueError):
        return 0.0
