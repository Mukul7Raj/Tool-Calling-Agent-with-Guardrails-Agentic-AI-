"""
tools.py - External tools, failure simulation, retries, and guardrail definitions.
"""

import time
from typing import Dict, Any, Tuple

# In-memory mock database for demo purposes
DEFAULT_MOCK_DATA = {
    "rec_101": {"id": "rec_101", "name": "Alice Johnson", "email": "alice@example.com", "role": "admin"},
    "rec_102": {"id": "rec_102", "name": "Bob Smith", "email": "bob@example.com", "role": "member"},
}
MOCK_DATA = DEFAULT_MOCK_DATA.copy()

def reset_mock_data():
    global MOCK_DATA
    MOCK_DATA = DEFAULT_MOCK_DATA.copy()

DESTRUCTIVE_TOOLS = {"delete_record", "purge_data", "drop_table"}

def is_destructive_tool(tool_name: str) -> bool:
    """Guardrail rule: identifies if a tool performs irreversible or destructive actions."""
    return tool_name.strip().lower() in DESTRUCTIVE_TOOLS

def fetch_record(record_id: str) -> Dict[str, Any]:
    """Safe read tool: queries a record by ID."""
    if record_id not in MOCK_DATA:
        return {"status": "found", "record": {"id": record_id, "name": f"User {record_id}", "email": f"{record_id}@example.com"}}
    return {"status": "found", "record": MOCK_DATA[record_id]}

def send_notification(recipient: str, message: str, fail_times: int = 0, current_attempt: int = 1) -> Dict[str, Any]:
    """External API tool: sends an alert/email with simulated transient failure & retry support."""
    if current_attempt <= fail_times:
        raise ConnectionError(f"Temporary 503 Service Unavailable (attempt {current_attempt}/{fail_times})")
    return {"status": "sent", "recipient": recipient, "message": message}

def fallback_notification(recipient: str, message: str) -> Dict[str, Any]:
    """Fallback tool: secondary delivery channel when primary notification fails."""
    return {"status": "fallback_logged", "recipient": recipient, "note": "Primary API failed; delivered via local queue"}

def delete_record(record_id: str) -> Dict[str, Any]:
    """Destructive action tool: deletes a record from the database."""
    MOCK_DATA.pop(record_id, None)
    return {"status": "deleted", "record_id": record_id}

def execute_tool_with_retry(tool_name: str, args: Dict[str, Any], max_retries: int = 2) -> Tuple[Dict[str, Any], int]:
    """Executes a tool with automatic retries and fallback upon repeated failures."""
    attempts = 0
    while attempts <= max_retries:
        attempts += 1
        try:
            if tool_name == "fetch_record":
                return fetch_record(args.get("record_id", "")), attempts
            elif tool_name == "send_notification":
                fail_times = args.get("fail_times", 0)
                return send_notification(args["recipient"], args["message"], fail_times=fail_times, current_attempt=attempts), attempts
            elif tool_name == "delete_record":
                return delete_record(args.get("record_id", "")), attempts
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except ConnectionError as err:
            if attempts <= max_retries:
                time.sleep(0.1)  # short backoff
                continue
            # Fallback path after retries exhausted
            if tool_name == "send_notification":
                fb_result = fallback_notification(args["recipient"], args["message"])
                return fb_result, attempts
            raise err
    raise RuntimeError(f"Tool {tool_name} failed after {max_retries} retries.")
