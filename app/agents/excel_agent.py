"""
Excel Agent  —  Brain (Groq) + Hands (Tools)
--------------------------------------------
Orchestrates a complete agent turn:
  1. Load current version DataFrame from storage
  2. Ask Groq to plan the action (Brain)
  3. Execute the selected tool (Hands)
  4. Save result as a new version
  5. Persist agent action record
  6. Return a structured result
"""

import logging
from typing import Any, Dict, Optional

from app.agents.tools import dispatch_tool
from app.services import supabase_service as sb
from app.services import groq_service, version_service
from app.services.excel_service import build_sample_for_ai

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(
    dataset_id: str,
    user_command: str,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a full agent turn.

    Parameters
    ----------
    dataset_id   : str — the dataset to operate on
    user_command : str — natural-language command from the user
    version_id   : str | None — explicit version to operate on;
                   defaults to the current version for the dataset

    Returns
    -------
    dict with keys:
      success, tool_used, intent, result_summary, ai_explanation,
      new_version_id, new_version_number, rows_before, rows_after,
      chart_data (optional), error (on failure)
    """

    # ── 1. Resolve the version to operate on ──────────────────────────────────
    if version_id:
        version = sb.get_version(version_id)
    else:
        version = sb.get_current_version(dataset_id)

    if not version:
        return _fail('No active dataset version found. Please upload a file first.')

    # ── 2. Load the DataFrame ──────────────────────────────────────────────────
    df = version_service.load_version_dataframe(version)
    if df is None:
        return _fail('Could not load dataset from storage.')

    # ── 3. Build compact context for the AI ───────────────────────────────────
    dataset_context = build_sample_for_ai(df, n_rows=20)
    column_names    = list(df.columns)

    # ── 4. Groq Brain: understand intent, select tool + params ────────────────
    try:
        plan = groq_service.plan_agent_action(
            user_command=user_command,
            dataset_context=dataset_context,
            column_names=column_names,
        )
    except Exception as exc:
        logger.error('Agent planning failed: %s', exc)
        return _fail(f'AI planning error: {exc}')

    tool_name = plan['tool']
    params    = plan['params']
    intent    = plan['intent']
    logger.info('Agent plan — tool=%s params=%s intent=%s', tool_name, params, intent)

    # ── 5. Execute the tool (Hands) ────────────────────────────────────────────
    rows_before = len(df)
    try:
        result_df, raw_summary, cols_affected = dispatch_tool(tool_name, df, params)
    except Exception as exc:
        logger.error('Tool execution failed: %s', exc)
        return _fail(f'Tool execution error: {exc}')

    rows_after = len(result_df)

    # ── 6. Handle special signals from tools ──────────────────────────────────
    chart_data   = None
    is_read_only = tool_name in (
        'find_missing_values', 'calculate_metric', 'create_summary',
        'generate_insights', 'export_excel', 'export_csv', 'generate_chart_data'
    )

    if tool_name == 'generate_chart_data':
        import json
        try:
            chart_data = json.loads(raw_summary)
        except Exception:
            chart_data = None

    if tool_name == 'generate_insights':
        # Trigger a fresh AI insights generation but do not change the DF
        raw_summary = 'Insights regenerated. Please refresh the Insights panel.'

    # ── 7. Get AI explanation of what happened ────────────────────────────────
    try:
        ai_explanation = groq_service.explain_agent_result(
            user_command=user_command,
            tool_used=tool_name,
            result_summary=raw_summary,
        )
    except Exception:
        ai_explanation = raw_summary

    # ── 8. Persist new version (only for operations that modify data) ──────────
    new_version = None
    if not is_read_only:
        dataset    = sb.get_dataset(dataset_id)
        sheet_name = (dataset or {}).get('sheet_name', 'Sheet1')
        orig_fname = (dataset or {}).get('original_filename', '')

        try:
            new_version = version_service.create_agent_version(
                dataset_id=dataset_id,
                parent_version_id=version['id'],
                parent_version_number=version['version_number'],
                df_processed=result_df,
                df_before=df,
                sheet_name=sheet_name,
                user_command=user_command,
                agent_action=tool_name,
                columns_affected=cols_affected,
                processing_summary=raw_summary,
                original_filename=orig_fname,
            )
        except Exception as exc:
            logger.error('Version creation failed: %s', exc)
            # Continue — return result even if storage fails
            new_version = None

    # ── 9. Save agent action record ───────────────────────────────────────────
    new_version_id = (new_version or {}).get('id') or version['id']
    try:
        sb.save_agent_action({
            'dataset_id':    dataset_id,
            'version_id':    new_version_id,
            'user_command':  user_command,
            'intent':        intent,
            'tool_used':     tool_name,
            'tool_params':   params,
            'result_summary': raw_summary,
            'rows_before':   rows_before,
            'rows_after':    rows_after,
            'success':       True,
        })
    except Exception as exc:
        logger.warning('Could not save agent action: %s', exc)

    # ── 10. Build response ────────────────────────────────────────────────────
    return {
        'success':            True,
        'tool_used':          tool_name,
        'intent':             intent,
        'result_summary':     raw_summary,
        'ai_explanation':     ai_explanation,
        'new_version_id':     (new_version or {}).get('id'),
        'new_version_number': (new_version or {}).get('version_number'),
        'rows_before':        rows_before,
        'rows_after':         rows_after,
        'cols_affected':      cols_affected,
        'is_read_only':       is_read_only,
        'chart_data':         chart_data,
        'download_excel':     (new_version or {}).get('storage_url_excel'),
        'download_csv':       (new_version or {}).get('storage_url_csv'),
    }


# ── Helper ─────────────────────────────────────────────────────────────────────

def _fail(message: str) -> Dict[str, Any]:
    return {
        'success':        False,
        'error':          message,
        'tool_used':      None,
        'intent':         None,
        'result_summary': message,
        'ai_explanation': message,
        'new_version_id': None,
        'rows_before':    0,
        'rows_after':     0,
        'chart_data':     None,
    }
