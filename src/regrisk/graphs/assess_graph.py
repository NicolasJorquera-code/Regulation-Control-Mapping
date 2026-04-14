"""
Graph 2: Assess Graph — Map + Assess Coverage + Score Risks + Finalize.

Topology::

    START → map_group ─┐
               ↑        │ has_more_map_groups?
               └────────┘
                  │ (all mapped)
                  ▼
            prepare_assessment → assess_coverage ─┐
                                      ↑            │ has_more_assessments?
                                      └────────────┘
                                            │ (all assessed)
                                            ▼
                                    prepare_risks → extract_and_score ─┐
                                                          ↑             │ has_more_gaps?
                                                          └─────────────┘
                                                                │
                                                                ▼
                                                            finalize → END
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

from langgraph.graph import END, START, StateGraph

from regrisk.agents.apqc_mapper import APQCMapperAgent
from regrisk.agents.base import AgentContext
from regrisk.agents.coverage_assessor import CoverageAssessorAgent
from regrisk.agents.risk_extractor_scorer import RiskExtractorAndScorerAgent
from regrisk.core.events import EventEmitter, EventType, PipelineEvent
from regrisk.core.models import APQCNode, ControlRecord
from regrisk.core.transport import build_client_from_env
from regrisk.graphs.assess_state import AssessState
from regrisk.graphs.graph_infra import GraphInfra
from regrisk.tracing.decorators import trace_node
from regrisk.tracing.transport_wrapper import TracingTransportClient
from regrisk.ingest.apqc_loader import build_apqc_summary
from regrisk.core.scoring import deduplicate_risks
from regrisk.ingest.control_loader import build_control_index, find_controls_for_apqc
from regrisk.validation.validator import validate_coverage, validate_mapping, validate_risk


# ---------------------------------------------------------------------------
# Module-level infrastructure
# ---------------------------------------------------------------------------

_infra = GraphInfra()
_partial_assessments: list[dict] = []
_trace_db: Any = None
_trace_run_id: str = ""
_auto_save_fn: Any = None  # callable(partial_assessments) or None
_AUTO_SAVE_INTERVAL: int = 25

_AGENT_CLASSES: dict[str, type] = {
    "mapper": APQCMapperAgent,
    "assessor": CoverageAssessorAgent,
    "risk_scorer": RiskExtractorAndScorerAgent,
}


def set_emitter(emitter: EventEmitter) -> None:
    _infra.set_emitter(emitter)


def get_emitter() -> EventEmitter:
    return _infra.get_emitter()


def set_auto_save(fn: Any, interval: int = 25) -> None:
    """Register a callback invoked every *interval* assessments with the partial list."""
    global _auto_save_fn, _AUTO_SAVE_INTERVAL
    _auto_save_fn = fn
    _AUTO_SAVE_INTERVAL = interval


def get_partial_assessments() -> list[dict]:
    """Return coverage assessments accumulated so far (survives graph failure)."""
    return list(_partial_assessments)


def reset_caches() -> None:
    """Reset all module-level caches (for test isolation and between runs)."""
    global _partial_assessments, _trace_db, _trace_run_id, _auto_save_fn
    _partial_assessments = []
    _infra.reset_caches()
    _trace_db = None
    _trace_run_id = ""
    _auto_save_fn = None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def map_group_node(state: AssessState) -> dict[str, Any]:
    """Map obligations in the current group to APQC processes."""
    idx = state.get("map_idx", 0)
    groups = state.get("mappable_groups", [])

    if idx >= len(groups):
        return {}

    group = groups[idx]
    total = len(groups)
    section_cit = group.get("section_citation", "")

    _infra.emit_event(EventType.ITEM_STARTED, f"Mapping {section_cit} ({idx + 1}/{total})")

    context = _infra.build_agent_context()
    agent = _infra.get_agent("mapper", _AGENT_CLASSES, context)

    # Build APQC summary from nodes in state
    apqc_node_dicts = state.get("apqc_nodes", [])
    apqc_nodes = [APQCNode(**n) for n in apqc_node_dicts]
    config = state.get("pipeline_config", {})
    apqc_summary = build_apqc_summary(apqc_nodes, max_depth=config.get("apqc_mapping_depth", 3))

    loop = _infra.get_or_create_event_loop()
    result = loop.run_until_complete(
        agent.execute(
            obligations=group.get("obligations", []),
            apqc_summary=apqc_summary,
            config=config,
            regulation_name=state.get("regulation_name", ""),
            section_citation=section_cit,
            section_title=group.get("section_title", ""),
        )
    )

    mappings = result.get("mappings", [])

    # Validate
    errors: list[str] = []
    all_passed = True
    all_failures: list[str] = []
    for m in mappings:
        passed, failures = validate_mapping(m)
        if not passed:
            all_passed = False
            all_failures.extend(failures)
            errors.append(f"Mapping validation for {m.get('citation', '?')}: {failures}")

    # Record quality metrics in trace DB
    if _trace_db and _trace_run_id:
        _trace_db.update_llm_call_quality(
            run_id=_trace_run_id,
            node_name="map_group",
            agent_name="APQCMapperAgent",
            timestamp=time.time(),
            validation_passed=all_passed,
            validation_failures=all_failures,
            retry_attempt=0,
            output_type="map",
            parsed_output=result,
        )

    _infra.emit_event(EventType.MAPPING_COMPLETED, f"Mapped {len(mappings)} obligations in {section_cit}")

    return {
        "obligation_mappings": mappings,
        "map_idx": idx + 1,
        "errors": errors,
    }


def has_more_map_groups(state: AssessState) -> str:
    if state.get("map_idx", 0) < len(state.get("mappable_groups", [])):
        return "map_group"
    return "prepare_assessment"


def prepare_assessment_node(state: AssessState) -> dict[str, Any]:
    """Build assessment items: (obligation, mapping, candidate controls)."""
    _infra.emit_event(EventType.STAGE_STARTED, "Preparing coverage assessment")

    mappings = state.get("obligation_mappings", [])
    control_dicts = state.get("controls", [])
    control_index = build_control_index(
        [ControlRecord(**c) for c in control_dicts]
    ) if control_dicts else {}

    # Build a lookup from citation to obligation data
    approved = state.get("approved_obligations", [])
    ob_lookup: dict[str, dict[str, Any]] = {}
    for ob in approved:
        ob_lookup[ob.get("citation", "")] = ob

    assess_items: list[dict[str, Any]] = []
    for m in mappings:
        cit = m.get("citation", "")
        apqc_id = m.get("apqc_hierarchy_id", "")

        # Find candidate controls by structural match
        candidates = find_controls_for_apqc(
            {hid: [c.model_dump() if hasattr(c, "model_dump") else c for c in ctrls]
             for hid, ctrls in control_index.items()},
            apqc_id,
        ) if control_index else []

        # Convert ControlRecord objects to dicts if needed
        candidate_dicts = [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in candidates
        ]

        assess_items.append({
            "obligation": ob_lookup.get(cit, {"citation": cit}),
            "mapping": m,
            "apqc_hierarchy_id": apqc_id,
            "apqc_process_name": m.get("apqc_process_name", ""),
            "candidate_controls": candidate_dicts,
        })

    _infra.emit_event(EventType.STAGE_COMPLETED, f"Prepared {len(assess_items)} assessment items")

    return {
        "assess_items": assess_items,
        "assess_idx": 0,
    }


def assess_coverage_node(state: AssessState) -> dict[str, Any]:
    """Assess coverage for the current item."""
    idx = state.get("assess_idx", 0)
    items = state.get("assess_items", [])

    if idx >= len(items):
        return {}

    item = items[idx]
    total = len(items)
    citation = item.get("obligation", {}).get("citation", "")

    _infra.emit_event(EventType.ITEM_STARTED, f"Assessing coverage ({idx + 1}/{total}): {citation}")

    candidates = item.get("candidate_controls", [])
    obligation = item.get("obligation", {})
    apqc_id = item.get("apqc_hierarchy_id", "")
    apqc_name = item.get("apqc_process_name", "")

    context = _infra.build_agent_context(max_tokens=2048)
    agent = _infra.get_agent("assessor", _AGENT_CLASSES, context)
    loop = _infra.get_or_create_event_loop()

    if not candidates:
        # No candidates → deterministic Not Covered
        assessment = loop.run_until_complete(
            agent.execute(
                obligation=obligation,
                control=None,
                apqc_hierarchy_id=apqc_id,
                apqc_process_name=apqc_name,
            )
        )
    else:
        # Evaluate best candidate
        best_assessment: dict[str, Any] | None = None
        for ctrl in candidates:
            result = loop.run_until_complete(
                agent.execute(
                    obligation=obligation,
                    control=ctrl,
                    apqc_hierarchy_id=apqc_id,
                    apqc_process_name=apqc_name,
                )
            )
            if best_assessment is None:
                best_assessment = result
            elif result.get("overall_coverage") == "Covered":
                best_assessment = result
                break
            elif (result.get("overall_coverage") == "Partially Covered"
                  and best_assessment.get("overall_coverage") == "Not Covered"):
                best_assessment = result

        assessment = best_assessment or {
            "citation": citation,
            "apqc_hierarchy_id": apqc_id,
            "control_id": None,
            "structural_match": False,
            "semantic_match": "None",
            "semantic_rationale": "",
            "relationship_match": "Not Satisfied",
            "relationship_rationale": "",
            "overall_coverage": "Not Covered",
        }

    # Validate
    errors: list[str] = []
    passed, failures = validate_coverage(assessment)
    if not passed:
        errors.append(f"Coverage validation for {citation}: {failures}")

    # Record quality metrics in trace DB
    if _trace_db and _trace_run_id:
        _trace_db.update_llm_call_quality(
            run_id=_trace_run_id,
            node_name="assess_coverage",
            agent_name="CoverageAssessorAgent",
            timestamp=time.time(),
            validation_passed=passed,
            validation_failures=failures,
            retry_attempt=0,
            output_type="assess",
            parsed_output=assessment,
        )

    _infra.emit_event(EventType.COVERAGE_ASSESSED, f"Coverage for {citation}: {assessment.get('overall_coverage', '?')}")

    # Track for partial-checkpoint recovery on failure
    _partial_assessments.append(assessment)

    # Periodic auto-save to protect against silent interruption
    if _auto_save_fn and len(_partial_assessments) % _AUTO_SAVE_INTERVAL == 0:
        try:
            _auto_save_fn(_partial_assessments)
        except Exception:
            pass  # never let auto-save failure break the pipeline

    return {
        "coverage_assessments": [assessment],
        "assess_idx": idx + 1,
        "errors": errors,
    }


def has_more_assessments(state: AssessState) -> str:
    if state.get("assess_idx", 0) < len(state.get("assess_items", [])):
        return "assess_coverage"
    return "prepare_risks"


def prepare_risks_node(state: AssessState) -> dict[str, Any]:
    """Filter assessments to only Not Covered and Partially Covered."""
    _infra.emit_event(EventType.STAGE_STARTED, "Preparing risk extraction")

    assessments = state.get("coverage_assessments", [])
    gaps = [a for a in assessments if a.get("overall_coverage") in ("Not Covered", "Partially Covered")]

    _infra.emit_event(EventType.STAGE_COMPLETED, f"Found {len(gaps)} coverage gaps requiring risk extraction")

    return {
        "gap_obligations": gaps,
        "risk_idx": 0,
    }


def extract_and_score_node(state: AssessState) -> dict[str, Any]:
    """Extract and score risks for the current gap."""
    idx = state.get("risk_idx", 0)
    gaps = state.get("gap_obligations", [])

    if idx >= len(gaps):
        return {}

    gap = gaps[idx]
    total = len(gaps)
    citation = gap.get("citation", "")

    _infra.emit_event(EventType.ITEM_STARTED, f"Extracting risks ({idx + 1}/{total}): {citation}")

    # Find the obligation data
    approved = state.get("approved_obligations", [])
    ob_data: dict[str, Any] = {}
    for ob in approved:
        if ob.get("citation") == citation:
            ob_data = ob
            break

    context = _infra.build_agent_context(max_tokens=4096)
    agent = _infra.get_agent("risk_scorer", _AGENT_CLASSES, context)
    loop = _infra.get_or_create_event_loop()

    # Count existing risks for sequential ID
    existing_risks = state.get("scored_risks", [])
    risk_counter = len(existing_risks)

    result = loop.run_until_complete(
        agent.execute(
            obligation=ob_data or {"citation": citation},
            coverage_status=gap.get("overall_coverage", "Not Covered"),
            gap_rationale=gap.get("semantic_rationale", ""),
            apqc_hierarchy_id=gap.get("apqc_hierarchy_id", ""),
            apqc_process_name=gap.get("apqc_process_name", ""),
            risk_taxonomy=state.get("risk_taxonomy", {}),
            config=state.get("pipeline_config", {}),
            risk_counter=risk_counter,
        )
    )

    risks = result.get("risks", [])

    # Validate
    errors: list[str] = []
    all_passed = True
    all_failures: list[str] = []
    for r in risks:
        passed, failures = validate_risk(r)
        if not passed:
            all_passed = False
            all_failures.extend(failures)
            errors.append(f"Risk validation for {citation}: {failures}")

    # Record quality metrics in trace DB
    if _trace_db and _trace_run_id:
        _trace_db.update_llm_call_quality(
            run_id=_trace_run_id,
            node_name="extract_and_score",
            agent_name="RiskExtractorAndScorerAgent",
            timestamp=time.time(),
            validation_passed=all_passed,
            validation_failures=all_failures,
            retry_attempt=0,
            output_type="risk",
            parsed_output=result,
        )

    _infra.emit_event(EventType.RISK_SCORED, f"Scored {len(risks)} risks for {citation}")

    return {
        "scored_risks": risks,
        "risk_idx": idx + 1,
        "errors": errors,
    }


def has_more_gaps(state: AssessState) -> str:
    if state.get("risk_idx", 0) < len(state.get("gap_obligations", [])):
        return "extract_and_score"
    return "finalize"


def finalize_node(state: AssessState) -> dict[str, Any]:
    """Assemble final reports."""
    _infra.emit_event(EventType.STAGE_STARTED, "Finalizing reports")

    approved = state.get("approved_obligations", [])
    mappings = state.get("obligation_mappings", [])
    assessments = state.get("coverage_assessments", [])
    raw_risks = state.get("scored_risks", [])

    # Deduplicate: keep one risk per (source_citation, risk_category),
    # prioritising the highest impact × frequency score.
    risk_id_prefix = state.get("pipeline_config", {}).get("risk_id_prefix", "RISK")
    risks = deduplicate_risks(raw_risks, id_prefix=risk_id_prefix)

    # Classified counts
    classified_counts: dict[str, int] = defaultdict(int)
    for ob in approved:
        cat = ob.get("obligation_category", "Not Assigned")
        classified_counts[cat] += 1

    # Coverage summary
    coverage_summary: dict[str, int] = defaultdict(int)
    for a in assessments:
        status = a.get("overall_coverage", "Not Covered")
        coverage_summary[status] += 1

    # Gaps
    gaps = [a for a in assessments if a.get("overall_coverage") in ("Not Covered", "Partially Covered")]

    gap_report = {
        "regulation_name": state.get("regulation_name", ""),
        "total_obligations": len(approved),
        "classified_counts": dict(classified_counts),
        "mapped_obligation_count": len(set(m.get("citation") for m in mappings)),
        "coverage_summary": dict(coverage_summary),
        "gaps": gaps,
    }

    # Compliance matrix
    matrix_rows: list[dict[str, Any]] = []
    mapping_lookup: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mapping_lookup[m.get("citation", "")].append(m)
    assessment_lookup: dict[tuple[str, str], dict] = {}
    for a in assessments:
        assessment_lookup[(a.get("citation", ""), a.get("apqc_hierarchy_id", ""))] = a
    risk_lookup: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risk_lookup[r.get("source_citation", "")].append(r)

    for ob in approved:
        cit = ob.get("citation", "")
        for m in mapping_lookup.get(cit, [{}]):
            apqc_id = m.get("apqc_hierarchy_id", "")
            a = assessment_lookup.get((cit, apqc_id), {})
            matrix_rows.append({
                "citation": cit,
                "obligation_category": ob.get("obligation_category", ""),
                "criticality_tier": ob.get("criticality_tier", ""),
                "apqc_hierarchy_id": apqc_id,
                "apqc_process_name": m.get("apqc_process_name", ""),
                "control_id": a.get("control_id", ""),
                "overall_coverage": a.get("overall_coverage", ""),
                "risk_ids": [r.get("risk_id", "") for r in risk_lookup.get(cit, [])],
            })

    compliance_matrix = {"rows": matrix_rows}

    # Risk register
    risk_dist: dict[str, int] = defaultdict(int)
    critical_count = 0
    high_count = 0
    for r in risks:
        risk_dist[r.get("risk_category", "Unknown")] += 1
        rating = r.get("inherent_risk_rating", "")
        if rating == "Critical":
            critical_count += 1
        elif rating == "High":
            high_count += 1

    risk_register = {
        "scored_risks": risks,
        "total_risks": len(risks),
        "risk_distribution": dict(risk_dist),
        "critical_count": critical_count,
        "high_count": high_count,
    }

    _infra.emit_event(
        EventType.PIPELINE_COMPLETED,
        f"Finalized: {len(assessments)} assessments, {len(gaps)} gaps, {len(risks)} risks",
    )

    # Compute run metrics after all phases are complete
    if _trace_db and _trace_run_id:
        try:
            _trace_db.compute_run_metrics(_trace_run_id)
        except Exception:
            pass  # metrics computation is best-effort

    return {
        "gap_report": gap_report,
        "compliance_matrix": compliance_matrix,
        "risk_register": risk_register,
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_assess_graph(trace_db=None, run_id: str = ""):
    """Build and compile the assessment graph.

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

    if trace_db and run_id:
        _infra.install_tracing_transport(trace_db, run_id)

    def _wrap(name, fn):
        if trace_db and run_id:
            return trace_node(trace_db, run_id, name)(fn)
        return fn

    graph = StateGraph(AssessState)
    graph.add_node("map_group", _wrap("map_group", map_group_node))
    graph.add_node("prepare_assessment", _wrap("prepare_assessment", prepare_assessment_node))
    graph.add_node("assess_coverage", _wrap("assess_coverage", assess_coverage_node))
    graph.add_node("prepare_risks", _wrap("prepare_risks", prepare_risks_node))
    graph.add_node("extract_and_score", _wrap("extract_and_score", extract_and_score_node))
    graph.add_node("finalize", _wrap("finalize", finalize_node))
    graph.add_edge(START, "map_group")
    graph.add_conditional_edges("map_group", has_more_map_groups)
    graph.add_edge("prepare_assessment", "assess_coverage")
    graph.add_conditional_edges("assess_coverage", has_more_assessments)
    graph.add_edge("prepare_risks", "extract_and_score")
    graph.add_conditional_edges("extract_and_score", has_more_gaps)
    graph.add_edge("finalize", END)
    return graph.compile()
