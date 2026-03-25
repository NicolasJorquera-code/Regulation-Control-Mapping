"""ControlForge Modular — LangGraph StateGraph for config-driven control generation.

8-node graph: init → select → spec → narrative → validate → [enrich | narrative(retry)]
             → merge → [loop or finalize] → END

When ``llm_enabled`` is False the graph uses deterministic builders (no LLM calls).
When ``llm_enabled`` is True each agent node calls the LLM with config-aware prompts
and falls back to the deterministic path on any error.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from controlnexus.agents.base import AgentContext, BaseAgent
from controlnexus.core.domain_config import DomainConfig, load_domain_config
from controlnexus.core.transport import build_client_from_env
from controlnexus.graphs.forge_modular_helpers import (
    assign_control_ids,
    build_assignment_matrix,
    build_deterministic_enriched,
    build_deterministic_narrative,
    build_deterministic_spec,
    build_enricher_system_prompt,
    build_enricher_user_prompt,
    build_narrative_system_prompt,
    build_narrative_user_prompt,
    build_spec_system_prompt,
    build_spec_user_prompt,
)
from controlnexus.validation.validator import build_retry_appendix, validate

logger = logging.getLogger(__name__)


# ── Reducer ───────────────────────────────────────────────────────────────────


def _add(left: list, right: list) -> list:
    return left + right


# ── State ─────────────────────────────────────────────────────────────────────


class ForgeState(TypedDict, total=False):
    """State for the ControlForge Modular graph."""

    # Config (set by init)
    config_path: str
    domain_config: dict[str, Any]
    llm_enabled: bool

    # Distribution overrides from UI
    distribution_config: dict[str, Any]

    # Target
    target_count: int

    # Assignment tracking
    assignments: list[dict[str, Any]]
    current_idx: int
    current_assignment: dict[str, Any]

    # Per-control pipeline
    current_spec: dict[str, Any]
    current_narrative: dict[str, Any]
    current_enriched: dict[str, Any]
    retry_count: int
    validation_passed: bool
    validation_failures: list[str]
    retry_appendix: str

    # Accumulated output
    generated_records: Annotated[list[dict[str, Any]], _add]

    # Final
    plan_payload: dict[str, Any]


# ── Node implementations ─────────────────────────────────────────────────────


def init_node(state: ForgeState) -> dict[str, Any]:
    """Load DomainConfig and build the assignment matrix."""
    config_path = state.get("config_path", "")
    if not config_path:
        raise ValueError("config_path is required in ForgeState")

    domain_config = load_domain_config(Path(config_path))
    target = state.get("target_count", 10)
    dist_cfg = state.get("distribution_config")

    assignments = build_assignment_matrix(domain_config, target, dist_cfg)
    logger.info("init_node: built %d assignments for target_count=%d", len(assignments), target)

    return {
        "domain_config": domain_config.model_dump(),
        "llm_enabled": state.get("llm_enabled", False),
        "assignments": assignments,
        "current_idx": 0,
        "generated_records": [],
    }


def select_node(state: ForgeState) -> dict[str, Any]:
    """Pick the current assignment and reset per-control state."""
    idx = state.get("current_idx", 0)
    assignments = state.get("assignments", [])
    if idx >= len(assignments):
        raise IndexError(
            f"select_node: current_idx={idx} is out of range for "
            f"{len(assignments)} assignments"
        )
    return {
        "current_assignment": assignments[idx],
        "retry_count": 0,
        "validation_passed": False,
    }


# ── LLM helpers ───────────────────────────────────────────────────────────────

# Module-level caches so the transport client is built once and each agent
# keeps its call_count across controls (producing "LLM call #1", "#2", …).
# A dedicated event loop is kept alive so the async httpx connection pool
# doesn't break between node calls (asyncio.run() would close the loop each
# time, killing the TCP connections).
_llm_client_cache: dict[str, Any] = {}  # {"client": AsyncTransportClient | None}
_agent_cache: dict[str, BaseAgent] = {}  # {"SpecAgent": agent, ...}
_event_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop for LLM calls."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on the persistent event loop."""
    return _get_loop().run_until_complete(coro)


