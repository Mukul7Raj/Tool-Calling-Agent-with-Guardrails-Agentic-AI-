"""
database.py - Lightweight audit logging with PostgreSQL & SQLite fallback.
Logs every agent step, tool execution, and guardrail decision.
"""

import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Returns a PostgreSQL connection if DATABASE_URL is set, else SQLite."""
    if DB_URL:
        try:
            import psycopg2
            return psycopg2.connect(DB_URL)
        except Exception as e:
            print(f"[DB] PostgreSQL unavailable ({e}), using local SQLite fallback.")
    return sqlite3.connect("agent_audit.db")

def init_db():
    """Initializes the audit log table."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            task_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            status TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def log_step(task_id: str, step_name: str, action: str, details: Any, status: str = "SUCCESS"):
    """Logs a single agent event to the database."""
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    payload = json.dumps(details) if isinstance(details, (dict, list)) else str(details)
    now = datetime.utcnow().isoformat()
    cur.execute("""
        INSERT INTO agent_audit_logs (timestamp, task_id, step_name, action, details, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now, task_id, step_name, action, payload, status))
    conn.commit()
    conn.close()

def get_logs(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves audit logs for auditing and debugging."""
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    if task_id:
        cur.execute("SELECT timestamp, task_id, step_name, action, details, status FROM agent_audit_logs WHERE task_id = ? ORDER BY id ASC", (task_id,))
    else:
        cur.execute("SELECT timestamp, task_id, step_name, action, details, status FROM agent_audit_logs ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    return [{"timestamp": r[0], "task_id": r[1], "step": r[2], "action": r[3], "details": r[4], "status": r[5]} for r in rows]

