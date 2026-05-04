"""Flagship LangGraph workflow for Risk Inventory Builder."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from controlnexus.core.events import EventType
from controlnexus.graphs.graph_infra import _emit_event
from controlnexus.risk_inventory.demo import load_knowledge_pack
from controlnexus.risk_inventory.models import RiskInventoryRun, RiskInventoryWorkspace
from controlnexus.risk_inventory.services import (
    build_control_gaps,
    build_synthetic_control_recommendations,
    default_agent_trace_events,
    run_risk_inventory_workflow,
    validate_knowledge_pack,
)


class FlagshipRiskInventoryState(TypedDict, total=False):
    """State for the flagship risk inventory workflow."""

    knowledge_pack_path: str
    workspace: dict[str, Any]
    process_id: str
    llm_enabled: bool
    validation_findings: list[dict[str, Any]]
    selected_run: dict[str, Any]
    agent_trace: list[dict[str, Any]]
    synthetic_control_recommendations: list[dict[str, Any]]
    final_report: dict[str, Any]


def data_intake_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    workspace_data = state.get("workspace")
    workspace = (
        RiskInventoryWorkspace.model_validate(workspace_data)
        if workspace_data
        else load_knowledge_pack(state.get("knowledge_pack_path") or None)
    )
    findings = validate_knowledge_pack(workspace)
    _emit_event(
        EventType.STAGE_STARTED,
        f"Knowledge pack loaded: {workspace.bank_name}",
        business_units=len(workspace.business_units),
        processes=len(workspace.processes),
    )
    return {
        "workspace": workspace.model_dump(),
        "validation_findings": [finding.model_dump() for finding in findings],
    }


def taxonomy_applicability_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    workspace = RiskInventoryWorkspace.model_validate(state["workspace"])
    run = run_risk_inventory_workflow(
        workspace,
        {"process_id": state.get("process_id", "")},
        llm_enabled=state.get("llm_enabled", False),
    )
    _emit_event(
        EventType.AGENT_COMPLETED,
        f"Taxonomy applicability completed for {run.input_context.process_name}",
        records=len(run.records),
    )
    return {"selected_run": run.model_dump()}


def risk_statement_generation_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    _emit_event(
        EventType.AGENT_COMPLETED,
        f"Risk statements prepared for {len(run.records)} records",
    )
    return {}


def inherent_risk_calculation_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    _emit_event(
        EventType.STAGE_COMPLETED,
        "Inherent risk calculated by deterministic matrix",
        high_plus=sum(record.inherent_risk.inherent_rating.value in {"High", "Critical"} for record in run.records),
    )
    return {}


def control_coverage_mapping_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    _emit_event(
        EventType.AGENT_COMPLETED,
        "Control coverage mapping completed",
        mapped_controls=sum(len(record.control_mappings) for record in run.records),
    )
    return {}


def gap_analysis_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    workspace = RiskInventoryWorkspace.model_validate(state["workspace"])
    recommendations = []
    updated_records = []
    for record in run.records:
        gaps = build_control_gaps(record)
        recs = build_synthetic_control_recommendations(record, workspace)
        recommendations.extend(recs)
        updated_records.append(
            record.model_copy(
                update={
                    "control_gaps": gaps,
                    "synthetic_control_recommendations": recs,
                }
            )
        )
    run = run.model_copy(update={"records": updated_records})
    _emit_event(
        EventType.STAGE_COMPLETED,
        "Gap analysis and synthetic control recommendations completed",
        recommendations=len(recommendations),
    )
    return {
        "selected_run": run.model_dump(),
        "synthetic_control_recommendations": [item.model_dump() for item in recommendations],
    }


def residual_risk_calculation_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    _emit_event(
        EventType.STAGE_COMPLETED,
        "Residual risk calculated by deterministic matrix",
        high_plus=sum(record.residual_risk.residual_rating.value in {"High", "Critical"} for record in run.records),
    )
    return {}


def kri_recommendation_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    workspace = RiskInventoryWorkspace.model_validate(state["workspace"])
    run = RiskInventoryRun.model_validate(state["selected_run"])
    kri_count = sum(len(workspace.kris_for_taxonomy(record.taxonomy_node.id)) for record in run.records)
    _emit_event(EventType.AGENT_COMPLETED, "KRI recommendations prepared", kris=kri_count)
    return {}


def review_challenge_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    _emit_event(
        EventType.STAGE_COMPLETED,
        "Review and challenge package prepared",
        review_records=sum(bool(record.review_challenges) for record in run.records),
    )
    return {}


def executive_synthesis_node(state: FlagshipRiskInventoryState) -> dict[str, Any]:
    run = RiskInventoryRun.model_validate(state["selected_run"])
    trace = default_agent_trace_events(
        run,
        mode="live_llm" if state.get("llm_enabled", False) else "deterministic_fallback",
    )
    run = run.model_copy(update={"events": [event.model_dump() for event in trace]})
    _emit_event(EventType.PIPELINE_COMPLETED, f"Risk inventory ready: {run.run_id}")
    return {
        "agent_trace": [event.model_dump() for event in trace],
        "final_report": run.model_dump(),
    }


def build_flagship_risk_inventory_graph() -> Any:
    """Build the flagship Risk Inventory Builder graph."""
    graph = StateGraph(FlagshipRiskInventoryState)
    graph.add_node("data_intake", data_intake_node)
    graph.add_node("taxonomy_applicability", taxonomy_applicability_node)
    graph.add_node("risk_statement_generation", risk_statement_generation_node)
    graph.add_node("inherent_risk_calculation", inherent_risk_calculation_node)
    graph.add_node("control_coverage_mapping", control_coverage_mapping_node)
    graph.add_node("gap_analysis", gap_analysis_node)
    graph.add_node("residual_risk_calculation", residual_risk_calculation_node)
    graph.add_node("kri_recommendation", kri_recommendation_node)
    graph.add_node("review_challenge", review_challenge_node)
    graph.add_node("executive_synthesis", executive_synthesis_node)

    graph.set_entry_point("data_intake")
    graph.add_edge("data_intake", "taxonomy_applicability")
    graph.add_edge("taxonomy_applicability", "risk_statement_generation")
    graph.add_edge("risk_statement_generation", "inherent_risk_calculation")
    graph.add_edge("inherent_risk_calculation", "control_coverage_mapping")
    graph.add_edge("control_coverage_mapping", "gap_analysis")
    graph.add_edge("gap_analysis", "residual_risk_calculation")
    graph.add_edge("residual_risk_calculation", "kri_recommendation")
    graph.add_edge("kri_recommendation", "review_challenge")
    graph.add_edge("review_challenge", "executive_synthesis")
    graph.add_edge("executive_synthesis", END)
    return graph
