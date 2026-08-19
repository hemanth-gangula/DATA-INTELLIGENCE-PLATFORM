"""
Agent Tools (the Agent's HANDS)
---------------------------------
Each function takes a pandas DataFrame and a params dict.
It performs ONE validated, deterministic data operation.
Returns (result_df, summary_str, columns_affected_count).

Rules:
- Tools may only perform what they are explicitly designed to do.
- Tools never execute arbitrary code.
- Tools always return a DataFrame + human-readable summary.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

ToolResult = Tuple[pd.DataFrame, str, int]   # (df, summary, cols_affected)


# ══════════════════════════════════════════════════════════════════════════════
# 1. remove_duplicates
# ══════════════════════════════════════════════════════════════════════════════

def remove_duplicates(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Remove exact duplicate rows. Optionally limited to a subset of columns."""
    subset = params.get('subset') or None
    if subset:
        # Validate columns exist
        subset = [c for c in subset if c in df.columns]
        if not subset:
            subset = None

    before = len(df)
    result = df.drop_duplicates(subset=subset).reset_index(drop=True)
    removed = before - len(result)
    scope = f" based on columns: {subset}" if subset else ""
    summary = (
        f"Removed {removed} duplicate row(s){scope}. "
        f"Rows: {before} -> {len(result)}."
    )
    return result, summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. remove_blank_rows
# ══════════════════════════════════════════════════════════════════════════════

