"""
main.py - Interactive CLI runner demonstrating tool calling, guardrails, and HITL.
"""

import uuid
from agent import create_agent
from database import get_logs

def run_task(agent, task_description: str, auto_approve: bool = False):
    print("\n" + "=" * 60)
    print(f"[TASK] {task_description}")
    print("=" * 60)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "task_id": thread_id[:8],
        "task": task_description,
        "plan": [],
        "step_index": 0,
        "status": "planning",
        "requires_approval": False,
        "human_approved": False,
        "pending_step": None,
        "results": [],
        "error": None
    }

    # Initial execution up to completion or human confirmation pause
    state = agent.invoke(initial_state, config=config)

    print(f"-> Generated Plan ({len(state['plan'])} steps):")
    for i, step in enumerate(state["plan"]):
        print(f"   {i+1}. {step['tool']}({step['args']})")

    # Handle Human-in-the-Loop if guardrail pauses the execution
    if state.get("status") == "awaiting_approval":
        pending = state.get("pending_step", {})
        print("\n [!] GUARDRAIL TRIGGERED: DESTRUCTIVE ACTION DETECTED!")
        print(f"     Tool: {pending.get('tool')}")
        print(f"     Arguments: {pending.get('args')}")

        if auto_approve:
            user_choice = "y"
            print("     [Auto-Confirm Mode] Approving action...")
        else:
            user_choice = input("     Approve execution? (y/N): ").strip().lower()

        if user_choice == "y":
            print("     -> Action approved by human operator. Resuming agent...")
            agent.update_state(config, {"human_approved": True, "status": "executing"})
            state = agent.invoke(None, config=config)
        else:
            print("     -> Action rejected by human operator. Aborting execution.")
            agent.update_state(config, {"status": "rejected"})

    print("\n-> Final Results:")
    for res in state.get("results", []):
        print(f"   Step {res['step']} [{res['tool']}]: {res['result']} (attempts: {res['attempts']})")

    print(f"-> Final Agent Status: {state.get('status')}")
    return thread_id[:8]

def main():
    agent = create_agent()

    print("TOOL-CALLING AGENT WITH GUARDRAILS (AGENTIC AI)")
    print("--------------------------------------------------")

    # Scenario 1: Safe task with transient tool failure & automatic retry
    task_1 = "Fetch Alice's user profile and send an alert notification (with retry)"
    tid1 = run_task(agent, task_1)

    # Scenario 2: Destructive task requiring human-in-the-loop approval
    task_2 = "Audit user Alice rec_101 and delete her record from the system"
    tid2 = run_task(agent, task_2, auto_approve=True)

    # Display audit trail from Database
    print("\n" + "=" * 60)
    print("[AUDIT LOGS] Persistent Audit Trail from Database:")
    print("=" * 60)
    logs = get_logs()
    for log in logs[:10]:
        print(f"[{log['timestamp'][:19]}] Task:{log['task_id']} | Step:{log['step']} | Action:{log['action']} | Status:{log['status']}")

if __name__ == "__main__":
    main()
