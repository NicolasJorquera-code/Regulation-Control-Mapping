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
