"""
Dashboard Service
-----------------
Dynamically computes KPIs and chart data from a DataFrame.
Only generates metrics that make sense for the actual data.
"""

import logging
import math
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def compute_dashboard(df: pd.DataFrame, version_label: str = '') -> Dict[str, Any]:
    """
    Analyse the DataFrame and return:
      - kpis:   list of {label, value, sub_label, icon, color}
      - charts: list of chart-spec dicts
      - filters: list of filterable column specs
    """
    kpis   = _compute_kpis(df)
    charts = _generate_charts(df)
    filters = _build_filters(df)

    return {
        'version_label': version_label,
        'total_rows':    len(df),
        'total_columns': len(df.columns),
        'columns':       list(df.columns),
        'kpis':          kpis,
        'charts':        charts,
        'filters':       filters,
    }


# ══════════════════════════════════════════════════════════════════════════════
# KPI computation
# ══════════════════════════════════════════════════════════════════════════════

def _compute_kpis(df: pd.DataFrame) -> List[Dict[str, Any]]:
    kpis = []

    # Always-present KPIs
    kpis.append({
        'label':     'Total Records',
        'value':     f"{len(df):,}",
        'raw_value': len(df),
        'sub_label': f"{len(df.columns)} columns",
        'icon':      'table',
        'color':     'blue',
    })

    # Missing values
    missing = int(df.isna().sum().sum())
    if missing > 0:
        kpis.append({
            'label':     'Missing Values',
            'value':     f"{missing:,}",
            'raw_value': missing,
            'sub_label': 'across all columns',
            'icon':      'alert-circle',
            'color':     'orange',
        })

    # Duplicate rows
    dups = int(df.duplicated().sum())
    if dups > 0:
        kpis.append({
            'label':     'Duplicate Rows',
            'value':     f"{dups:,}",
            'raw_value': dups,
            'sub_label': 'exact duplicates',
            'icon':      'copy',
            'color':     'red',
        })

    # Numeric column KPIs — only for columns that look like meaningful numbers
    numeric_kpi_added = 0
    for col in df.columns:
        if numeric_kpi_added >= 4:
            break
        numeric = pd.to_numeric(df[col], errors='coerce')
        valid   = numeric.dropna()
        if len(valid) < max(len(df) * 0.5, 2):
            continue

        col_lower = col.lower()

        # Revenue / Sales / Amount / Total → sum + mean
        if any(kw in col_lower for kw in ('sale', 'revenue', 'amount', 'total', 'price', 'cost', 'income', 'profit')):
            total = valid.sum()
            avg   = valid.mean()
            kpis.append({
                'label':     f"Total {col}",
                'value':     _fmt_number(total),
                'raw_value': float(total),
                'sub_label': f"Avg: {_fmt_number(avg)}",
                'icon':      'trending-up',
                'color':     'green',
            })
            numeric_kpi_added += 1

        elif any(kw in col_lower for kw in ('qty', 'quantity', 'count', 'units', 'orders')):
            total = valid.sum()
            kpis.append({
                'label':     f"Total {col}",
                'value':     f"{int(total):,}",
                'raw_value': int(total),
                'sub_label': f"Avg: {avg:.1f}" if 'avg' in dir() else '',
                'icon':      'package',
                'color':     'purple',
            })
            numeric_kpi_added += 1

    # Unique values in categorical columns
    cat_count = 0
    for col in df.columns:
        if cat_count >= 2:
            break
        series = df[col]
        numeric = pd.to_numeric(series, errors='coerce')
        if numeric.notna().sum() / max(len(series), 1) > 0.8:
            continue   # Skip numeric columns
        unique_n = series.nunique(dropna=True)
        col_lower = col.lower()
        if any(kw in col_lower for kw in ('customer', 'client', 'user', 'name', 'product', 'category', 'region', 'city')):
            kpis.append({
                'label':     f"Unique {col}",
                'value':     f"{unique_n:,}",
                'raw_value': unique_n,
                'sub_label': f"out of {len(series):,} records",
                'icon':      'users',
                'color':     'teal',
            })
            cat_count += 1

    return kpis


# ══════════════════════════════════════════════════════════════════════════════
# Chart generation
# ══════════════════════════════════════════════════════════════════════════════

