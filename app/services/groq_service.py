"""
Groq AI Service
---------------
Integrates Groq API for:
  1. AI Insights - explain pre-computed statistics in plain English
  2. Agent Brain - understand natural-language commands, select a validated tool
  3. Result Explanation - narrate what the agent just did
  4. Cleaning Commentary - describe automatic cleaning results

Security: GROQ_API_KEY is read from environment only - never exposed to frontend.
Model:    Reads GROQ_MODEL env var at every call (default: groq/compound).
"""

import json
import logging
import os
import re
import time as _time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_MAX_TOKENS  = 1024
_TEMPERATURE = 0.1


# ══════════════════════════════════════════════════════════════════════════════
# Client + model helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_client():
    from groq import Groq
    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key:
        raise RuntimeError('GROQ_API_KEY environment variable is not set.')
    return Groq(api_key=api_key)


def _model() -> str:
    """Read model name at call time so .env changes take effect without restart."""
    return os.environ.get('GROQ_MODEL', 'groq/compound')


def _chat(messages: List[Dict[str, str]], max_tokens: int = _MAX_TOKENS) -> str:
    """
    Send a chat completion and return the response text.
    Automatically retries once on 429 rate-limit, waiting the suggested delay.
    """
    client = _get_client()
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=_model(),
                messages=messages,
                temperature=_TEMPERATURE,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            msg = str(exc)
            if '429' in msg and attempt == 0:
                # Parse "try again in Xs" from the error if available
                wait = 15
                m = re.search(r'try again in (\d+(?:\.\d+)?)s', msg)
                if m:
                    wait = min(int(float(m.group(1))) + 2, 45)
                logger.warning('Groq rate limit - waiting %ds before retry', wait)
                _time.sleep(wait)
                # Re-create client after waiting
                client = _get_client()
                continue
            raise
    raise RuntimeError('Groq rate limit - all retries exhausted.')


# ══════════════════════════════════════════════════════════════════════════════
# Robust JSON extractor
# Handles: clean JSON, markdown fences, <think> blocks, prose prefix
# ══════════════════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from any model output.
    Handles think-blocks, markdown fences, and leading prose.
    """
    # 1. Strip <think>...</think> reasoning blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # 2. Strip markdown fences
    text = re.sub(r'```(?:json)?', '', text)
    text = text.strip().strip('`').strip()
    # 3. Find first {...} JSON object (handles prose prefix)
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


# ══════════════════════════════════════════════════════════════════════════════
# Parameter normalisation
# Different model responses use slightly different param names - normalise here
# ══════════════════════════════════════════════════════════════════════════════

def _normalise_params(tool: str, params: dict) -> dict:
    """Ensure params match the exact keys expected by the tool dispatcher."""
    if not isinstance(params, dict):
        return {}
    p = dict(params)

    if tool == 'filter_data':
        if 'condition' in p and 'value' not in p:
            p['value'] = p.pop('condition')
        if 'filter_value' in p and 'value' not in p:
            p['value'] = p.pop('filter_value')
        if 'col' in p and 'column' not in p:
            p['column'] = p.pop('col')
        if 'value' in p and 'operator' not in p:
            p['operator'] = 'contains'

    elif tool == 'sort_data':
        if 'order' in p and 'ascending' not in p:
            p['ascending'] = p.pop('order') not in ('desc', 'descending', False)
        if 'col' in p and 'column' not in p:
            p['column'] = p.pop('col')

    elif tool == 'group_data':
        if 'group_column' in p and 'group_by' not in p:
            p['group_by'] = p.pop('group_column')
        if 'aggregate' in p and 'agg_func' not in p:
            p['agg_func'] = p.pop('aggregate')
        if 'value_column' in p and 'agg_column' not in p:
            p['agg_column'] = p.pop('value_column')

    elif tool in ('clean_column', 'standardize_values'):
        if 'col' in p and 'column' not in p:
            p['column'] = p.pop('col')

    elif tool == 'rename_column':
        if 'from' in p and 'old_name' not in p:
            p['old_name'] = p.pop('from')
        if 'to' in p and 'new_name' not in p:
            p['new_name'] = p.pop('to')

    elif tool == 'calculate_metric':
        if 'type' in p and 'metric' not in p:
            p['metric'] = p.pop('type')

    return p


# ══════════════════════════════════════════════════════════════════════════════
# INSIGHT GENERATION
# ══════════════════════════════════════════════════════════════════════════════

_INSIGHT_SYSTEM = (
    "You are a senior data analyst providing concise, factual insights about a "
    "dataset. You ONLY reference numbers and facts explicitly provided to you. "
    "You NEVER invent or estimate statistics. "
    "Respond with 4-8 bullet points in clear business language."
)


def generate_insights(stats_summary: str, dataset_name: str = 'Dataset') -> str:
    """
    Generate AI insights from pre-computed statistics.
    The model only explains numbers it receives - never invents figures.
    """
    user_msg = (
        f"Dataset: {dataset_name}\n\n"
        f"Computed Statistics:\n{stats_summary}\n\n"
        "Provide 4-8 concise, factual business insights based strictly "
        "on the numbers above. Do not invent any figures."
    )
    try:
        raw = _chat([
            {'role': 'system', 'content': _INSIGHT_SYSTEM},
            {'role': 'user',   'content': user_msg},
        ], max_tokens=700)
        return re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    except Exception as exc:
        logger.error('generate_insights error: %s', exc)
        return f'Insight generation unavailable: {exc}'


# ══════════════════════════════════════════════════════════════════════════════
# AGENT BRAIN - Intent Understanding + Tool Selection
# ══════════════════════════════════════════════════════════════════════════════

AVAILABLE_TOOLS = [
    'remove_duplicates',
    'remove_blank_rows',
    'find_missing_values',
    'clean_column',
    'rename_column',
    'standardize_values',
    'filter_data',
    'sort_data',
    'group_data',
    'calculate_metric',
    'create_summary',
    'generate_chart_data',
    'generate_insights',
    'export_excel',
    'export_csv',
]

_PLANNER_SYSTEM = """You are the planning brain of an AI data-processing agent.

