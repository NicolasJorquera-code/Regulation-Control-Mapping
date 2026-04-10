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
import uuid
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
# New table DDL — run_metrics + run_comparisons
# ---------------------------------------------------------------------------

_RUN_METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id            TEXT PRIMARY KEY,
    regulation_name   TEXT,
    model             TEXT,
    provider          TEXT,
    scope_description TEXT,

    total_tokens          INTEGER DEFAULT 0,
    total_prompt_tokens   INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    estimated_cost_usd    REAL DEFAULT 0.0,
    total_latency_ms      REAL DEFAULT 0.0,
    avg_latency_per_call_ms REAL DEFAULT 0.0,
    total_llm_calls       INTEGER DEFAULT 0,

    classify_total        INTEGER DEFAULT 0,
    classify_passed       INTEGER DEFAULT 0,
    classify_pass_rate    REAL DEFAULT 0.0,
    classify_retries      INTEGER DEFAULT 0,
    classify_category_distribution TEXT,

    map_total             INTEGER DEFAULT 0,
    map_passed            INTEGER DEFAULT 0,
    map_pass_rate         REAL DEFAULT 0.0,
    map_avg_confidence    REAL DEFAULT 0.0,
    map_retries           INTEGER DEFAULT 0,

    assess_total          INTEGER DEFAULT 0,
    assess_passed         INTEGER DEFAULT 0,
    assess_pass_rate      REAL DEFAULT 0.0,
    coverage_covered_count   INTEGER DEFAULT 0,
    coverage_partial_count   INTEGER DEFAULT 0,
    coverage_gap_count       INTEGER DEFAULT 0,
    coverage_covered_pct     REAL DEFAULT 0.0,
    coverage_partial_pct     REAL DEFAULT 0.0,
    coverage_gap_pct         REAL DEFAULT 0.0,

    risk_total            INTEGER DEFAULT 0,
    risk_passed           INTEGER DEFAULT 0,
    risk_pass_rate        REAL DEFAULT 0.0,
    risk_avg_impact       REAL DEFAULT 0.0,
    risk_avg_frequency    REAL DEFAULT 0.0,
    risk_distribution     TEXT,

    overall_pass_rate     REAL DEFAULT 0.0,
    overall_retry_rate    REAL DEFAULT 0.0,
    quality_score         REAL DEFAULT 0.0,

    computed_at           REAL
);
"""

_RUN_COMPARISONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_comparisons (
    comparison_id     TEXT PRIMARY KEY,
    run_id_a          TEXT NOT NULL,
    run_id_b          TEXT NOT NULL,

    model_a           TEXT,
    model_b           TEXT,
    regulation_a      TEXT,
    regulation_b      TEXT,

    token_delta       INTEGER,
    cost_delta_usd    REAL,
    latency_delta_ms  REAL,

    quality_delta     REAL,
    pass_rate_delta   REAL,

    classify_agreement_rate REAL,
    map_overlap_rate       REAL,
    coverage_agreement_rate REAL,

    notes             TEXT,
    computed_at        REAL,

    FOREIGN KEY (run_id_a) REFERENCES runs(run_id),
    FOREIGN KEY (run_id_b) REFERENCES runs(run_id)
);
"""

# Columns added to llm_calls via ALTER TABLE migration
_LLM_CALLS_NEW_COLUMNS: list[tuple[str, str]] = [
    ("validation_passed", "BOOLEAN"),
    ("validation_failures", "TEXT"),
    ("retry_attempt", "INTEGER DEFAULT 0"),
    ("output_type", "TEXT"),
    ("parsed_output", "TEXT"),
]

