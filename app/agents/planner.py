"""
Agent Planner (thin wrapper — main logic lives in excel_agent.py and groq_service.py)
"""
from app.agents.excel_agent import run_agent

__all__ = ['run_agent']