def _get_client() -> Any | None:
    """Return the cached transport client, building it once."""
    if "client" not in _llm_client_cache:
        _llm_client_cache["client"] = build_client_from_env()
    return _llm_client_cache["client"]


def _get_agent(name: str) -> BaseAgent | None:
    """Return a cached BaseAgent wrapper with the given display *name*.

    Returns ``None`` when no LLM credentials are available.
    """
    client = _get_client()
    if client is None:
        return None

    if name not in _agent_cache:

        class _Proxy(BaseAgent):
            async def execute(self, **kwargs: Any) -> dict[str, Any]:
                raise NotImplementedError  # we use call_llm directly

        ctx = AgentContext(client=client, model=client.model)
        _agent_cache[name] = _Proxy(ctx, name=name)

    return _agent_cache[name]


def reset_llm_cache() -> None:
    """Clear the module-level LLM caches (useful between test runs)."""
    global _event_loop
    if _event_loop is not None and not _event_loop.is_closed():
        _event_loop.close()
    _event_loop = None
    _llm_client_cache.clear()
    _agent_cache.clear()


# ── Agent nodes ───────────────────────────────────────────────────────────────


def spec_node(state: ForgeState) -> dict[str, Any]:
    """Generate a control specification (deterministic or LLM)."""
    assignment = state["current_assignment"]
    config = DomainConfig(**state["domain_config"])

    if not state.get("llm_enabled"):
        return {"current_spec": build_deterministic_spec(assignment, config)}

    try:
        agent = _get_agent("SpecAgent")
        if agent is None:
            return {"current_spec": build_deterministic_spec(assignment, config)}

        system_prompt = build_spec_system_prompt(config)
        user_prompt = build_spec_user_prompt(assignment, config)
        raw = _run_async(agent.call_llm(system_prompt, user_prompt))
        result = agent.parse_json(raw)
        return {"current_spec": result}
    except Exception:
        logger.warning("spec_node LLM failed — falling back to deterministic", exc_info=True)
        return {"current_spec": build_deterministic_spec(assignment, config)}


def narrative_node(state: ForgeState) -> dict[str, Any]:
    """Generate a 5W narrative from the spec (deterministic or LLM)."""
    spec = state["current_spec"]
    config = DomainConfig(**state["domain_config"])

    if not state.get("llm_enabled"):
        return {"current_narrative": build_deterministic_narrative(spec, config)}

    try:
        agent = _get_agent("NarrativeAgent")
        if agent is None:
            return {"current_narrative": build_deterministic_narrative(spec, config)}

        system_prompt = build_narrative_system_prompt(config)
        retry_appendix = state.get("retry_appendix", "")
        user_prompt = build_narrative_user_prompt(spec, config, retry_appendix or None)
        raw = _run_async(agent.call_llm(system_prompt, user_prompt))
        result = agent.parse_json(raw)
        return {"current_narrative": result}
    except Exception:
        logger.warning("narrative_node LLM failed — falling back to deterministic", exc_info=True)
        return {"current_narrative": build_deterministic_narrative(spec, config)}


def validate_node(state: ForgeState) -> dict[str, Any]:
    """Validate the narrative against the spec.

    Deterministic output is trusted (always passes).  LLM output goes
    through the 6-rule validator with config-driven word-count limits.
    After 3 failed retries the control is accepted as-is.
    """
    if not state.get("llm_enabled"):
        return {"validation_passed": True, "validation_failures": [], "retry_appendix": ""}

    narrative = state.get("current_narrative", {})
    spec = state.get("current_spec", {})
    config = DomainConfig(**state["domain_config"])
    retry_count = state.get("retry_count", 0)

    result = validate(
        narrative, spec,
        min_words=config.narrative.word_count_min,
        max_words=config.narrative.word_count_max,
    )

    if result.passed:
        return {"validation_passed": True, "validation_failures": [], "retry_appendix": ""}

    if retry_count >= 3:
        # Max retries — accept as-is
        return {"validation_passed": True, "validation_failures": result.failures, "retry_appendix": ""}

    appendix = build_retry_appendix(
        retry_count + 1, 3, result.failures, result.word_count,
        min_words=config.narrative.word_count_min,
        max_words=config.narrative.word_count_max,
    )
    return {
        "validation_passed": False,
        "retry_count": retry_count + 1,
        "validation_failures": result.failures,
        "retry_appendix": appendix,
    }


