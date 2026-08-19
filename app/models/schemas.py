"""
Data models / schema definitions used across services.
These are plain dataclasses – no ORM dependency.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class DatasetRecord:
    id: str
    name: str
    original_filename: str
    upload_timestamp: str
    sheet_name: str
    total_rows: int
    total_columns: int
    current_version_id: Optional[str] = None
    status: str = 'active'


@dataclass
class DatasetVersion:
    id: str
    dataset_id: str
    version_number: int
    version_type: str           # 'original' | 'automatic_cleaned' | 'agent_processed'
    label: str
    user_command: Optional[str] = None
    agent_action: Optional[str] = None
    rows_before: int = 0
    rows_after: int = 0
    columns_affected: int = 0
    processing_summary: Optional[str] = None
    file_path_excel: Optional[str] = None
    file_path_csv: Optional[str] = None
    storage_url_excel: Optional[str] = None
    storage_url_csv: Optional[str] = None
    parent_version_id: Optional[str] = None
    created_at: Optional[str] = None
    is_current: bool = False


@dataclass
class CleaningOperation:
    id: str
    dataset_id: str
    version_id: str
    duplicates_found: int = 0
    duplicates_removed: int = 0
    blank_rows_found: int = 0
    blank_rows_removed: int = 0
    empty_columns_removed: int = 0
    whitespace_fixed: int = 0
    columns_modified: int = 0
    missing_values_count: int = 0
    issues_remaining: int = 0
    cleaning_required: bool = False
    cleaning_summary: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AgentAction:
    id: str
    dataset_id: str
    version_id: str
    user_command: str
    intent: str
    tool_used: str
    tool_params: Dict[str, Any] = field(default_factory=dict)
    result_summary: str = ''
    rows_before: int = 0
    rows_after: int = 0
    success: bool = True
    error_message: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class InsightRecord:
    id: str
    dataset_id: str
    version_id: str
    insight_text: str
    insight_type: str = 'general'
    created_at: Optional[str] = None