TASK:
1. Understand the user's natural-language command about their dataset.
2. Choose exactly ONE tool from the validated list.
3. Extract the required parameters from the command and dataset context.
4. Return a JSON object ONLY - absolutely no prose, no markdown, no explanation outside the JSON.

VALIDATED TOOLS: """ + json.dumps(AVAILABLE_TOOLS) + """

PARAMETER SCHEMAS (use these exact key names):
- remove_duplicates:   {"subset": ["col1","col2"] or null}
- remove_blank_rows:   {}
- find_missing_values: {"column": "colname or null"}
- clean_column:        {"column": "colname", "operations": ["trim","lowercase","uppercase","titlecase"]}
- rename_column:       {"old_name": "current_name", "new_name": "desired_name"}
- standardize_values:  {"column": "colname", "case": "lower|upper|title"}
- filter_data:         {"column": "colname", "operator": "eq|ne|contains|startswith|gt|lt|gte|lte", "value": "filter_value"}
- sort_data:           {"column": "colname", "ascending": true or false}
- group_data:          {"group_by": "colname", "agg_column": "colname", "agg_func": "sum|mean|count|max|min"}
- calculate_metric:    {"metric": "total|mean|max|min|count", "column": "colname"}
- create_summary:      {}
- generate_chart_data: {"chart_type": "bar|line|pie|area", "x": "colname", "y": "colname"}
- generate_insights:   {}
- export_excel:        {}
- export_csv:          {}

