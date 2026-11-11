# Technical Interview Guide: Tool-Calling Agent with Guardrails

This guide prepares you for deep-dive technical questions about this project during interviews.

---

### Q1: Why did you choose a Planner-Executor architecture in LangGraph rather than a standard ReAct loop?
**Answer:**
- **Predictability & Latency:** In a standard ReAct loop (Reason-Act-Observe), an LLM decides actions turn-by-turn, which can lead to rambling, unpredictable tool sequences, or infinite loops on complex tasks.
- **Decomposition:** A Planner-Executor separates high-level planning from tool execution. The planner produces an explicit DAG or sequential step list upfront.
- **Guardrail Visibility:** Having a concrete plan before tool invocation allows the safety guardrail node to inspect the upcoming step and pause *before* initiating irreversible side effects.

---

### Q2: How does the Human-in-the-Loop (HITL) approval work in LangGraph without losing state?
**Answer:**
- **State Checkpointing:** We use LangGraph's checkpointer (`MemorySaver` or PostgreSQL checkpointer) parameterized by a unique `thread_id`.
- **Conditional Interruption:** When the `guardrail` node detects a destructive tool (e.g. `delete_record`, `purge_data`), it transitions state to `status = "awaiting_approval"` and routes to `END`.
- **State Resumption:** When the human confirms (via CLI or UI button), the application calls `agent.update_state(config, {"human_approved": True, "status": "executing"})` and invokes the graph with `None`, resuming exactly where it paused.

---

### Q3: How do you handle tool failures, flakiness, and rate limits?
**Answer:**
- **Exponential Backoff Retries:** For transient errors (e.g. HTTP 503, connection timeouts), the tool wrapper attempts up to `N` retries with backoff.
- **Graceful Fallbacks:** If the primary tool exceeds its retry budget, the agent routes to a secondary fallback mechanism (e.g., local queue or dead-letter logger) rather than crashing the execution graph.
- **Audit Trace:** Every attempt and recovery is persisted to PostgreSQL for post-mortem debugging.

---

### Q4: What failure modes did you identify during evaluation, and how did you resolve them?
**Answer:**
1. **Schema Mismatches / Hallucinated Tool Arguments:** LLMs sometimes passed extra or misnamed parameters. We introduced strict Pydantic tool schemas and explicit system instructions restricting output to valid tool signatures.
2. **Missing State Transitions:** Early iterations risked bypassing guardrail checks when re-planning. We structured conditional edges in LangGraph so every step must flow through the `guardrail` inspection node before reaching the `executor`.
3. **Flaky External APIs:** We built automated retry wrappers with circuit-breaking fallback logic, boosting multi-step benchmark completion to 100%.

---

### Q5: How is PostgreSQL used for auditability?
**Answer:**
- We record every state transition into the `agent_audit_logs` table:
  - `timestamp`: UTC ISO timestamp
  - `task_id`: Correlation ID tying multi-step actions together
  - `step_name`: `PLANNER`, `GUARDRAIL`, or `EXECUTOR`
  - `action`: Specific tool or guardrail rule triggered
  - `details`: JSON payload of arguments, LLM outputs, or error traces
  - `status`: `SUCCESS`, `AWAITING_APPROVAL`, `REJECTED`, or `FAILED`
