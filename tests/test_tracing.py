"""Tests for the SQLite tracing subsystem."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from regrisk.tracing.db import TraceDB
from regrisk.tracing.listener import SQLiteTraceListener
from regrisk.tracing.decorators import trace_node, get_current_trace_context, set_current_trace_context, _summarise_state
from regrisk.core.events import EventEmitter, EventType, PipelineEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path: Path) -> TraceDB:
    """Create a fresh TraceDB in a temp directory."""
    return TraceDB(tmp_path / "test_traces.db")


@pytest.fixture()
def run_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# TraceDB tests
# ---------------------------------------------------------------------------

class TestTraceDB:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "traces.db"
        db = TraceDB(db_path)
        assert db_path.exists()
        db.close()

    def test_insert_and_list_runs(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id, regulation_name="Test Reg", graph_name="classify")
        runs = db.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id
        assert runs[0]["regulation_name"] == "Test Reg"
        assert runs[0]["graph_name"] == "classify"
        assert runs[0]["status"] == "running"

    def test_update_run_status(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id, graph_name="classify")
        db.update_run_status(run_id, "completed")
        run = db.get_run(run_id)
        assert run is not None
        assert run["status"] == "completed"
        assert run["completed_at"] is not None

    def test_update_run_status_with_reg_name(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id, graph_name="classify")
        db.update_run_status(run_id, "completed", regulation_name="Updated Reg")
        run = db.get_run(run_id)
        assert run["regulation_name"] == "Updated Reg"

    def test_insert_and_get_events(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_event(run_id, event_type="stage_started", stage="init", message="Starting")
        db.insert_event(run_id, event_type="stage_completed", stage="init", message="Done")
        events = db.get_run_events(run_id)
        assert len(events) == 2
        assert events[0]["event_type"] == "stage_started"
        assert events[1]["event_type"] == "stage_completed"

    def test_insert_and_get_node_executions(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        now = time.time()
        db.insert_node_execution(
            run_id, node_name="classify_group",
            started_at=now, completed_at=now + 1.5,
            duration_ms=1500.0,
            input_summary='{"groups": "list(3)"}',
            output_summary='{"classified": "list(10)"}',
        )
        nodes = db.get_run_nodes(run_id)
        assert len(nodes) == 1
        assert nodes[0]["node_name"] == "classify_group"
        assert nodes[0]["duration_ms"] == 1500.0

    def test_insert_and_get_llm_calls(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_llm_call(
            run_id,
            node_name="classify_group",
            agent_name="ObligationClassifierAgent",
            system_prompt="You are a classifier.",
            user_prompt="Classify these obligations.",
            response_text='{"classifications": []}',
            model="gpt-4o",
            temperature=0.2,
            max_tokens=8000,
            prompt_tokens=500,
            completion_tokens=200,
            total_tokens=700,
            latency_ms=1234.5,
        )
        calls = db.get_run_llm_calls(run_id)
        assert len(calls) == 1
        assert calls[0]["agent_name"] == "ObligationClassifierAgent"
        assert calls[0]["prompt_tokens"] == 500
        assert calls[0]["system_prompt"] == "You are a classifier."

    def test_get_run_summary(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id, graph_name="classify")
        db.insert_event(run_id, event_type="stage_started")
        db.insert_event(run_id, event_type="stage_completed")
        db.insert_node_execution(
            run_id, node_name="init", started_at=time.time(),
            duration_ms=100.0,
        )
        db.insert_llm_call(
            run_id, prompt_tokens=100, completion_tokens=50, total_tokens=150,
            latency_ms=500.0,
        )
        summary = db.get_run_summary(run_id)
        assert summary["event_count"] == 2
        assert summary["node_count"] == 1
        assert summary["llm_call_count"] == 1
        assert summary["total_tokens"] == 150
        assert summary["total_node_ms"] == 100.0

    def test_delete_run(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_event(run_id, event_type="test")
        db.insert_node_execution(run_id, node_name="n", started_at=time.time())
        db.insert_llm_call(run_id)
        db.delete_run(run_id)
        assert db.get_run(run_id) is None
        assert db.get_run_events(run_id) == []
        assert db.get_run_nodes(run_id) == []
        assert db.get_run_llm_calls(run_id) == []

    def test_purge_old_runs(self, db: TraceDB) -> None:
        for i in range(5):
            db.insert_run(f"run-{i}", graph_name="test")
            time.sleep(0.01)  # ensure ordering
        deleted = db.purge_old_runs(keep_latest=2)
        assert deleted == 3
        assert len(db.list_runs()) == 2

    def test_get_nonexistent_run(self, db: TraceDB) -> None:
        assert db.get_run("nonexistent") is None
        assert db.get_run_summary("nonexistent") == {}


# ---------------------------------------------------------------------------
# SQLiteTraceListener tests
# ---------------------------------------------------------------------------

class TestSQLiteTraceListener:
    def test_writes_events(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        listener = SQLiteTraceListener(db, run_id)

        event = PipelineEvent(
            event_type=EventType.STAGE_STARTED,
            stage="init",
            message="Starting init",
        )
        listener(event)

        events = db.get_run_events(run_id)
        assert len(events) == 1
        assert events[0]["event_type"] == "stage_started"
        assert events[0]["message"] == "Starting init"

    def test_updates_status_on_completed(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        listener = SQLiteTraceListener(db, run_id)

        event = PipelineEvent(
            event_type=EventType.PIPELINE_COMPLETED,
            message="Done",
        )
        listener(event)

        run = db.get_run(run_id)
        assert run["status"] == "completed"

    def test_updates_status_on_failed(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        listener = SQLiteTraceListener(db, run_id)

        event = PipelineEvent(
            event_type=EventType.PIPELINE_FAILED,
            message="Boom",
        )
        listener(event)

        run = db.get_run(run_id)
        assert run["status"] == "failed"

    def test_integrates_with_emitter(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        emitter = EventEmitter()
        listener = SQLiteTraceListener(db, run_id)
        emitter.on(listener)

        emitter.stage_started("init", run_id=run_id)
        emitter.progress("Working...")
        emitter.stage_completed("init", run_id=run_id)

        events = db.get_run_events(run_id)
        assert len(events) == 3


# ---------------------------------------------------------------------------
# Decorator tests
# ---------------------------------------------------------------------------

class TestTraceNode:
    def test_records_node_execution(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)

        @trace_node(db, run_id, "test_node")
        def my_node(state):
            return {"output_key": [1, 2, 3]}

        result = my_node({"input_key": "hello", "items": [1, 2]})
        assert result == {"output_key": [1, 2, 3]}

        nodes = db.get_run_nodes(run_id)
        assert len(nodes) == 1
        assert nodes[0]["node_name"] == "test_node"
        assert nodes[0]["duration_ms"] > 0
        assert '"input_key"' in nodes[0]["input_summary"]
        assert '"output_key"' in nodes[0]["output_summary"]
        assert nodes[0]["error"] is None

    def test_records_errors(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)

        @trace_node(db, run_id, "failing_node")
        def bad_node(state):
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            bad_node({"x": 1})

        nodes = db.get_run_nodes(run_id)
        assert len(nodes) == 1
        assert "ValueError" in nodes[0]["error"]

    def test_sets_trace_context(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        captured_ctx = {}

        @trace_node(db, run_id, "ctx_node")
        def ctx_node(state):
            captured_ctx.update(get_current_trace_context())
            return {}

        ctx_node({"a": 1})
        assert captured_ctx["node_name"] == "ctx_node"

        # Context should be cleared after
        after = get_current_trace_context()
        assert after["node_name"] == ""

    def test_context_cleared_on_error(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)

        @trace_node(db, run_id, "err_node")
        def err_node(state):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            err_node({})

        ctx = get_current_trace_context()
        assert ctx["node_name"] == ""


class TestSummariseState:
    def test_basic_types(self) -> None:
        import json
        result = json.loads(_summarise_state({
            "name": "hello",
            "count": 42,
            "items": [1, 2, 3],
            "config": {"a": 1, "b": 2},
            "flag": True,
            "nothing": None,
        }))
        assert result["name"] == "str(5)"
        assert result["count"] == "42"
        assert result["items"] == "list(3)"
        assert result["config"] == "dict(2)"
        assert result["flag"] == "True"
        assert result["nothing"] == "None"


# ---------------------------------------------------------------------------
# Evaluation metrics tests
# ---------------------------------------------------------------------------

class TestMigration:
    """Verify ALTER TABLE migration adds new columns to existing databases."""

    def test_fresh_db_has_new_columns(self, tmp_path: Path) -> None:
        db = TraceDB(tmp_path / "fresh.db")
        cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(llm_calls)").fetchall()}
        for col in ("validation_passed", "validation_failures", "retry_attempt", "output_type", "parsed_output"):
            assert col in cols, f"Missing column {col}"
        db.close()

    def test_migration_on_old_db(self, tmp_path: Path) -> None:
        """Create a DB with the old schema, then open with TraceDB to trigger migration."""
        import sqlite3 as _sqlite3
        old_path = tmp_path / "old.db"
        conn = _sqlite3.connect(str(old_path))
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, regulation_name TEXT, "
            "graph_name TEXT, started_at REAL NOT NULL, completed_at REAL, "
            "status TEXT NOT NULL DEFAULT 'running', config_json TEXT);\n"
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "run_id TEXT NOT NULL, event_type TEXT NOT NULL, stage TEXT, message TEXT, "
            "data_json TEXT, timestamp REAL NOT NULL);\n"
            "CREATE TABLE IF NOT EXISTS node_executions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "run_id TEXT NOT NULL, node_name TEXT NOT NULL, started_at REAL NOT NULL, "
            "completed_at REAL, duration_ms REAL, input_summary TEXT, output_summary TEXT, error TEXT);\n"
            "CREATE TABLE IF NOT EXISTS llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "run_id TEXT NOT NULL, node_name TEXT, agent_name TEXT, system_prompt TEXT, "
            "user_prompt TEXT, response_text TEXT, model TEXT, temperature REAL, "
            "max_tokens INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, "
            "total_tokens INTEGER, latency_ms REAL, timestamp REAL NOT NULL, error TEXT);\n"
        )
        conn.close()

        db = TraceDB(old_path)
        cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(llm_calls)").fetchall()}
        assert "validation_passed" in cols
        assert "parsed_output" in cols
        db.close()

    def test_new_tables_created(self, tmp_path: Path) -> None:
        db = TraceDB(tmp_path / "tables.db")
        tables = {r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "run_metrics" in tables
        assert "run_comparisons" in tables
        db.close()


class TestUpdateLlmCallQuality:
    def test_updates_existing_row(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_llm_call(
            run_id,
            node_name="classify_group",
            agent_name="ObligationClassifierAgent",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=500.0,
        )

        db.update_llm_call_quality(
            run_id=run_id,
            node_name="classify_group",
            agent_name="ObligationClassifierAgent",
            timestamp=time.time(),
            validation_passed=True,
            validation_failures=[],
            retry_attempt=0,
            output_type="classify",
            parsed_output={"classifications": [{"citation": "§252.34", "obligation_category": "Controls"}]},
        )

        calls = db.get_run_llm_calls(run_id)
        assert len(calls) == 1
        assert calls[0]["validation_passed"] == 1  # SQLite stores True as 1
        assert calls[0]["output_type"] == "classify"
        assert calls[0]["retry_attempt"] == 0
        import json
        parsed = json.loads(calls[0]["parsed_output"])
        assert "classifications" in parsed

    def test_updates_with_failures(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_llm_call(run_id, node_name="classify_group")

        db.update_llm_call_quality(
            run_id=run_id,
            node_name="classify_group",
            agent_name="ObligationClassifierAgent",
            timestamp=time.time(),
            validation_passed=False,
            validation_failures=["INVALID_CATEGORY", "MISSING_CITATION"],
            retry_attempt=1,
            output_type="classify",
            parsed_output=None,
        )

        calls = db.get_run_llm_calls(run_id)
        assert calls[0]["validation_passed"] == 0
        import json
        failures = json.loads(calls[0]["validation_failures"])
        assert "INVALID_CATEGORY" in failures
        assert calls[0]["retry_attempt"] == 1

    def test_no_match_is_harmless(self, db: TraceDB, run_id: str) -> None:
        """Updating a nonexistent row should not raise."""
        db.insert_run(run_id)
        db.update_llm_call_quality(
            run_id=run_id,
            node_name="nonexistent",
            agent_name="Agent",
            timestamp=time.time(),
            validation_passed=True,
            validation_failures=[],
            retry_attempt=0,
            output_type="classify",
            parsed_output={},
        )
        # No exception = pass


class TestComputeRunMetrics:
    def _insert_calls(self, db: TraceDB, run_id: str) -> None:
        """Insert a mix of LLM calls with quality data for testing."""
        db.insert_run(run_id, regulation_name="Test Reg", graph_name="assess")
        now = time.time()

        # Classify call (passed)
        db.insert_llm_call(run_id, node_name="classify_group", agent_name="Classifier",
                           model="gpt-4o", prompt_tokens=200, completion_tokens=100,
                           total_tokens=300, latency_ms=1000.0)
        db.update_llm_call_quality(
            run_id=run_id, node_name="classify_group", agent_name="Classifier",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="classify",
            parsed_output={"classifications": [{"citation": "§1", "obligation_category": "Controls"}]},
        )

        # Map call (passed)
        db.insert_llm_call(run_id, node_name="map_group", agent_name="Mapper",
                           model="gpt-4o", prompt_tokens=300, completion_tokens=150,
                           total_tokens=450, latency_ms=1500.0)
        db.update_llm_call_quality(
            run_id=run_id, node_name="map_group", agent_name="Mapper",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="map",
            parsed_output={"mappings": [{"citation": "§1", "apqc_hierarchy_id": "11.1", "confidence": 0.85}]},
        )

        # Assess call (passed)
        db.insert_llm_call(run_id, node_name="assess_coverage", agent_name="Assessor",
                           model="gpt-4o", prompt_tokens=250, completion_tokens=120,
                           total_tokens=370, latency_ms=1200.0)
        db.update_llm_call_quality(
            run_id=run_id, node_name="assess_coverage", agent_name="Assessor",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="assess",
            parsed_output={"citation": "§1", "overall_coverage": "Covered"},
        )

        # Risk call (failed validation)
        db.insert_llm_call(run_id, node_name="extract_and_score", agent_name="RiskScorer",
                           model="gpt-4o", prompt_tokens=400, completion_tokens=200,
                           total_tokens=600, latency_ms=2000.0)
        db.update_llm_call_quality(
            run_id=run_id, node_name="extract_and_score", agent_name="RiskScorer",
            timestamp=now, validation_passed=False,
            validation_failures=["WORD_COUNT (15)"], retry_attempt=0,
            output_type="risk",
            parsed_output={"risks": [{"inherent_risk_rating": "High", "impact_rating": 3, "frequency_rating": 2}]},
        )

    def test_computes_metrics(self, db: TraceDB, run_id: str) -> None:
        self._insert_calls(db, run_id)
        metrics = db.compute_run_metrics(run_id)

        assert metrics["run_id"] == run_id
        assert metrics["total_tokens"] == 300 + 450 + 370 + 600
        assert metrics["total_llm_calls"] == 4
        assert metrics["classify_total"] == 1
        assert metrics["classify_passed"] == 1
        assert metrics["map_total"] == 1
        assert metrics["map_passed"] == 1
        assert 0.84 <= metrics["map_avg_confidence"] <= 0.86
        assert metrics["assess_total"] == 1
        assert metrics["coverage_covered_count"] == 1
        assert metrics["risk_total"] == 1
        assert metrics["risk_passed"] == 0
        assert 0.0 < metrics["quality_score"] <= 1.0
        assert metrics["overall_pass_rate"] == 0.75  # 3 of 4 passed
        assert metrics["estimated_cost_usd"] > 0

    def test_stored_in_run_metrics_table(self, db: TraceDB, run_id: str) -> None:
        self._insert_calls(db, run_id)
        db.compute_run_metrics(run_id)

        row = db.get_run_metrics(run_id)
        assert row is not None
        assert row["run_id"] == run_id
        assert row["total_tokens"] == 1720

    def test_idempotent(self, db: TraceDB, run_id: str) -> None:
        self._insert_calls(db, run_id)
        m1 = db.compute_run_metrics(run_id)
        m2 = db.compute_run_metrics(run_id)
        assert m1["quality_score"] == m2["quality_score"]

    def test_empty_run(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        metrics = db.compute_run_metrics(run_id)
        assert metrics["total_llm_calls"] == 0

    def test_nonexistent_run(self, db: TraceDB) -> None:
        assert db.compute_run_metrics("nonexistent") == {}


class TestCompareRuns:
    def test_basic_comparison(self, db: TraceDB) -> None:
        now = time.time()

        rid_a = "run_a_123"
        db.insert_run(rid_a, regulation_name="Reg YY", graph_name="assess")
        db.insert_llm_call(rid_a, node_name="classify_group", model="gpt-4o",
                           prompt_tokens=200, completion_tokens=100, total_tokens=300,
                           latency_ms=1000.0)
        db.update_llm_call_quality(
            run_id=rid_a, node_name="classify_group", agent_name="Cls",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="classify",
            parsed_output={"classifications": [{"citation": "§1", "obligation_category": "Controls"}]},
        )

        rid_b = "run_b_456"
        db.insert_run(rid_b, regulation_name="Reg YY", graph_name="assess")
        db.insert_llm_call(rid_b, node_name="classify_group", model="gpt-4o",
                           prompt_tokens=250, completion_tokens=120, total_tokens=370,
                           latency_ms=1200.0)
        db.update_llm_call_quality(
            run_id=rid_b, node_name="classify_group", agent_name="Cls",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="classify",
            parsed_output={"classifications": [{"citation": "§1", "obligation_category": "Controls"}]},
        )

        comp = db.compare_runs(rid_a, rid_b)
        assert comp["run_id_a"] == rid_a
        assert comp["run_id_b"] == rid_b
        assert comp["token_delta"] == 370 - 300
        assert comp["classify_agreement_rate"] == 1.0

    def test_different_regulations(self, db: TraceDB) -> None:
        """Agreement metrics should be None when regulations differ."""
        rid_a = "run_diff_a"
        rid_b = "run_diff_b"
        db.insert_run(rid_a, regulation_name="Reg A")
        db.insert_run(rid_b, regulation_name="Reg B")
        db.insert_llm_call(rid_a, node_name="n", prompt_tokens=100,
                           completion_tokens=50, total_tokens=150)
        db.insert_llm_call(rid_b, node_name="n", prompt_tokens=100,
                           completion_tokens=50, total_tokens=150)

        comp = db.compare_runs(rid_a, rid_b)
        assert comp["classify_agreement_rate"] is None
        assert comp["map_overlap_rate"] is None
        assert comp["coverage_agreement_rate"] is None

    def test_comparison_stored(self, db: TraceDB) -> None:
        rid_a = "run_store_a"
        rid_b = "run_store_b"
        db.insert_run(rid_a, regulation_name="R")
        db.insert_run(rid_b, regulation_name="R")

        comp = db.compare_runs(rid_a, rid_b, notes="test note")
        assert comp["notes"] == "test note"

        stored = db.get_comparison(comp["comparison_id"])
        assert stored is not None
        assert stored["comparison_id"] == comp["comparison_id"]

        all_comps = db.list_comparisons()
        assert any(c["comparison_id"] == comp["comparison_id"] for c in all_comps)


class TestQueryMethods:
    def test_list_run_metrics(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id, regulation_name="Test")
        db.insert_llm_call(run_id, prompt_tokens=100, completion_tokens=50,
                           total_tokens=150)
        db.compute_run_metrics(run_id)

        metrics_list = db.list_run_metrics()
        assert len(metrics_list) >= 1
        assert any(m["run_id"] == run_id for m in metrics_list)

    def test_get_phase_breakdown(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        now = time.time()
        db.insert_llm_call(run_id, node_name="classify_group")
        db.update_llm_call_quality(
            run_id=run_id, node_name="classify_group", agent_name="Cls",
            timestamp=now, validation_passed=True, validation_failures=[],
            retry_attempt=0, output_type="classify", parsed_output={},
        )

        breakdown = db.get_phase_breakdown(run_id)
        assert "classify" in breakdown
        assert breakdown["classify"]["total"] == 1
        assert breakdown["classify"]["passed"] == 1

    def test_get_cost_history(self, db: TraceDB, run_id: str) -> None:
        db.insert_run(run_id)
        db.insert_llm_call(run_id, model="gpt-4o", prompt_tokens=100,
                           completion_tokens=50, total_tokens=150)
        db.compute_run_metrics(run_id)

        history = db.get_cost_history()
        assert len(history) >= 1
        assert any(h["run_id"] == run_id for h in history)

    def test_recompute_all_metrics(self, db: TraceDB) -> None:
        for i in range(3):
            rid = f"recompute_{i}"
            db.insert_run(rid)
            db.insert_llm_call(rid, prompt_tokens=100, completion_tokens=50,
                               total_tokens=150)

        count = db.recompute_all_metrics()
        assert count == 3
        assert len(db.list_run_metrics()) == 3
