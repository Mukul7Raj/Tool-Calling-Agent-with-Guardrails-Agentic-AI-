"""
app.py - Lightweight Streamlit UI for visual agent execution, guardrails, and HITL.
"""

import uuid
import streamlit as st
from agent import create_agent
from database import get_logs

st.set_page_config(page_title="Tool-Calling Agent with Guardrails", layout="wide")
st.title("🛡️ Tool-Calling Agent with Guardrails")
st.caption("Planner-Executor Architecture in LangGraph with Human-in-the-Loop & Audit Logging")

if "agent" not in st.session_state:
    st.session_state.agent = create_agent()
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "agent_state" not in st.session_state:
    st.session_state.agent_state = None

col1, col2 = st.columns([2, 1])

with col1:
    task_input = st.text_input(
        "Enter a multi-step task for the agent:",
        value="Audit user Alice rec_101 and delete her record from the system"
    )

    c1, c2, c3 = st.columns(3)
    preset_safe = c1.button("Preset: Safe Notification (with retry)")
    preset_destructive = c2.button("Preset: Destructive Deletion (HITL)")
    run_btn = c3.button("🚀 Run Agent", type="primary")

    if preset_safe:
        task_input = "Fetch user rec_101 and send an alert notification (with retry)"
        run_btn = True
    elif preset_destructive:
        task_input = "Audit user Alice rec_101 and delete her record from the system"
        run_btn = True

    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    if run_btn:
        st.session_state.thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        init_state = {
            "task_id": st.session_state.thread_id[:8],
            "task": task_input,
            "plan": [],
            "step_index": 0,
            "status": "planning",
            "requires_approval": False,
            "human_approved": False,
            "pending_step": None,
            "results": [],
            "error": None
        }
        st.session_state.agent_state = st.session_state.agent.invoke(init_state, config=config)

    state = st.session_state.agent_state

    if state:
        st.subheader("📋 Execution Plan")
        for idx, step in enumerate(state.get("plan", [])):
            st.markdown(f"**Step {idx+1}:** `{step['tool']}` with args `{step['args']}`")

        # Guardrail interception & Human-in-the-loop dialog
        if state.get("status") == "awaiting_approval":
            pending = state.get("pending_step", {})
            st.warning(f"⚠️ **GUARDRAIL INTERCEPTED:** Destructive tool `{pending.get('tool')}` detected! Human confirmation required.")

            b_approve, b_reject = st.columns(2)
            if b_approve.button("✅ Approve Destructive Action"):
                st.session_state.agent.update_state(config, {"human_approved": True, "status": "executing"})
                st.session_state.agent_state = st.session_state.agent.invoke(None, config=config)
                st.rerun()

            if b_reject.button("❌ Reject Action"):
                st.session_state.agent.update_state(config, {"status": "rejected"})
                st.session_state.agent_state["status"] = "rejected"
                st.error("Action rejected by operator. Execution halted.")
                st.rerun()

        st.subheader("📊 Step Results")
        for res in state.get("results", []):
            st.success(f"**Step {res['step']} [{res['tool']}]:** {res['result']} *(attempts: {res['attempts']})*")

        st.info(f"**Final Agent Status:** `{state.get('status')}`")

with col2:
    st.subheader("📜 Database Audit Trail")
    if st.button("🔄 Refresh Audit Logs"):
        st.rerun()
    logs = get_logs()
    for log in logs[:8]:
        with st.container(border=True):
            st.caption(f"🕒 {log['timestamp'][:19]} | Task: {log['task_id']}")
            st.markdown(f"**{log['step']}** -> `{log['action']}` ({log['status']})")