REQUIRED OUTPUT FORMAT - return this JSON and nothing else:
{"tool": "tool_name", "params": {...}, "intent": "one sentence describing what you understood"}"""


def plan_agent_action(
    user_command: str,
    dataset_context: str,
    column_names: List[str],
) -> Dict[str, Any]:
    """
    Use Groq to understand the user command and select the correct tool + params.
    Returns {'tool': str, 'params': dict, 'intent': str}.
    Falls back to keyword matching if Groq fails or returns invalid JSON.
    """
    user_msg = (
        f"User command: {user_command}\n\n"
        f"Available columns: {', '.join(column_names)}\n\n"
        f"Dataset context:\n{dataset_context}"
    )

    raw = ''
    try:
        raw = _chat([
            {'role': 'system', 'content': _PLANNER_SYSTEM},
            {'role': 'user',   'content': user_msg},
        ], max_tokens=400)

        plan   = _extract_json(raw)
        tool   = plan.get('tool', '')
        params = plan.get('params', {})
        intent = plan.get('intent', '')

        if tool not in AVAILABLE_TOOLS:
            logger.warning('Groq returned unknown tool %r - falling back to keyword match', tool)
            tool   = _keyword_fallback(user_command)
            params = {}
            intent = f'(keyword fallback) {user_command}'

        params = _normalise_params(tool, params)
        return {'tool': tool, 'params': params, 'intent': intent}

    except json.JSONDecodeError as exc:
        logger.error('plan_agent_action JSON error: %s | raw=%r', exc, raw[:300])
        tool = _keyword_fallback(user_command)
        return {'tool': tool, 'params': {}, 'intent': f'(keyword fallback) {user_command}'}

    except ValueError:
        raise

    except Exception as exc:
        logger.error('plan_agent_action error: %s', exc)
        raise ValueError(f'Agent planning failed: {exc}')


def _keyword_fallback(command: str) -> str:
    """
    Keyword-based tool selection when Groq cannot be reached or returns bad JSON.
    Ensures the agent always returns a valid, runnable tool.
    """
    cmd = command.lower()
    if any(w in cmd for w in ('duplicate', 'dedup')):
        return 'remove_duplicates'
    if any(w in cmd for w in ('blank row', 'empty row', 'blank rows')):
        return 'remove_blank_rows'
    if any(w in cmd for w in ('missing', 'null values', 'na ')):
        return 'find_missing_values'
    if any(w in cmd for w in ('filter', 'show only', 'only show', 'where ', 'from ')):
        return 'filter_data'
    if any(w in cmd for w in ('sort', 'order by', 'highest', 'lowest', 'rank')):
        return 'sort_data'
    if any(w in cmd for w in ('group', 'aggregate', 'by category', 'breakdown')):
        return 'group_data'
    if any(w in cmd for w in ('total', 'sum ', 'average', 'mean', 'max ', 'min ', 'count ')):
        return 'calculate_metric'
    if any(w in cmd for w in ('rename', 'name column', 'change column name')):
        return 'rename_column'
    if any(w in cmd for w in ('clean column', 'trim', 'whitespace', 'lowercase', 'uppercase')):
        return 'clean_column'
    if any(w in cmd for w in ('standardize', 'normalise', 'normalize')):
        return 'standardize_values'
    if any(w in cmd for w in ('insight', 'analyse', 'analyze', 'tell me about', 'what does')):
        return 'generate_insights'
    if any(w in cmd for w in ('summary', 'summarize', 'summarise', 'describe', 'overview')):
        return 'create_summary'
    if any(w in cmd for w in ('chart', 'graph', 'plot', 'visuali')):
        return 'generate_chart_data'
    if 'excel' in cmd and ('download' in cmd or 'export' in cmd):
        return 'export_excel'
    if 'csv' in cmd and ('download' in cmd or 'export' in cmd):
        return 'export_csv'
    return 'create_summary'   # Safe default


# ══════════════════════════════════════════════════════════════════════════════
# RESULT EXPLANATION
# ══════════════════════════════════════════════════════════════════════════════

_EXPLAIN_SYSTEM = (
    "You are a helpful data assistant. Write a 2-4 sentence plain-English "
    "explanation of what was done and what the outcome means. "
    "Be factual - only reference numbers explicitly provided."
)


def explain_agent_result(
    user_command: str,
    tool_used: str,
    result_summary: str,
) -> str:
    """Generate a human-friendly explanation of what the agent just did."""
    user_msg = (
        f"User asked: {user_command}\n"
        f"Tool executed: {tool_used}\n"
        f"Result: {result_summary}"
    )
    try:
        raw = _chat([
            {'role': 'system', 'content': _EXPLAIN_SYSTEM},
            {'role': 'user',   'content': user_msg},
        ], max_tokens=250)
        return re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    except Exception as exc:
        logger.error('explain_agent_result error: %s', exc)
        return result_summary   # Fall back to raw summary


# ══════════════════════════════════════════════════════════════════════════════
# CLEANING COMMENTARY
# ══════════════════════════════════════════════════════════════════════════════

def explain_cleaning_result(cleaning_report: Dict[str, Any]) -> str:
    """Generate a natural-language summary of the automatic cleaning."""
    system = (
        "You are a data quality analyst. Given a cleaning report, write a clear "
        "2-4 sentence summary of what was found and fixed. Be factual."
    )
    user_msg = f"Cleaning report:\n{json.dumps(cleaning_report, indent=2)}"
    try:
        raw = _chat([
            {'role': 'system', 'content': system},
            {'role': 'user',   'content': user_msg},
        ], max_tokens=250)
        return re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    except Exception as exc:
        logger.error('explain_cleaning_result error: %s', exc)
        return cleaning_report.get('status', 'Cleaning completed.')