# Approximate cost per 1K tokens by model
COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
    "ica_default": {"prompt": 0.003, "completion": 0.015},
}


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
        """Create core tables and run migrations for new columns/tables."""
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(_RUN_METRICS_SCHEMA)
        self._conn.executescript(_RUN_COMPARISONS_SCHEMA)
        self._migrate_llm_calls()

    def _migrate_llm_calls(self) -> None:
        """Add new columns to llm_calls if they don't exist yet.

        SQLite has no ``ALTER TABLE ADD COLUMN IF NOT EXISTS``, so we
        check ``PRAGMA table_info`` and add only missing columns.
        """
        rows = self._conn.execute("PRAGMA table_info(llm_calls)").fetchall()
        existing = {row["name"] for row in rows}
        for col_name, col_type in _LLM_CALLS_NEW_COLUMNS:
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE llm_calls ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

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

    def update_llm_call_quality(
        self,
        run_id: str,
        node_name: str,
        agent_name: str,
        timestamp: float,
        validation_passed: bool,
        validation_failures: list[str],
        retry_attempt: int,
        output_type: str,
        parsed_output: dict | None,
    ) -> None:
        """Update an existing ``llm_calls`` row with quality metrics.

        Matches the row by ``(run_id, node_name)`` and the closest
        timestamp within a 60-second window.  The LLM call is inserted by
        ``TracingTransportClient``; quality data arrives later from the
        graph node after validation.

        Args:
            run_id: Pipeline run identifier.
            node_name: Graph node that triggered the call.
            agent_name: Agent class name.
            timestamp: Approximate time of the call (``time.time()``).
            validation_passed: Whether the agent output passed validation.
            validation_failures: List of failure code strings.
            retry_attempt: 0 for first attempt, incremented on retries.
            output_type: One of ``'classify'``, ``'map'``, ``'assess'``, ``'risk'``.
            parsed_output: The structured dict returned by the agent (stored as JSON).
        """
        window_start = timestamp - 60.0
        self._conn.execute(
            """UPDATE llm_calls
               SET validation_passed = ?,
                   validation_failures = ?,
                   retry_attempt = ?,
                   output_type = ?,
                   parsed_output = ?
               WHERE id = (
                   SELECT id FROM llm_calls
                   WHERE run_id = ? AND node_name = ? AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT 1
               )""",
            (
                validation_passed,
                json.dumps(validation_failures),
                retry_attempt,
                output_type,
                json.dumps(parsed_output) if parsed_output is not None else None,
                run_id,
                node_name,
                window_start,
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

    # ---- run metrics computation ----

    @staticmethod
    def _normalize(x: float, lo: float, hi: float) -> float:
        """Clamp *x* to [lo, hi] and map linearly to [0.0, 1.0]."""
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (x - lo) / (hi - lo)))

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD for a given token count and model."""
        pricing = COST_PER_1K_TOKENS.get(model, COST_PER_1K_TOKENS["ica_default"])
        return (
            (prompt_tokens / 1000) * pricing["prompt"]
            + (completion_tokens / 1000) * pricing["completion"]
        )

    def compute_run_metrics(self, run_id: str) -> dict[str, Any]:
        """Aggregate quality and cost metrics for a pipeline run.

        Queries ``llm_calls`` for *run_id*, computes per-phase and overall
        aggregates, and inserts/replaces the result in ``run_metrics``.

        Args:
            run_id: The pipeline run to summarise.

        Returns:
            The computed metrics dict (all column values).
        """
        run = self.get_run(run_id)
        if not run:
            return {}

        # Fetch all LLM calls for this run
        calls = self._conn.execute(
            "SELECT * FROM llm_calls WHERE run_id = ?", (run_id,)
        ).fetchall()
        calls = [dict(c) for c in calls]

        # --- Global aggregates ---
        total_prompt = sum(c.get("prompt_tokens") or 0 for c in calls)
        total_completion = sum(c.get("completion_tokens") or 0 for c in calls)
        total_tokens = sum(c.get("total_tokens") or 0 for c in calls)
        total_latency = sum(c.get("latency_ms") or 0 for c in calls)
        total_llm_calls = len(calls)
        avg_latency = total_latency / total_llm_calls if total_llm_calls else 0.0

        model = run.get("config_json", "")
        try:
            model = json.loads(model).get("model", "")
        except (json.JSONDecodeError, AttributeError):
            model = ""
        # Fallback: pick model from first call
        if not model and calls:
            model = calls[0].get("model", "")

        provider = ""
        if "ica" in model.lower():
            provider = "ica"
        elif "gpt" in model.lower():
            provider = "openai"
        elif "claude" in model.lower():
            provider = "anthropic"
        else:
            provider = "unknown"

        cost = self._estimate_cost(model, total_prompt, total_completion)

        # --- Per-phase aggregates ---
        by_type: dict[str, list[dict]] = {"classify": [], "map": [], "assess": [], "risk": []}
        for c in calls:
            ot = c.get("output_type") or ""
            if ot in by_type:
                by_type[ot].append(c)

        def _phase_stats(rows: list[dict]) -> dict:
            total = len(rows)
            passed = sum(1 for r in rows if r.get("validation_passed"))
            retries = sum(1 for r in rows if (r.get("retry_attempt") or 0) > 0)
            pass_rate = passed / total if total else 0.0
            return {"total": total, "passed": passed, "retries": retries, "pass_rate": pass_rate}

        cl = _phase_stats(by_type["classify"])
        mp = _phase_stats(by_type["map"])
        ass = _phase_stats(by_type["assess"])
        rsk = _phase_stats(by_type["risk"])

        # Classification category distribution
        cat_dist: dict[str, int] = {}
        for c in by_type["classify"]:
            raw = c.get("parsed_output")
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                items = parsed if isinstance(parsed, list) else parsed.get("classifications", [parsed])
                for item in items:
                    cat = item.get("obligation_category", "Unknown")
                    cat_dist[cat] = cat_dist.get(cat, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        # Mapping avg confidence
        conf_values: list[float] = []
        for c in by_type["map"]:
            raw = c.get("parsed_output")
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                items = parsed if isinstance(parsed, list) else parsed.get("mappings", [parsed])
                for item in items:
                    conf = item.get("confidence")
                    if conf is not None:
                        conf_values.append(float(conf))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        map_avg_confidence = sum(conf_values) / len(conf_values) if conf_values else 0.0

        # Coverage distribution
        covered_count = partial_count = gap_count = 0
        for c in by_type["assess"]:
            raw = c.get("parsed_output")
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                status = parsed.get("overall_coverage", "")
                if status == "Covered":
                    covered_count += 1
                elif status == "Partially Covered":
                    partial_count += 1
                elif status == "Not Covered":
                    gap_count += 1
            except (json.JSONDecodeError, TypeError):
                pass
        cov_total = covered_count + partial_count + gap_count
        covered_pct = covered_count / cov_total if cov_total else 0.0
        partial_pct = partial_count / cov_total if cov_total else 0.0
        gap_pct = gap_count / cov_total if cov_total else 0.0

        # Risk distribution
        risk_dist: dict[str, int] = {}
        impact_vals: list[float] = []
        freq_vals: list[float] = []
        for c in by_type["risk"]:
            raw = c.get("parsed_output")
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                items = parsed if isinstance(parsed, list) else parsed.get("risks", [parsed])
                for item in items:
                    rating = item.get("inherent_risk_rating", "Unknown")
                    risk_dist[rating] = risk_dist.get(rating, 0) + 1
                    imp = item.get("impact_rating")
                    freq = item.get("frequency_rating")
                    if imp is not None:
                        impact_vals.append(float(imp))
                    if freq is not None:
                        freq_vals.append(float(freq))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        risk_avg_impact = sum(impact_vals) / len(impact_vals) if impact_vals else 0.0
        risk_avg_freq = sum(freq_vals) / len(freq_vals) if freq_vals else 0.0

        # --- Overall quality ---
        all_with_type = [c for c in calls if c.get("output_type")]
        overall_total = len(all_with_type)
        overall_passed = sum(1 for c in all_with_type if c.get("validation_passed"))
        overall_retried = sum(1 for c in all_with_type if (c.get("retry_attempt") or 0) > 0)
        overall_pass_rate = overall_passed / overall_total if overall_total else 0.0
        overall_retry_rate = overall_retried / overall_total if overall_total else 0.0

        quality_score = (
            0.30 * overall_pass_rate
            + 0.25 * (1.0 - overall_retry_rate)
            + 0.20 * map_avg_confidence
            + 0.15 * covered_pct
            + 0.10 * (1.0 - self._normalize(avg_latency, 0, 60000))
        )

        metrics = {
            "run_id": run_id,
            "regulation_name": run.get("regulation_name", ""),
            "model": model,
            "provider": provider,
            "scope_description": "",
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "estimated_cost_usd": round(cost, 6),
            "total_latency_ms": round(total_latency, 2),
            "avg_latency_per_call_ms": round(avg_latency, 2),
            "total_llm_calls": total_llm_calls,
            "classify_total": cl["total"],
            "classify_passed": cl["passed"],
            "classify_pass_rate": round(cl["pass_rate"], 4),
            "classify_retries": cl["retries"],
            "classify_category_distribution": json.dumps(cat_dist),
            "map_total": mp["total"],
            "map_passed": mp["passed"],
            "map_pass_rate": round(mp["pass_rate"], 4),
            "map_avg_confidence": round(map_avg_confidence, 4),
            "map_retries": mp["retries"],
            "assess_total": ass["total"],
            "assess_passed": ass["passed"],
            "assess_pass_rate": round(ass["pass_rate"], 4),
            "coverage_covered_count": covered_count,
            "coverage_partial_count": partial_count,
            "coverage_gap_count": gap_count,
            "coverage_covered_pct": round(covered_pct, 4),
            "coverage_partial_pct": round(partial_pct, 4),
            "coverage_gap_pct": round(gap_pct, 4),
            "risk_total": rsk["total"],
            "risk_passed": rsk["passed"],
            "risk_pass_rate": round(rsk["pass_rate"], 4),
            "risk_avg_impact": round(risk_avg_impact, 4),
            "risk_avg_frequency": round(risk_avg_freq, 4),
            "risk_distribution": json.dumps(risk_dist),
            "overall_pass_rate": round(overall_pass_rate, 4),
            "overall_retry_rate": round(overall_retry_rate, 4),
            "quality_score": round(quality_score, 4),
            "computed_at": time.time(),
        }

        cols = ", ".join(metrics.keys())
        placeholders = ", ".join("?" for _ in metrics)
        self._conn.execute(
            f"INSERT OR REPLACE INTO run_metrics ({cols}) VALUES ({placeholders})",
            tuple(metrics.values()),
        )
        self._conn.commit()
        return metrics

    def recompute_all_metrics(self) -> int:
        """Recompute ``run_metrics`` for every run. Returns count recomputed."""
        runs = self.list_runs(limit=99999)
        count = 0
        for r in runs:
            self.compute_run_metrics(r["run_id"])
            count += 1
        return count

    # ---- run comparisons ----

    def compare_runs(
        self,
        run_id_a: str,
        run_id_b: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """Compare two pipeline runs and store the result.

        Loads (or computes) ``run_metrics`` for both runs, calculates deltas,
        and computes agreement metrics when both runs process the same
        regulation.

        Args:
            run_id_a: First run identifier.
            run_id_b: Second run identifier.
            notes: Optional free-text annotation.

        Returns:
            The comparison dict (all column values).
        """
        ma = self.get_run_metrics(run_id_a)
        if not ma:
            ma = self.compute_run_metrics(run_id_a)
        mb = self.get_run_metrics(run_id_b)
        if not mb:
            mb = self.compute_run_metrics(run_id_b)
        if not ma or not mb:
            return {}

        same_reg = (ma.get("regulation_name") or "") == (mb.get("regulation_name") or "") and ma.get("regulation_name")

        # Agreement metrics (only meaningful for same regulation)
        classify_agree = None
        map_overlap = None
        coverage_agree = None
        if same_reg:
            classify_agree = self._classification_agreement(run_id_a, run_id_b)
            map_overlap = self._mapping_overlap(run_id_a, run_id_b)
            coverage_agree = self._coverage_agreement(run_id_a, run_id_b)

        comparison = {
            "comparison_id": uuid.uuid4().hex[:16],
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "model_a": ma.get("model", ""),
            "model_b": mb.get("model", ""),
            "regulation_a": ma.get("regulation_name", ""),
            "regulation_b": mb.get("regulation_name", ""),
            "token_delta": (mb.get("total_tokens") or 0) - (ma.get("total_tokens") or 0),
            "cost_delta_usd": round((mb.get("estimated_cost_usd") or 0) - (ma.get("estimated_cost_usd") or 0), 6),
            "latency_delta_ms": round((mb.get("total_latency_ms") or 0) - (ma.get("total_latency_ms") or 0), 2),
            "quality_delta": round((mb.get("quality_score") or 0) - (ma.get("quality_score") or 0), 4),
            "pass_rate_delta": round((mb.get("overall_pass_rate") or 0) - (ma.get("overall_pass_rate") or 0), 4),
            "classify_agreement_rate": round(classify_agree, 4) if classify_agree is not None else None,
            "map_overlap_rate": round(map_overlap, 4) if map_overlap is not None else None,
            "coverage_agreement_rate": round(coverage_agree, 4) if coverage_agree is not None else None,
            "notes": notes,
            "computed_at": time.time(),
        }

        cols = ", ".join(comparison.keys())
        placeholders = ", ".join("?" for _ in comparison)
        self._conn.execute(
            f"INSERT OR REPLACE INTO run_comparisons ({cols}) VALUES ({placeholders})",
            tuple(comparison.values()),
        )
        self._conn.commit()
        return comparison

    def _extract_parsed_by_citation(self, run_id: str, output_type: str) -> dict[str, list[dict]]:
        """Extract parsed_output dicts keyed by citation for a run/output_type."""
        rows = self._conn.execute(
            "SELECT parsed_output FROM llm_calls WHERE run_id = ? AND output_type = ?",
            (run_id, output_type),
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for row in rows:
            raw = row["parsed_output"]
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                items = parsed if isinstance(parsed, list) else [parsed]
                # Agent outputs may nest items under a key
                if len(items) == 1 and isinstance(items[0], dict):
                    inner = items[0]
                    for key in ("classifications", "mappings", "risks"):
                        if key in inner and isinstance(inner[key], list):
                            items = inner[key]
                            break
                for item in items:
                    cit = item.get("citation", item.get("source_citation", ""))
                    if cit:
                        result.setdefault(cit, []).append(item)
            except (json.JSONDecodeError, TypeError):
                pass
        return result

    def _classification_agreement(self, run_a: str, run_b: str) -> float:
        """Return fraction of obligations classified identically."""
        a = self._extract_parsed_by_citation(run_a, "classify")
        b = self._extract_parsed_by_citation(run_b, "classify")
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        agree = 0
        for cit in common:
            cats_a = {item.get("obligation_category") for item in a[cit]}
            cats_b = {item.get("obligation_category") for item in b[cit]}
            if cats_a == cats_b:
                agree += 1
        return agree / len(common)

    def _mapping_overlap(self, run_a: str, run_b: str) -> float:
        """Return average Jaccard similarity of APQC mappings per citation."""
        a = self._extract_parsed_by_citation(run_a, "map")
        b = self._extract_parsed_by_citation(run_b, "map")
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        total_jaccard = 0.0
        for cit in common:
            ids_a = {item.get("apqc_hierarchy_id") for item in a[cit]}
            ids_b = {item.get("apqc_hierarchy_id") for item in b[cit]}
            union = ids_a | ids_b
            if union:
                total_jaccard += len(ids_a & ids_b) / len(union)
        return total_jaccard / len(common)

    def _coverage_agreement(self, run_a: str, run_b: str) -> float:
        """Return fraction of assessments with same coverage status."""
        a = self._extract_parsed_by_citation(run_a, "assess")
        b = self._extract_parsed_by_citation(run_b, "assess")
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        agree = 0
        for cit in common:
            status_a = {item.get("overall_coverage") for item in a[cit]}
            status_b = {item.get("overall_coverage") for item in b[cit]}
            if status_a == status_b:
                agree += 1
        return agree / len(common)

    # ---- read methods for UI ----

    def list_run_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return ``run_metrics`` rows ordered by ``computed_at DESC``.

        Args:
            limit: Maximum rows to return.
        """
        rows = self._conn.execute(
            "SELECT * FROM run_metrics ORDER BY computed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run_metrics(self, run_id: str) -> dict[str, Any] | None:
        """Return a single ``run_metrics`` row, or *None* if not found."""
        row = self._conn.execute(
            "SELECT * FROM run_metrics WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_comparisons(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return ``run_comparisons`` rows ordered by ``computed_at DESC``.

        Args:
            limit: Maximum rows to return.
        """
        rows = self._conn.execute(
            "SELECT * FROM run_comparisons ORDER BY computed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_comparison(self, comparison_id: str) -> dict[str, Any] | None:
        """Return a single ``run_comparisons`` row, or *None* if not found."""
        row = self._conn.execute(
            "SELECT * FROM run_comparisons WHERE comparison_id = ?", (comparison_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_phase_breakdown(self, run_id: str) -> dict[str, Any]:
        """Return per-phase metrics with individual call details.

        Args:
            run_id: Pipeline run identifier.

        Returns:
            Dict with keys ``classify``, ``map``, ``assess``, ``risk``, each
            containing ``{"total", "passed", "retries", "calls": [...]}``.
        """
        calls = self._conn.execute(
            "SELECT id, node_name, agent_name, model, prompt_tokens, completion_tokens, "
            "       total_tokens, latency_ms, timestamp, validation_passed, "
            "       validation_failures, retry_attempt, output_type "
            "FROM llm_calls WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for ot in ("classify", "map", "assess", "risk"):
            phase_calls = [dict(c) for c in calls if c["output_type"] == ot]
            passed = sum(1 for c in phase_calls if c.get("validation_passed"))
            retries = sum(1 for c in phase_calls if (c.get("retry_attempt") or 0) > 0)
            result[ot] = {
                "total": len(phase_calls),
                "passed": passed,
                "retries": retries,
                "calls": phase_calls,
            }
        return result

    def get_cost_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent runs' cost and quality for scatter plots.

        Args:
            limit: Maximum runs to return.

        Returns:
            List of dicts with keys ``run_id``, ``model``, ``total_tokens``,
            ``estimated_cost_usd``, ``quality_score``.
        """
        rows = self._conn.execute(
            "SELECT run_id, model, total_tokens, estimated_cost_usd, quality_score "
            "FROM run_metrics ORDER BY computed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- lifecycle ----

    def close(self) -> None:
        self._conn.close()