def remove_blank_rows(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Remove rows where all cells are NaN or empty string."""
    mask = df.apply(
        lambda row: row.isna().all() or (row.astype(str).str.strip() == '').all(),
        axis=1
    )
    before = len(df)
    result = df[~mask].reset_index(drop=True)
    removed = before - len(result)
    summary = (
        f"Removed {removed} completely blank row(s). "
        f"Rows: {before} -> {len(result)}."
    )
    return result, summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. find_missing_values
# ══════════════════════════════════════════════════════════════════════════════

def find_missing_values(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """
    Report missing values per column (does NOT modify the DataFrame).
    """
    target_col = params.get('column')
    missing: Dict[str, int] = {}

    if target_col and target_col in df.columns:
        cols = [target_col]
    else:
        cols = list(df.columns)

    for col in cols:
        null_count  = int(df[col].isna().sum())
        empty_count = int((df[col].astype(str).str.strip() == '').sum())
        total = null_count + empty_count
        if total > 0:
            missing[col] = total

    if missing:
        lines = [f"  • {col}: {cnt} missing" for col, cnt in missing.items()]
        summary = "Missing values found:\n" + "\n".join(lines)
    else:
        summary = "No missing values found in the selected column(s)."

    return df.copy(), summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. clean_column
# ══════════════════════════════════════════════════════════════════════════════

def clean_column(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """
    Apply safe text operations to a specific column.
    Supported operations: trim, lowercase, uppercase, titlecase
    """
    col        = params.get('column', '')
    operations = params.get('operations', ['trim'])

    if col not in df.columns:
        # Try case-insensitive match
        match = [c for c in df.columns if c.lower() == col.lower()]
        if match:
            col = match[0]
        else:
            return df.copy(), f"Column '{col}' not found.", 0

    result = df.copy()
    applied = []

    for op in operations:
        op = op.strip().lower()
        if op == 'trim':
            result[col] = result[col].apply(
                lambda v: v.strip() if isinstance(v, str) else v
            )
            applied.append('trimmed whitespace')
        elif op == 'lowercase':
            result[col] = result[col].apply(
                lambda v: v.lower() if isinstance(v, str) else v
            )
            applied.append('converted to lowercase')
        elif op == 'uppercase':
            result[col] = result[col].apply(
                lambda v: v.upper() if isinstance(v, str) else v
            )
            applied.append('converted to uppercase')
        elif op in ('titlecase', 'title'):
            result[col] = result[col].apply(
                lambda v: v.title() if isinstance(v, str) else v
            )
            applied.append('converted to title case')

    summary = (
        f"Column '{col}': {', '.join(applied)}."
        if applied else f"No operations applied to column '{col}'."
    )
    return result, summary, 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. rename_column
# ══════════════════════════════════════════════════════════════════════════════

def rename_column(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Rename a column."""
    old_name = params.get('old_name', '')
    new_name = params.get('new_name', '')

    if not old_name or not new_name:
        return df.copy(), "rename_column requires 'old_name' and 'new_name'.", 0

    if old_name not in df.columns:
        # Case-insensitive fallback
        match = [c for c in df.columns if c.lower() == old_name.lower()]
        if match:
            old_name = match[0]
        else:
            return df.copy(), f"Column '{old_name}' not found.", 0

    result  = df.rename(columns={old_name: new_name})
    summary = f"Renamed column '{old_name}' -> '{new_name}'."
    return result, summary, 1


# ══════════════════════════════════════════════════════════════════════════════
# 6. standardize_values
# ══════════════════════════════════════════════════════════════════════════════

def standardize_values(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Standardise string values in a column to lower / upper / title case."""
    col  = params.get('column', '')
    case = params.get('case', 'title').lower()

    if col not in df.columns:
        match = [c for c in df.columns if c.lower() == col.lower()]
        if match:
            col = match[0]
        else:
            return df.copy(), f"Column '{col}' not found.", 0

    result = df.copy()
    fn_map = {'lower': str.lower, 'upper': str.upper, 'title': str.title}
    fn = fn_map.get(case, str.title)
    result[col] = result[col].apply(lambda v: fn(v) if isinstance(v, str) else v)
    summary = f"Standardised column '{col}' values to {case} case."
    return result, summary, 1


# ══════════════════════════════════════════════════════════════════════════════
# 7. filter_data
# ══════════════════════════════════════════════════════════════════════════════

_FILTER_OPS = {
    'eq':         lambda s, v: s.astype(str).str.strip().str.lower() == str(v).lower(),
    'ne':         lambda s, v: s.astype(str).str.strip().str.lower() != str(v).lower(),
    'contains':   lambda s, v: s.astype(str).str.lower().str.contains(str(v).lower(), na=False),
    'startswith': lambda s, v: s.astype(str).str.lower().str.startswith(str(v).lower(), na=False),
    'gt':         lambda s, v: pd.to_numeric(s, errors='coerce') > _safe_num(v),
    'lt':         lambda s, v: pd.to_numeric(s, errors='coerce') < _safe_num(v),
    'gte':        lambda s, v: pd.to_numeric(s, errors='coerce') >= _safe_num(v),
    'lte':        lambda s, v: pd.to_numeric(s, errors='coerce') <= _safe_num(v),
}


def filter_data(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Filter rows by a column condition."""
    col      = params.get('column', '')
    operator = params.get('operator', 'eq')
    value    = params.get('value', '')

    if col not in df.columns:
        match = [c for c in df.columns if c.lower() == col.lower()]
        if match:
            col = match[0]
        else:
            return df.copy(), f"Column '{col}' not found.", 0

    op_fn = _FILTER_OPS.get(operator)
    if not op_fn:
        return df.copy(), f"Unknown operator '{operator}'.", 0

    before = len(df)
    mask   = op_fn(df[col], value)
    result = df[mask].reset_index(drop=True)
    summary = (
        f"Filtered '{col}' {operator} '{value}'. "
        f"Rows: {before} -> {len(result)} matching records."
    )
    return result, summary, 1


# ══════════════════════════════════════════════════════════════════════════════
# 8. sort_data
# ══════════════════════════════════════════════════════════════════════════════

def sort_data(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Sort the DataFrame by a column."""
    col       = params.get('column', '')
    ascending = params.get('ascending', True)

    if col not in df.columns:
        match = [c for c in df.columns if c.lower() == col.lower()]
        if match:
            col = match[0]
        else:
            return df.copy(), f"Column '{col}' not found.", 0

    # Try numeric sort; fall back to string
    numeric = pd.to_numeric(df[col], errors='coerce')
    if numeric.notna().sum() / max(len(df), 1) > 0.8:
        sort_key = numeric
        result = df.assign(__sort_key=sort_key).sort_values(
            '__sort_key', ascending=ascending
        ).drop(columns='__sort_key').reset_index(drop=True)
    else:
        result = df.sort_values(col, ascending=ascending).reset_index(drop=True)

    direction = 'ascending' if ascending else 'descending'
    summary   = f"Sorted by '{col}' ({direction}). {len(result)} rows."
    return result, summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 9. group_data
# ══════════════════════════════════════════════════════════════════════════════

def group_data(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """
    Group by a column and aggregate another column.
    Returns a SUMMARY DataFrame (not the original).
    """
    group_by   = params.get('group_by', '')
    agg_col    = params.get('agg_column', '')
    agg_func   = params.get('agg_func', 'count').lower()

    valid_funcs = {'sum', 'mean', 'count', 'max', 'min'}
    if agg_func not in valid_funcs:
        agg_func = 'count'

    if group_by not in df.columns:
        match = [c for c in df.columns if c.lower() == group_by.lower()]
        group_by = match[0] if match else ''

    if not group_by:
        return df.copy(), f"Group-by column not found.", 0

    if agg_col and agg_col not in df.columns:
        match = [c for c in df.columns if c.lower() == agg_col.lower()]
        agg_col = match[0] if match else ''

    try:
        if agg_col and agg_func != 'count':
            numeric_col = pd.to_numeric(df[agg_col], errors='coerce')
            temp = df.copy()
            temp[agg_col] = numeric_col
            grouped = getattr(temp.groupby(group_by)[agg_col], agg_func)()
        else:
            grouped = df.groupby(group_by).size()
            grouped.name = 'count'

        result = grouped.reset_index().sort_values(
            grouped.name if hasattr(grouped, 'name') else agg_col or 'count',
            ascending=False
        )

        summary = (
            f"Grouped by '{group_by}', {agg_func} of '{agg_col or 'rows'}'. "
            f"{len(result)} groups found."
        )
        return result, summary, 2
    except Exception as exc:
        logger.error('group_data error: %s', exc)
        return df.copy(), f"Grouping failed: {exc}", 0


# ══════════════════════════════════════════════════════════════════════════════
# 10. calculate_metric
# ══════════════════════════════════════════════════════════════════════════════

def calculate_metric(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Calculate a single aggregate metric on a numeric column."""
    metric = params.get('metric', 'count').lower()
    col    = params.get('column', '')

    if col and col not in df.columns:
        match = [c for c in df.columns if c.lower() == col.lower()]
        col   = match[0] if match else ''

    if metric == 'count':
        value   = len(df)
        summary = f"Total rows: {value:,}"
        return df.copy(), summary, 0

    if not col:
        return df.copy(), "A column name is required for this metric.", 0

    numeric = pd.to_numeric(df[col], errors='coerce').dropna()
    if numeric.empty:
        return df.copy(), f"Column '{col}' has no numeric values.", 0

    fn_map = {
        'total': numeric.sum,
        'sum':   numeric.sum,
        'mean':  numeric.mean,
        'avg':   numeric.mean,
        'max':   numeric.max,
        'min':   numeric.min,
    }
    fn = fn_map.get(metric)
    if not fn:
        return df.copy(), f"Unknown metric '{metric}'.", 0

    value   = fn()
    summary = f"{metric.capitalize()} of '{col}': {value:,.2f}"
    return df.copy(), summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 11. create_summary
# ══════════════════════════════════════════════════════════════════════════════

def create_summary(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Return a descriptive statistics summary of the DataFrame."""
    lines = [f"Dataset Summary - {len(df):,} rows x {len(df.columns)} columns"]
    lines.append("")

    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors='coerce')
        if numeric.notna().sum() > 0:
            lines.append(
                f"  {col}: min={numeric.min():.2f}, max={numeric.max():.2f}, "
                f"mean={numeric.mean():.2f}, nulls={df[col].isna().sum()}"
            )
        else:
            lines.append(
                f"  {col}: unique={df[col].nunique()}, "
                f"nulls={df[col].isna().sum()}"
            )

    summary = "\n".join(lines)
    return df.copy(), summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 12. generate_chart_data
# ══════════════════════════════════════════════════════════════════════════════

def generate_chart_data(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """
    Prepare chart-ready data. Does NOT modify the working DataFrame.
    The summary contains JSON-serialisable chart data.
    """
    import json

    chart_type = params.get('chart_type', 'bar')
    x_col      = params.get('x', '')
    y_col      = params.get('y', '')

    if x_col not in df.columns:
        match = [c for c in df.columns if c.lower() == x_col.lower()]
        x_col = match[0] if match else (df.columns[0] if len(df.columns) > 0 else '')

    if y_col not in df.columns:
        match = [c for c in df.columns if c.lower() == y_col.lower()]
        y_col = match[0] if match else ''

    if not x_col:
        return df.copy(), "Could not identify chart columns.", 0

    if y_col:
        numeric = pd.to_numeric(df[y_col], errors='coerce')
        chart_df = pd.DataFrame({x_col: df[x_col], y_col: numeric})
        chart_df = chart_df.dropna().head(50)
        chart_data = {
            'type':   chart_type,
            'labels': chart_df[x_col].astype(str).tolist(),
            'values': chart_df[y_col].tolist(),
            'x_label': x_col,
            'y_label': y_col,
        }
    else:
        counts = df[x_col].value_counts().head(20)
        chart_data = {
            'type':    chart_type,
            'labels':  counts.index.astype(str).tolist(),
            'values':  counts.values.tolist(),
            'x_label': x_col,
            'y_label': 'Count',
        }

    summary = json.dumps(chart_data)
    return df.copy(), summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# 13–15. generate_insights / export_excel / export_csv
# ══════════════════════════════════════════════════════════════════════════════

def generate_insights(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Signal the caller to regenerate AI insights (no DF modification)."""
    summary = "REGENERATE_INSIGHTS"
    return df.copy(), summary, 0


def export_excel(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Signal the caller that an Excel export is ready (no DF modification)."""
    summary = f"Excel export ready. {len(df):,} rows x {len(df.columns)} columns."
    return df.copy(), summary, 0


def export_csv(df: pd.DataFrame, params: Dict[str, Any]) -> ToolResult:
    """Signal the caller that a CSV export is ready (no DF modification)."""
    summary = f"CSV export ready. {len(df):,} rows x {len(df.columns)} columns."
    return df.copy(), summary, 0


# ══════════════════════════════════════════════════════════════════════════════
# Tool dispatcher
# ══════════════════════════════════════════════════════════════════════════════

_TOOL_REGISTRY = {
    'remove_duplicates':   remove_duplicates,
    'remove_blank_rows':   remove_blank_rows,
    'find_missing_values': find_missing_values,
    'clean_column':        clean_column,
    'rename_column':       rename_column,
    'standardize_values':  standardize_values,
    'filter_data':         filter_data,
    'sort_data':           sort_data,
    'group_data':          group_data,
    'calculate_metric':    calculate_metric,
    'create_summary':      create_summary,
    'generate_chart_data': generate_chart_data,
    'generate_insights':   generate_insights,
    'export_excel':        export_excel,
    'export_csv':          export_csv,
}


def dispatch_tool(
    tool_name: str,
    df: pd.DataFrame,
    params: Dict[str, Any],
) -> ToolResult:
    """
    Execute a validated tool by name.
    Raises ValueError if the tool name is unknown.
    """
    fn = _TOOL_REGISTRY.get(tool_name)
    if fn is None:
        raise ValueError(
            f"Unknown tool '{tool_name}'. "
            f"Available: {list(_TOOL_REGISTRY.keys())}"
        )
    return fn(df, params)


def list_tools() -> List[str]:
    return list(_TOOL_REGISTRY.keys())


# ── Private helper ─────────────────────────────────────────────────────────────

def _safe_num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
