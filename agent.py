"""
agent.py - LangGraph Planner-Executor Agent with Guardrails & Human-in-the-Loop.
"""

import os
import json
import uuid
from typing import TypedDict, List, Dict, Any, Optional
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from tools import is_destructive_tool, execute_tool_with_retry
from database import log_step

load_dotenv()

class AgentState(TypedDict):
    task_id: str
    task: str
    plan: List[Dict[str, Any]]
    step_index: int
    status: str  # "planning", "awaiting_approval", "executing", "completed", "rejected"
    requires_approval: bool
    human_approved: bool
    pending_step: Optional[Dict[str, Any]]
    results: List[Dict[str, Any]]
    error: Optional[str]

def plan_with_llm_or_fallback(task: str) -> List[Dict[str, Any]]:
    """Generates plan using OpenAI if key exists, else deterministic rule planner."""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and not api_key.startswith("your_"):
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            sys_prompt = (
                "You are a task decomposition planner. Available tools: fetch_record(record_id), "
                "send_notification(recipient, message, fail_times), delete_record(record_id). "
                "Output ONLY a valid JSON array of objects with keys 'tool' and 'args'."
            )
            resp = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=task)])
            return json.loads(resp.content.strip("` \n").replace("json\n", ""))
        except Exception as e:
            print(f"[Planner] LLM planning failed ({e}); falling back to rule planner.")

    # Rule-based fallback planner
    task_lower = task.lower()
    plan = []
    if any(k in task_lower for k in ("delete", "remove", "purge", "drop", "destroy")):
        plan.append({"tool": "fetch_record", "args": {"record_id": "rec_101"}})
        plan.append({"tool": "delete_record", "args": {"record_id": "rec_101"}})
    elif any(k in task_lower for k in ("notif", "alert", "email", "message", "send")):
        plan.append({"tool": "fetch_record", "args": {"record_id": "rec_101"}})
        simulate_fail = 2 if ("fail" in task_lower or "retry" in task_lower) else 0
        plan.append({"tool": "send_notification", "args": {"recipient": "alice@example.com", "message": "Quarterly audit complete", "fail_times": simulate_fail}})
    else:
        plan.append({"tool": "fetch_record", "args": {"record_id": "rec_101"}})
    return plan

def planner_node(state: AgentState) -> Dict[str, Any]:
    """Decomposes the task into an ordered sequence of tool invocations."""
    plan = plan_with_llm_or_fallback(state["task"])
    log_step(state["task_id"], "PLANNER", "generate_plan", {"task": state["task"], "plan": plan}, "SUCCESS")
    return {"plan": plan, "step_index": 0, "status": "executing", "results": []}

def guardrail_node(state: AgentState) -> Dict[str, Any]:
    """Inspects pending tool call. Pauses execution for human confirmation if destructive."""
    if state["step_index"] >= len(state["plan"]):
        return {"status": "completed", "requires_approval": False}

    current_step = state["plan"][state["step_index"]]
    tool_name = current_step.get("tool", "")

    if is_destructive_tool(tool_name) and not state.get("human_approved", False):
        log_step(
            state["task_id"], "GUARDRAIL", "block_destructive_action",
            {"tool": tool_name, "args": current_step.get("args")}, "AWAITING_APPROVAL"
        )
        return {
            "status": "awaiting_approval",
            "requires_approval": True,
            "pending_step": current_step
        }

    return {"status": "executing", "requires_approval": False, "pending_step": current_step}

def executor_node(state: AgentState) -> Dict[str, Any]:
    """Executes the tool with retries & fallback, records results, and logs step."""
    step = state["plan"][state["step_index"]]
    tool_name = step["tool"]
    args = step["args"]

    try:
        result, attempts = execute_tool_with_retry(tool_name, args, max_retries=2)
        log_step(state["task_id"], "EXECUTOR", tool_name, {"args": args, "result": result, "attempts": attempts}, "SUCCESS")
        new_results = list(state.get("results", []))
        new_results.append({"step": state["step_index"] + 1, "tool": tool_name, "result": result, "attempts": attempts})
        return {
            "results": new_results,
            "step_index": state["step_index"] + 1,
            "human_approved": False,  # reset after executing approved step
            "requires_approval": False,
            "status": "executing"
        }
    except Exception as e:
        log_step(state["task_id"], "EXECUTOR", tool_name, {"args": args, "error": str(e)}, "FAILED")
        return {"error": str(e), "status": "failed"}

def route_after_guardrail(state: AgentState) -> str:
    """Branches to executor or pauses if human approval is needed."""
    if state.get("status") == "awaiting_approval":
        return END
    if state.get("status") == "completed" or state["step_index"] >= len(state["plan"]):
        return END
    return "executor"

def route_after_executor(state: AgentState) -> str:
    """Loops back to guardrail check for next step or ends."""
    if state.get("status") == "failed":
        return END
    if state["step_index"] >= len(state["plan"]):
        return END
    return "guardrail"

def create_agent():
    """Builds and compiles the LangGraph state machine."""
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("executor", executor_node)

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "guardrail")
    workflow.add_conditional_edges("guardrail", route_after_guardrail, ["executor", END])
    workflow.add_conditional_edges("executor", route_after_executor, ["guardrail", END])

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
