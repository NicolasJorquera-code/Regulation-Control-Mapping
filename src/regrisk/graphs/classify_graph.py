"""
Graph 1: Classify Graph — Ingest + Classify obligations.

Topology::

    START → init → ingest → classify_group ─┐
                                ↑             │ has_more_classify_groups?
                                └─────────────┘
                                      │ (all classified)
                                      ▼
                                end_classify → END
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from regrisk.agents.base import AgentContext
from regrisk.agents.obligation_classifier import ObligationClassifierAgent
from regrisk.core.config import (
    PipelineConfig,
    default_config_path,
    default_taxonomy_path,
    load_config,
    load_risk_taxonomy,
)
from regrisk.core.events import EventEmitter, EventType, PipelineEvent
from regrisk.core.transport import build_client_from_env
from regrisk.graphs.classify_state import ClassifyState
from regrisk.tracing.decorators import trace_node, set_current_trace_context
from regrisk.tracing.transport_wrapper import TracingTransportClient
from regrisk.ingest.apqc_loader import load_apqc_hierarchy
from regrisk.ingest.control_loader import discover_control_files, load_and_merge_controls
from regrisk.ingest.regulation_parser import group_obligations, parse_regulation_excel
from regrisk.validation.validator import validate_classification


# ---------------------------------------------------------------------------
# Module-level singletons (reused across node invocations)
# ---------------------------------------------------------------------------

_emitter: EventEmitter = EventEmitter()
_llm_client_cache: Any = None
_agent_cache: dict[str, Any] = {}
_event_loop: asyncio.AbstractEventLoop | None = None
_trace_db: Any = None
_trace_run_id: str = ""


def set_emitter(emitter: EventEmitter) -> None:
    global _emitter
    _emitter = emitter


def get_emitter() -> EventEmitter:
    return _emitter


def _emit(event_type: EventType, message: str = "", **data: Any) -> None:
    _emitter.emit(PipelineEvent(event_type=event_type, message=message, data=data))


def _get_loop() -> asyncio.AbstractEventLoop:
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _build_context(max_tokens: int = 8000) -> AgentContext:
    global _llm_client_cache
    if _llm_client_cache is None:
        _llm_client_cache = build_client_from_env()
    model = "gpt-4o"
    if _llm_client_cache:
        model = _llm_client_cache.model
    return AgentContext(client=_llm_client_cache, model=model, max_tokens=max_tokens)


def _get_agent(name: str, context: AgentContext) -> Any:
    if name not in _agent_cache:
        agents = {
            "classifier": ObligationClassifierAgent,
        }
        cls = agents[name]
        _agent_cache[name] = cls(context)
    return _agent_cache[name]


def reset_caches() -> None:
    """Reset all module-level caches (for test isolation)."""
    global _llm_client_cache, _agent_cache, _event_loop, _emitter, _trace_db, _trace_run_id
    _llm_client_cache = None
    _agent_cache = {}
    if _event_loop and not _event_loop.is_closed():
        _event_loop.close()
    _event_loop = None
    _emitter = EventEmitter()
    _trace_db = None
    _trace_run_id = ""


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def init_node(state: ClassifyState) -> dict[str, Any]:
    """Load config, risk taxonomy, detect LLM availability."""
    _emit(EventType.PIPELINE_STARTED, "Classification pipeline started")

    config_path = state.get("config_path") or str(default_config_path())
    config = load_config(config_path)

    taxonomy_path = str(default_taxonomy_path())
    try:
        taxonomy = load_risk_taxonomy(taxonomy_path)
    except Exception:
        taxonomy = {}

    context = _build_context()

    _emit(EventType.STAGE_COMPLETED, "Init complete", llm_enabled=context.client is not None)

    return {
        "pipeline_config": config.model_dump(),
        "risk_taxonomy": taxonomy,
        "llm_enabled": context.client is not None,
    }


def ingest_node(state: ClassifyState) -> dict[str, Any]:
    """Parse regulation, APQC hierarchy, and control files."""
    _emit(EventType.STAGE_STARTED, "Ingesting data")

    reg_path = state.get("regulation_path", "")
    apqc_path = state.get("apqc_path", "")
    controls_dir = state.get("controls_dir", "")

    errors: list[str] = []

    # Parse regulation
    try:
        regulation_name, obligations = parse_regulation_excel(reg_path)
        groups = group_obligations(obligations)
        groups_dicts = [g.model_dump() for g in groups]

        # Apply scope filtering
        scope = state.get("scope_config", {})
        scope_mode = scope.get("mode", "All obligations")
        if scope_mode == "Filter by subpart":
            allowed = [s.lower() for s in scope.get("subparts", [])]
            groups_dicts = [
                g for g in groups_dicts
                if g.get("subpart", "").lower() in allowed
            ]
        elif scope_mode == "Quick sample":
            n = scope.get("sample_count", 3)
            groups_dicts = groups_dicts[:n]

        # Recount obligations after filtering
        obligations_count = sum(g.get("obligation_count", 0) for g in groups_dicts)
    except Exception as exc:
        errors.append(f"Regulation parse error: {exc}")
        regulation_name = ""
        groups_dicts = []
        obligations_count = 0

    # Load APQC
    try:
        apqc_nodes = load_apqc_hierarchy(apqc_path)
        apqc_dicts = [n.model_dump() for n in apqc_nodes]
    except Exception as exc:
        errors.append(f"APQC load error: {exc}")
        apqc_dicts = []

    # Load controls
    config = state.get("pipeline_config", {})
    pattern = config.get("control_file_pattern", "section_*__controls.xlsx")
    try:
        control_files = discover_control_files(controls_dir, pattern)
        controls = load_and_merge_controls(control_files)
        control_dicts = [c.model_dump() for c in controls]
    except Exception as exc:
        errors.append(f"Control load error: {exc}")
        control_dicts = []

    _emit(
        EventType.INGEST_COMPLETED,
        f"Ingested {obligations_count} obligations ({len(groups_dicts)} groups), {len(apqc_dicts)} APQC nodes, {len(control_dicts)} controls",
    )

    return {
        "regulation_name": regulation_name,
        "total_obligations": obligations_count,
        "obligation_groups": groups_dicts,
        "apqc_nodes": apqc_dicts,
        "controls": control_dicts,
        "classify_idx": 0,
        "errors": errors,
    }


def classify_group_node(state: ClassifyState) -> dict[str, Any]:
    """Classify all obligations in the current group."""
    idx = state.get("classify_idx", 0)
    groups = state.get("obligation_groups", [])

    if idx >= len(groups):
        return {}

    group = groups[idx]
    total = len(groups)
    section_cit = group.get("section_citation", "")

    _emit(EventType.ITEM_STARTED, f"Classifying {section_cit} ({idx + 1}/{total})")

    context = _build_context()
    agent = _get_agent("classifier", context)

    loop = _get_loop()
    result = loop.run_until_complete(
        agent.execute(
            group=group,
            config=state.get("pipeline_config", {}),
            regulation_name=state.get("regulation_name", ""),
        )
    )

    classifications = result.get("classifications", [])

    # Validate and collect errors
    errors: list[str] = []
    all_passed = True
    all_failures: list[str] = []
    for c in classifications:
        passed, failures = validate_classification(c)
        if not passed:
            all_passed = False
            all_failures.extend(failures)
            errors.append(f"Classification validation for {c.get('citation', '?')}: {failures}")

    # Record quality metrics in trace DB
    if _trace_db and _trace_run_id:
        _trace_db.update_llm_call_quality(
            run_id=_trace_run_id,
            node_name="classify_group",
            agent_name="ObligationClassifierAgent",
            timestamp=time.time(),
            validation_passed=all_passed,
            validation_failures=all_failures,
            retry_attempt=0,
            output_type="classify",
            parsed_output=result,
        )

    _emit(EventType.GROUP_CLASSIFIED, f"Classified {len(classifications)} obligations in {section_cit}")

    return {
        "classified_obligations": classifications,
        "classify_idx": idx + 1,
        "errors": errors,
    }


def has_more_classify_groups(state: ClassifyState) -> str:
    """Conditional edge: loop or end."""
    if state.get("classify_idx", 0) < len(state.get("obligation_groups", [])):
        return "classify_group"
    return "end_classify"


def end_classify_node(state: ClassifyState) -> dict[str, Any]:
    """Summary statistics and completion event."""
    classified = state.get("classified_obligations", [])
    total = state.get("total_obligations", 0)

    _emit(
        EventType.PIPELINE_COMPLETED,
        f"Classification complete: {len(classified)} obligations classified out of {total}",
    )

    return {}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_classify_graph(trace_db=None, run_id: str = ""):
    """Build and compile the classification graph.

    Parameters
    ----------
    trace_db : TraceDB | None
        If provided, every node execution, event, and LLM call is recorded
        to the local SQLite trace database.
    run_id : str
        Unique identifier for this pipeline run (used for tracing).
    """
    # Store trace references for quality capture in graph nodes
    global _trace_db, _trace_run_id
    _trace_db = trace_db
    _trace_run_id = run_id

    # If tracing is enabled, also wrap the transport client
    if trace_db and run_id:
        _install_tracing_transport(trace_db, run_id)

    def _wrap(name, fn):
        if trace_db and run_id:
            return trace_node(trace_db, run_id, name)(fn)
        return fn

    graph = StateGraph(ClassifyState)
    graph.add_node("init", _wrap("init", init_node))
    graph.add_node("ingest", _wrap("ingest", ingest_node))
    graph.add_node("classify_group", _wrap("classify_group", classify_group_node))
    graph.add_node("end_classify", _wrap("end_classify", end_classify_node))
    graph.add_edge(START, "init")
    graph.add_edge("init", "ingest")
    graph.add_edge("ingest", "classify_group")
    graph.add_conditional_edges("classify_group", has_more_classify_groups)
    graph.add_edge("end_classify", END)
    return graph.compile()


def _install_tracing_transport(trace_db, run_id: str) -> None:
    """Replace the cached LLM client with a tracing wrapper."""
    global _llm_client_cache
    if _llm_client_cache is None:
        _llm_client_cache = build_client_from_env()
    if _llm_client_cache and not isinstance(_llm_client_cache, TracingTransportClient):
        _llm_client_cache = TracingTransportClient(_llm_client_cache, trace_db, run_id)
    # Also update any already-cached agents so they use the wrapped client
    for agent in _agent_cache.values():
        if hasattr(agent, "context") and agent.context.client is not _llm_client_cache:
            agent.context.client = _llm_client_cache