def _generate_charts(df: pd.DataFrame) -> List[Dict[str, Any]]:
    charts = []

    numeric_cols = _get_numeric_cols(df)
    categorical_cols = _get_categorical_cols(df)
    date_cols = _get_date_cols(df)

    # Chart 1 — Category distribution (bar)
    if categorical_cols:
        cat_col = categorical_cols[0]
        counts  = df[cat_col].value_counts().head(15)
        charts.append({
            'id':     'cat_distribution',
            'title':  f"{cat_col} Distribution",
            'type':   'bar',
            'labels': counts.index.astype(str).tolist(),
            'values': counts.values.tolist(),
            'x_label': cat_col,
            'y_label': 'Count',
        })

    # Chart 2 — Numeric column overview (bar with top grouping)
    if categorical_cols and numeric_cols:
        cat_col = categorical_cols[0]
        num_col = numeric_cols[0]
        numeric = pd.to_numeric(df[num_col], errors='coerce')
        temp = df[[cat_col]].copy()
        temp[num_col] = numeric
        grouped = temp.groupby(cat_col)[num_col].sum().nlargest(15)
        charts.append({
            'id':     'top_by_numeric',
            'title':  f"Top {cat_col} by {num_col}",
            'type':   'bar',
            'labels': grouped.index.astype(str).tolist(),
            'values': grouped.values.tolist(),
            'x_label': cat_col,
            'y_label': num_col,
        })

    # Chart 3 — Time series (line) if a date column exists
    if date_cols and numeric_cols:
        date_col = date_cols[0]
        num_col  = numeric_cols[0]
        try:
            temp = df[[date_col, num_col]].copy()
            temp[date_col] = pd.to_datetime(temp[date_col], errors='coerce')
            temp[num_col]  = pd.to_numeric(temp[num_col], errors='coerce')
            temp = temp.dropna().sort_values(date_col)
            temp['_period'] = temp[date_col].dt.to_period('M').astype(str)
            ts = temp.groupby('_period')[num_col].sum().head(24)
            if len(ts) >= 2:
                charts.append({
                    'id':     'time_series',
                    'title':  f"{num_col} Over Time",
                    'type':   'line',
                    'labels': ts.index.tolist(),
                    'values': ts.values.tolist(),
                    'x_label': 'Period',
                    'y_label': num_col,
                })
        except Exception:
            pass

    # Chart 4 — Pie chart (second categorical column, or first if only one)
    if len(categorical_cols) >= 2:
        pie_col = categorical_cols[1]
    elif categorical_cols:
        pie_col = categorical_cols[0]
    else:
        pie_col = None

    if pie_col and pie_col != (charts[0].get('x_label') if charts else None):
        counts = df[pie_col].value_counts().head(8)
        if len(counts) >= 2:
            charts.append({
                'id':     'pie_chart',
                'title':  f"{pie_col} Share",
                'type':   'pie',
                'labels': counts.index.astype(str).tolist(),
                'values': counts.values.tolist(),
                'x_label': pie_col,
                'y_label': 'Count',
            })

    # Chart 5 — Numeric distribution (histogram-style bar)
    if len(numeric_cols) >= 2:
        num_col = numeric_cols[1]
        numeric = pd.to_numeric(df[num_col], errors='coerce').dropna()
        if len(numeric) >= 10:
            try:
                counts, edges = np.histogram(numeric, bins=10)
                labels = [f"{e:.1f}" for e in edges[:-1]]
                charts.append({
                    'id':     'numeric_distribution',
                    'title':  f"{num_col} Distribution",
                    'type':   'bar',
                    'labels': labels,
                    'values': counts.tolist(),
                    'x_label': num_col,
                    'y_label': 'Frequency',
                })
            except Exception:
                pass

    return charts


# ══════════════════════════════════════════════════════════════════════════════
# Filter generation
# ══════════════════════════════════════════════════════════════════════════════

def _build_filters(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Return a spec for each column that makes a useful filter."""
    filters = []
    for col in df.columns:
        series  = df[col]
        unique_n = series.nunique(dropna=True)
        numeric  = pd.to_numeric(series, errors='coerce')
        is_num   = numeric.notna().sum() / max(len(series), 1) > 0.8

        if is_num:
            filters.append({
                'column':    col,
                'type':      'range',
                'min_value': float(numeric.min()),
                'max_value': float(numeric.max()),
            })
        elif 2 <= unique_n <= 50:
            options = series.dropna().astype(str).unique().tolist()[:50]
            options.sort()
            filters.append({
                'column':  col,
                'type':    'select',
                'options': options,
            })
        elif unique_n > 50:
            filters.append({'column': col, 'type': 'text_search'})

    return filters


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_numeric_cols(df: pd.DataFrame, min_ratio: float = 0.5) -> List[str]:
    cols = []
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors='coerce')
        if numeric.notna().sum() / max(len(df), 1) >= min_ratio:
            cols.append(col)
    return cols


def _get_categorical_cols(df: pd.DataFrame, max_unique: int = 100) -> List[str]:
    cols = []
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors='coerce')
        if numeric.notna().sum() / max(len(df), 1) > 0.8:
            continue
        if 2 <= df[col].nunique(dropna=True) <= max_unique:
            cols.append(col)
    return cols


def _get_date_cols(df: pd.DataFrame) -> List[str]:
    cols = []
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(30)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors='coerce')
        if parsed.notna().sum() / max(len(sample), 1) >= 0.7:
            cols.append(col)
    return cols


def _fmt_number(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:,.2f}"