def enrich_node(state: ForgeState) -> dict[str, Any]:
    """Enrich a validated control (deterministic or LLM)."""
    spec = state["current_spec"]
    narrative = state.get("current_narrative", {})
    config = DomainConfig(**state["domain_config"])

    if not state.get("llm_enabled"):
        enriched = build_deterministic_enriched(spec, narrative, config)
        return {"current_enriched": enriched, "validation_passed": True}

    try:
        agent = _get_agent("EnricherAgent")
        if agent is None:
            enriched = build_deterministic_enriched(spec, narrative, config)
            return {"current_enriched": enriched, "validation_passed": True}

        system_prompt = build_enricher_system_prompt(config)
        user_prompt = build_enricher_user_prompt(narrative, config)
        raw = _run_async(agent.call_llm(system_prompt, user_prompt))
        llm_result = agent.parse_json(raw)

        # Merge spec + narrative + enrichment into a full record
        enriched = build_deterministic_enriched(spec, narrative, config)
        if "refined_full_description" in llm_result:
            enriched["full_description"] = llm_result["refined_full_description"]
        if "quality_rating" in llm_result:
            enriched["quality_rating"] = llm_result["quality_rating"]
        return {"current_enriched": enriched, "validation_passed": True}
    except Exception:
        logger.warning("enrich_node LLM failed — falling back to deterministic", exc_info=True)
        enriched = build_deterministic_enriched(spec, narrative, config)
        return {"current_enriched": enriched, "validation_passed": True}


def merge_node(state: ForgeState) -> dict[str, Any]:
    """Append the current record and advance the index."""
    return {
        "generated_records": [state["current_enriched"]],
        "current_idx": state["current_idx"] + 1,
    }


def finalize_node(state: ForgeState) -> dict[str, Any]:
    """Assign control IDs and build the final plan payload."""
    config = DomainConfig(**state["domain_config"])
    records = list(state.get("generated_records", []))

    final_records = assign_control_ids(records, config)

    return {
        "plan_payload": {
            "config_name": config.name,
            "total_controls": len(final_records),
            "control_types_used": list({r["control_type"] for r in final_records}),
            "final_records": final_records,
        },
    }


# ── Routing ───────────────────────────────────────────────────────────────────


def after_init(state: ForgeState) -> str:
    """Route after init: skip to finalize if no assignments were built."""
    if not state.get("assignments"):
        return "finalize"
    return "select"


def after_validate(state: ForgeState) -> str:
    """Route after validation: enrich if passed, retry narrative if not."""
    if state.get("validation_passed", False):
        return "enrich"
    return "narrative"


def has_more(state: ForgeState) -> str:
    """Route back to select if more assignments, else finalize."""
    next_idx = state.get("current_idx", 0)
    total = len(state.get("assignments", []))
    if next_idx < total:
        return "select"
    return "finalize"


# ── Graph builder ─────────────────────────────────────────────────────────────


def build_forge_graph() -> StateGraph:
    """Build and return the ControlForge Modular graph.

    Topology (8 nodes)::

        init → select → spec → narrative → validate
            → [enrich | narrative (retry)]
            → merge → [select (loop) | finalize] → END
    """
    graph = StateGraph(ForgeState)

    graph.add_node("init", init_node)
    graph.add_node("select", select_node)
    graph.add_node("spec", spec_node)
    graph.add_node("narrative", narrative_node)
    graph.add_node("validate", validate_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("merge", merge_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("init")
    graph.add_conditional_edges("init", after_init, {
        "select": "select",
        "finalize": "finalize",
    })
    graph.add_edge("select", "spec")
    graph.add_edge("spec", "narrative")
    graph.add_edge("narrative", "validate")
    graph.add_conditional_edges("validate", after_validate, {
        "enrich": "enrich",
        "narrative": "narrative",
    })
    graph.add_edge("enrich", "merge")
    graph.add_conditional_edges("merge", has_more, {
        "select": "select",
        "finalize": "finalize",
    })
    graph.add_edge("finalize", END)

    return graph
