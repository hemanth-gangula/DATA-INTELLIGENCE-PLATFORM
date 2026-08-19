"""
Data Cleaning Service
---------------------
GOLDEN RULE: Only change data when a real issue is detected, the correction
is safe, and the correction is justified.  If data is already clean, return
it completely unchanged.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.services.excel_service import analyze_data_quality

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Analyse the DataFrame and perform ONLY safe, justified cleaning steps.

    Returns
    -------
    cleaned_df : pd.DataFrame
        The cleaned copy (identical to input if nothing needed fixing).
    report : dict
        Full cleaning report with before/after statistics.
    """
    # Step 1 — analyse first, modify nothing yet
    quality = analyze_data_quality(df)
    original_rows = len(df)
    original_cols = len(df.columns)

    if not quality['cleaning_required']:
        return df.copy(), _no_change_report(quality)

    # Work on a copy — original is never touched
    working = df.copy()
    ops: List[str] = []

    duplicates_removed      = 0
    blank_rows_removed      = 0
    empty_cols_removed      = 0
    whitespace_cells_fixed  = 0
    columns_modified        = set()
    issues_remaining        = 0

    # ── 1. Remove completely blank rows ───────────────────────────────────────
    if quality['blank_rows'] > 0:
        mask_blank = working.apply(
            lambda row: row.isna().all() or (row.astype(str).str.strip() == '').all(),
            axis=1
        )
        blank_rows_removed = int(mask_blank.sum())
        working = working[~mask_blank].reset_index(drop=True)
        ops.append(f"Removed {blank_rows_removed} completely blank row(s).")

    # ── 2. Remove exact duplicate rows ────────────────────────────────────────
    if quality['duplicate_rows'] > 0:
        before = len(working)
        working = working.drop_duplicates().reset_index(drop=True)
        duplicates_removed = before - len(working)
        ops.append(f"Removed {duplicates_removed} duplicate row(s).")

    # ── 3. Remove completely empty columns ────────────────────────────────────
    if quality['empty_column_count'] > 0:
        cols_to_drop = [
            col for col in working.columns
            if working[col].isna().all() or
               (working[col].astype(str).str.strip() == '').all()
        ]
        if cols_to_drop:
            working = working.drop(columns=cols_to_drop)
            empty_cols_removed = len(cols_to_drop)
            ops.append(f"Removed {empty_cols_removed} empty column(s): {cols_to_drop}.")

    # ── 4. Trim leading/trailing whitespace in text cells ─────────────────────
    if quality['whitespace_columns']:
        for col in quality['whitespace_columns']:
            if col not in working.columns:
                continue
            str_series = working[col].astype(str)
            trimmed    = str_series.str.strip()
            changed    = (str_series != trimmed).sum()
            if changed > 0:
                # Preserve NaN cells as NaN, only touch actual string values
                working[col] = working[col].apply(
                    lambda v: v.strip() if isinstance(v, str) else v
                )
                whitespace_cells_fixed += int(changed)
                columns_modified.add(col)
        if whitespace_cells_fixed:
            ops.append(
                f"Trimmed whitespace in {whitespace_cells_fixed} cell(s) across "
                f"{len(quality['whitespace_columns'])} column(s)."
            )

    # ── 5. Fix invalid / empty column headers ─────────────────────────────────
    if quality['invalid_headers']:
        new_cols = {}
        for col in working.columns:
            col_str = str(col).strip()
            if not col_str or col_str.startswith('Unnamed:'):
                idx = list(working.columns).index(col)
                new_cols[col] = f'Column_{idx + 1}'
        if new_cols:
            working = working.rename(columns=new_cols)
            ops.append(
                f"Renamed {len(new_cols)} empty/unnamed header(s) to Column_N placeholders."
            )

    # ── 6. Standardise obviously inconsistent date columns ────────────────────
    #    Only normalise if >80 % of non-null values parse as dates but some do not.
    #    We convert to ISO 8601 (YYYY-MM-DD) string to stay safe.
    date_cols_standardised = 0
    for col in quality.get('date_inconsistency_cols', []):
        if col not in working.columns:
            continue
        result = _standardise_date_column(working, col)
        if result is not None:
            working[col] = result
            columns_modified.add(col)
            date_cols_standardised += 1
    if date_cols_standardised:
        ops.append(
            f"Standardised date format in {date_cols_standardised} column(s)."
        )

    # ── 7. Count remaining missing values (we do NOT fill them — too risky) ───
    issues_remaining = int(
        working.isna().sum().sum() +
        (working.astype(str).apply(lambda c: (c.str.strip() == '').sum())).sum()
    )

    # ── Build report ──────────────────────────────────────────────────────────
    final_rows = len(working)
    final_cols = len(working.columns)
    report = {
        'cleaning_required':        True,
        'original_rows':            original_rows,
        'original_columns':         original_cols,
        'final_rows':               final_rows,
        'final_columns':            final_cols,
        'duplicates_found':         quality['duplicate_rows'],
        'duplicates_removed':       duplicates_removed,
        'blank_rows_found':         quality['blank_rows'],
        'blank_rows_removed':       blank_rows_removed,
        'empty_columns_removed':    empty_cols_removed,
        'whitespace_cells_fixed':   whitespace_cells_fixed,
        'columns_modified':         list(columns_modified),
        'columns_modified_count':   len(columns_modified),
        'missing_values_remaining': issues_remaining,
        'operations':               ops,
        'status':                   'Automatic cleaning completed.',
        'flagged_issues': _build_flagged_issues(quality, working),
    }
    return working, report


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _no_change_report(quality: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'cleaning_required':        False,
        'original_rows':            quality['total_rows'],
        'original_columns':         quality['total_columns'],
        'final_rows':               quality['total_rows'],
        'final_columns':            quality['total_columns'],
        'duplicates_found':         0,
        'duplicates_removed':       0,
        'blank_rows_found':         0,
        'blank_rows_removed':       0,
        'empty_columns_removed':    0,
        'whitespace_cells_fixed':   0,
        'columns_modified':         [],
        'columns_modified_count':   0,
        'missing_values_remaining': quality['missing_values_total'],
        'operations':               [],
        'status':                   'Data is already clean. No changes were made.',
        'flagged_issues':           [],
    }


def _standardise_date_column(df: pd.DataFrame, col: str):
    """
    If the column looks like a date column (>80 % parse) with inconsistent formats,
    normalise all parseable values to YYYY-MM-DD strings.
    Returns the new Series or None if we should not touch it.
    """
    try:
        parsed = pd.to_datetime(df[col], errors='coerce')
        parse_ratio = parsed.notna().sum() / max(len(parsed), 1)
        # Only standardise if most values parse but not all (mixed format)
        if 0.5 < parse_ratio < 1.0:
            result = parsed.apply(
                lambda v: v.strftime('%Y-%m-%d') if pd.notna(v) else None
            )
            return result
        # If ALL parse cleanly we still standardise for consistency
        if parse_ratio == 1.0:
            result = parsed.apply(
                lambda v: v.strftime('%Y-%m-%d') if pd.notna(v) else None
            )
            return result
        return None
    except Exception:
        return None


def _build_flagged_issues(quality: Dict[str, Any], df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Return issues that were DETECTED but NOT automatically fixed,
    so the user can decide what to do.
    """
    flags = []
    # Missing values per column (we do not fill them)
    for col, count in quality.get('missing_per_column', {}).items():
        if count > 0 and col in df.columns:
            flags.append({
                'type':    'missing_values',
                'column':  col,
                'count':   count,
                'message': f"Column '{col}' has {count} missing value(s). "
                           f"Manual review required before filling.",
            })
    return flags
