"""
SQLite-backed trace database for LLM pipeline observability.

This module provides a local, zero-config tracing database that records
every graph node execution, pipeline event, and LLM call — giving you
LangSmith-like visibility from a single file on your machine.

**What is SQLite?**
SQLite is a lightweight database engine built into Python (``import sqlite3``).
Unlike PostgreSQL or MySQL, there's no server to install or configure — it's
just a single file on disk (``data/traces.db``). You can query it from the
terminal with::

    sqlite3 data/traces.db "SELECT * FROM runs;"

**Schema overview**

``runs``
    One row per pipeline invocation (classify or assess graph).
``events``
    Every ``PipelineEvent`` (stage_started, agent_completed, etc.).
``node_executions``
    Timing and state-summary for each graph node (init, ingest, classify_group…).
``llm_calls``
    Full LLM request/response: prompts, output text, token counts, latency.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema DDL — executed once via CREATE TABLE IF NOT EXISTS
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT    PRIMARY KEY,
    regulation_name TEXT,
    graph_name      TEXT,
    started_at      REAL    NOT NULL,
    completed_at    REAL,
    status          TEXT    NOT NULL DEFAULT 'running',
    config_json     TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL REFERENCES runs(run_id),
    event_type  TEXT    NOT NULL,
    stage       TEXT,
    message     TEXT,
    data_json   TEXT,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS node_executions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id),
    node_name       TEXT    NOT NULL,
    started_at      REAL    NOT NULL,
    completed_at    REAL,
    duration_ms     REAL,
    input_summary   TEXT,
    output_summary  TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT    NOT NULL REFERENCES runs(run_id),
    node_name           TEXT,
    agent_name          TEXT,
    system_prompt       TEXT,
    user_prompt         TEXT,
    response_text       TEXT,
    model               TEXT,
    temperature         REAL,
    max_tokens          INTEGER,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    latency_ms          REAL,
    timestamp           REAL    NOT NULL,
    error               TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_run      ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_nodes_run       ON node_executions(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run   ON llm_calls(run_id);
"""


# ---------------------------------------------------------------------------
# TraceDB — thin wrapper around sqlite3.Connection
# ---------------------------------------------------------------------------

class TraceDB:
    """Local SQLite trace store.

    Usage::

        db = TraceDB("data/traces.db")   # creates file + tables if needed
        db.insert_run(run_id, ...)
        db.insert_event(run_id, ...)
        ...
        db.close()

    The database uses WAL (Write-Ahead Logging) mode so that reads from the
    Streamlit UI never block writes from the running pipeline.
    """

    def __init__(self, db_path: str | Path = "data/traces.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row          # rows behave like dicts
        self._conn.execute("PRAGMA journal_mode=WAL")  # safe concurrent reads
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    # ---- schema ----

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA)

    # ---- inserts ----

    def insert_run(
        self,
        run_id: str,
        regulation_name: str = "",
        graph_name: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO runs (run_id, regulation_name, graph_name, started_at, config_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, regulation_name, graph_name, time.time(), json.dumps(config or {})),
        )
        self._conn.commit()

    def update_run_status(
        self,
        run_id: str,
        status: str,
        regulation_name: str | None = None,
    ) -> None:
        if regulation_name is not None:
            self._conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, regulation_name = ? WHERE run_id = ?",
                (status, time.time(), regulation_name, run_id),
            )
        else:
            self._conn.execute(
                "UPDATE runs SET status = ?, completed_at = ? WHERE run_id = ?",
                (status, time.time(), run_id),
            )
        self._conn.commit()

    def insert_event(
        self,
        run_id: str,
        event_type: str,
        stage: str = "",
        message: str = "",
        data: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO events (run_id, event_type, stage, message, data_json, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, event_type, stage, message, json.dumps(data or {}), timestamp or time.time()),
        )
        self._conn.commit()

    def insert_node_execution(
        self,
        run_id: str,
        node_name: str,
        started_at: float,
        completed_at: float | None = None,
        duration_ms: float | None = None,
        input_summary: str = "",
        output_summary: str = "",
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO node_executions "
            "(run_id, node_name, started_at, completed_at, duration_ms, input_summary, output_summary, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, node_name, started_at, completed_at, duration_ms, input_summary, output_summary, error),
        )
        self._conn.commit()

    def insert_llm_call(
        self,
        run_id: str,
        *,
        node_name: str = "",
        agent_name: str = "",
        system_prompt: str = "",
        user_prompt: str = "",
        response_text: str = "",
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO llm_calls "
            "(run_id, node_name, agent_name, system_prompt, user_prompt, response_text, "
            " model, temperature, max_tokens, prompt_tokens, completion_tokens, total_tokens, "
            " latency_ms, timestamp, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, node_name, agent_name, system_prompt, user_prompt, response_text,
                model, temperature, max_tokens, prompt_tokens, completion_tokens, total_tokens,
                latency_ms, time.time(), error,
            ),
        )
        self._conn.commit()

    # ---- queries ----

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent runs, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY timestamp", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run_nodes(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM node_executions WHERE run_id = ? ORDER BY started_at", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run_llm_calls(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM llm_calls WHERE run_id = ? ORDER BY timestamp", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run_summary(self, run_id: str) -> dict[str, Any]:
        """Aggregate statistics for a single run."""
        run = self.get_run(run_id)
        if not run:
            return {}

        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM events WHERE run_id = ?", (run_id,)
        ).fetchone()
        event_count = row["cnt"] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt, "
            "       SUM(duration_ms) AS total_ms "
            "FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()
        node_count = row["cnt"] if row else 0
        total_node_ms = row["total_ms"] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt, "
            "       SUM(prompt_tokens) AS p_tok, "
            "       SUM(completion_tokens) AS c_tok, "
            "       SUM(total_tokens) AS t_tok, "
            "       SUM(latency_ms) AS llm_ms "
            "FROM llm_calls WHERE run_id = ?", (run_id,)
        ).fetchone()
        llm_count = row["cnt"] if row else 0
        prompt_tokens = row["p_tok"] or 0 if row else 0
        completion_tokens = row["c_tok"] or 0 if row else 0
        total_tokens = row["t_tok"] or 0 if row else 0
        total_llm_ms = row["llm_ms"] or 0 if row else 0

        return {
            **run,
            "event_count": event_count,
            "node_count": node_count,
            "total_node_ms": total_node_ms or 0,
            "llm_call_count": llm_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "total_llm_ms": total_llm_ms,
        }

    def delete_run(self, run_id: str) -> None:
        """Delete a run and all its associated data."""
        self._conn.execute("DELETE FROM llm_calls WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM node_executions WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        self._conn.commit()

    def purge_old_runs(self, keep_latest: int = 20) -> int:
        """Delete all but the N most recent runs. Returns count deleted."""
        runs = self.list_runs(limit=99999)
        if len(runs) <= keep_latest:
            return 0
        to_delete = runs[keep_latest:]
        for r in to_delete:
            self.delete_run(r["run_id"])
        return len(to_delete)

    # ---- lifecycle ----

    def close(self) -> None:
        self._conn.close()
