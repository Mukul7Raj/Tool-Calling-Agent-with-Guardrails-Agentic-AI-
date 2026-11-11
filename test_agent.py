"""
test_agent.py - Unit and integration tests for the Tool-Calling Agent.
"""

import uuid
import pytest
from agent import create_agent
from tools import is_destructive_tool, execute_tool_with_retry
from database import get_logs

def test_guardrail_detection():
    assert is_destructive_tool("delete_record") is True
    assert is_destructive_tool("purge_data") is True
    assert is_destructive_tool("fetch_record") is False
    assert is_destructive_tool("send_notification") is False

def test_tool_retry_success():
    # Transient failure of 1 attempt; should succeed on attempt 2
    res, attempts = execute_tool_with_retry("send_notification", {"recipient": "test@test.com", "message": "hi", "fail_times": 1}, max_retries=2)
    assert res["status"] == "sent"
    assert attempts == 2

def test_tool_fallback():
    # Fails 3 times, exceeds max_retries=2, triggers fallback notification
    res, attempts = execute_tool_with_retry("send_notification", {"recipient": "test@test.com", "message": "hi", "fail_times": 3}, max_retries=2)
    assert res["status"] == "fallback_logged"

def test_agent_safe_execution():
    agent = create_agent()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    state = agent.invoke({
        "task_id": "test_safe",
        "task": "Fetch Alice record",
        "plan": [],
        "step_index": 0,
        "status": "planning",
        "requires_approval": False,
        "human_approved": False,
        "pending_step": None,
        "results": [],
        "error": None
    }, config=config)

    assert state.get("requires_approval") is False
    assert len(state.get("results", [])) > 0

def test_agent_guardrail_pause_and_approval():
    agent = create_agent()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. Trigger destructive action
    state = agent.invoke({
        "task_id": "test_destruct",
        "task": "Delete user Alice rec_101",
        "plan": [],
        "step_index": 0,
        "status": "planning",
        "requires_approval": False,
        "human_approved": False,
        "pending_step": None,
        "results": [],
        "error": None
    }, config=config)

    # Must be paused by guardrail
    assert state.get("status") == "awaiting_approval"
    assert state.get("requires_approval") is True
    assert state.get("pending_step", {}).get("tool") == "delete_record"

    # 2. Simulate human approval
    agent.update_state(config, {"human_approved": True, "status": "executing"})
    resumed_state = agent.invoke(None, config=config)

    # Must have executed delete_record after approval
    tools_executed = [r["tool"] for r in resumed_state.get("results", [])]
    assert "delete_record" in tools_executed

def test_database_audit_logs():
    logs = get_logs()
    assert isinstance(logs, list)
    assert len(logs) > 0
