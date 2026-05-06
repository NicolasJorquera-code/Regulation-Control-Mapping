"""LangGraph workflow for Risk Inventory Builder."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from controlnexus.core.events import EventType
from controlnexus.graphs.graph_infra import _emit_event
from controlnexus.risk_inventory.calculators import (
    ControlEnvironmentCalculator,
    InherentRiskCalculator,
    ResidualRiskCalculator,
)
from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.demo import load_demo_risk_inventory
from controlnexus.risk_inventory.export import export_risk_inventory_to_excel
from controlnexus.risk_inventory.models import (
    ControlDesignEffectivenessAssessment,
    ControlEffectivenessRating,
    ControlEnvironmentAssessment,
    ControlMapping,
    ControlOperatingEffectivenessAssessment,
    EvidenceReference,
    ExecutiveSummary,
    ExposureMetric,
    ImpactAssessment,
    ImpactDimension,
    ImpactDimensionAssessment,
    ImpactScore,
    InherentRiskAssessment,
    LikelihoodAssessment,
    LikelihoodScore,
    MaterializationType,
    ProcessContext,
    ReviewChallengeRecord,
    ReviewStatus,
    RiskApplicabilityAssessment,
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskStatement,
)
from controlnexus.risk_inventory.taxonomy import (
    find_applicable_nodes,
    load_risk_inventory_taxonomy,
    normalize_root_cause_names,
    risk_statement_with_root_cause_selection,
)
from controlnexus.risk_inventory.validator import RiskInventoryValidator


class RiskInventoryState(TypedDict, total=False):
    """State for the risk inventory graph."""

    run_id: str
    tenant_id: str
    process_context: dict[str, Any]
    control_inventory: list[dict[str, Any]]
    config_dir: str
    max_risks: int
    demo_mode: bool
    export_path: str
    input_context: dict[str, Any]
    taxonomy_nodes: list[dict[str, Any]]
    risk_records: list[dict[str, Any]]
    validation_findings: list[dict[str, Any]]
    final_report: dict[str, Any]
    export_paths: list[str]


def context_ingestion_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        run = load_demo_risk_inventory()
        return {"final_report": run.model_dump(), "input_context": run.input_context.model_dump()}

    raw_context = state.get("process_context") or {}
    context = ProcessContext.model_validate(raw_context)
    _emit_event(EventType.STAGE_STARTED, f"Risk inventory context loaded: {context.process_name}")
    return {"input_context": context.model_dump()}


def taxonomy_applicability_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    context = ProcessContext.model_validate(state["input_context"])
    nodes = load_risk_inventory_taxonomy(state.get("config_dir"))
    process_text = " ".join(
        [
            context.process_name,
            context.product,
            context.business_unit,
            context.description,
            " ".join(context.systems),
        ]
    )
    selected = find_applicable_nodes(process_text, nodes, include_all_if_none=True)[: state.get("max_risks", 6)]
    return {"taxonomy_nodes": [node.model_dump() for node in selected]}


def risk_statement_generation_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    context = ProcessContext.model_validate(state["input_context"])
    records = []
    for idx, raw_node in enumerate(state.get("taxonomy_nodes", []), start=1):
        node = load_risk_inventory_taxonomy_node(raw_node)
        applicability = RiskApplicabilityAssessment(
            materializes=True,
            materialization_type=MaterializationType.PROCESS_SPECIFIC,
            rationale=(
                f"{node.level_2_category} applies because {context.process_name} involves "
                f"{', '.join(node.applicable_process_patterns[:3]) or 'configured risk drivers'}."
            ),
            confidence=0.72,
        )
        causes = normalize_root_cause_names(node.typical_root_causes[:3], node=node, max_items=3)
        statement_text = risk_statement_with_root_cause_selection(
            _process_specific_risk_statement(context, node, causes),
            causes,
        )
        records.append(
            {
                "risk_id": f"RI-{idx:03d}",
                "process_id": context.process_id,
                "process_name": context.process_name,
                "product": context.product,
                "taxonomy_node": node.model_dump(),
                "applicability": applicability.model_dump(),
                "risk_statement": RiskStatement(
                    risk_description=statement_text,
                    risk_event=statement_text,
                    causes=causes,
                    consequences=_contextual_consequences(context, node),
                    affected_stakeholders=context.stakeholders,
                ).model_dump(),
            }
        )
    return {"risk_records": records}


def exposure_metrics_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    records = []
    for record in state.get("risk_records", []):
        node = load_risk_inventory_taxonomy_node(record["taxonomy_node"])
        record = dict(record)
        record["exposure_metrics"] = [
            ExposureMetric(
                metric_name=metric,
                metric_value=_metric_value_from_context(metric, context_description=state.get("input_context", {}).get("description", "")),
                description=f"Recommended exposure metric for {node.level_2_category}.",
                source="workflow configuration",
                supports=["likelihood", "impact"],
            ).model_dump()
            for metric in node.common_exposure_metrics[:4]
        ]
        records.append(record)
    return {"risk_records": records}


def impact_assessment_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    records = []
    for record in state.get("risk_records", []):
        node = load_risk_inventory_taxonomy_node(record["taxonomy_node"])
        likely = set(node.likely_impact_dimensions)
        dims = []
        for dimension in ImpactDimension:
            score = ImpactScore.SIGNIFICANT if dimension in likely else ImpactScore.MEANINGFUL
            dims.append(
                ImpactDimensionAssessment(
                    dimension=dimension,
                    score=score,
                    rationale=f"{node.level_2_category} has {dimension.value} exposure based on configured taxonomy guidance.",
                )
            )
        overall = max(dim.score for dim in dims)
        record = dict(record)
        record["impact_assessment"] = ImpactAssessment(
            dimensions=dims,
            overall_impact_score=ImpactScore(overall),
            overall_impact_rationale=(
                f"Overall impact follows the highest material dimension for {node.level_2_category}."
            ),
        ).model_dump()
        records.append(record)
    return {"risk_records": records}


def likelihood_assessment_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    context = ProcessContext.model_validate(state["input_context"])
    score = LikelihoodScore.MEDIUM_HIGH if any(token in context.description.lower() for token in ("daily", "high-value", "payment")) else LikelihoodScore.MEDIUM_LOW
    records = []
    for record in state.get("risk_records", []):
        record = dict(record)
        record["likelihood_assessment"] = LikelihoodAssessment(
            likelihood_score=score,
            likelihood_rating={1: "Low", 2: "Medium Low", 3: "Medium High", 4: "High"}[int(score)],
            rationale=(
                f"Likelihood reflects process exposure, transaction frequency, and event drivers in {context.process_name}."
            ),
            assumptions=["Frequency and exposure should be refined when production metrics are uploaded."],
        ).model_dump()
        records.append(record)
    return {"risk_records": records}


def inherent_risk_calculator_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    calc = InherentRiskCalculator(MatrixConfigLoader(state.get("config_dir")).inherent_matrix())
    records = []
    for record in state.get("risk_records", []):
        impact = ImpactAssessment.model_validate(record["impact_assessment"])
        likelihood = LikelihoodAssessment.model_validate(record["likelihood_assessment"])
        record = dict(record)
        record["inherent_risk"] = calc.calculate(
            impact.overall_impact_score,
            likelihood.likelihood_score,
            rationale="Calculated by deterministic inherent risk matrix.",
        ).model_dump()
        records.append(record)
    return {"risk_records": records}


def control_mapping_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    controls = state.get("control_inventory", [])
    records = []
    for record in state.get("risk_records", []):
        node = load_risk_inventory_taxonomy_node(record["taxonomy_node"])
        matches = _match_controls(node, controls)
        record = dict(record)
        record["control_mappings"] = [_mapping_from_control(control, node).model_dump() for control in matches]
        records.append(record)
    return {"risk_records": records}


def control_effectiveness_node(state: RiskInventoryState) -> dict[str, Any]:
    return {} if state.get("demo_mode") else {"risk_records": state.get("risk_records", [])}


def control_environment_calculator_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    calc = ControlEnvironmentCalculator()
    records = []
    for record in state.get("risk_records", []):
        mappings = [ControlMapping.model_validate(item) for item in record.get("control_mappings", [])]
        design = _worst([m.design_effectiveness.rating for m in mappings if m.design_effectiveness])
        operating = _worst([m.operating_effectiveness.rating for m in mappings if m.operating_effectiveness])
        record = dict(record)
        record["control_environment"] = calc.calculate(design, operating).model_dump()
        records.append(record)
    return {"risk_records": records}


def residual_risk_calculator_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    loader = MatrixConfigLoader(state.get("config_dir"))
    calc = ResidualRiskCalculator(loader.residual_matrix(), loader.management_response_rules())
    records = []
    for record in state.get("risk_records", []):
        inherent = record["inherent_risk"]
        environment = record["control_environment"]
        record = dict(record)
        record["residual_risk"] = calc.calculate(
            inherent=InherentRiskAssessment.model_validate(inherent),
            environment=ControlEnvironmentAssessment.model_validate(environment),
        ).model_dump()
        records.append(record)
    return {"risk_records": records}


def review_challenge_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {}
    records = []
    for record in state.get("risk_records", []):
        node = load_risk_inventory_taxonomy_node(record["taxonomy_node"])
        record = dict(record)
        record["review_challenges"] = [
            ReviewChallengeRecord(
                review_status=ReviewStatus.PENDING_REVIEW,
                reviewer="Business reviewer",
                challenge_comments=f"Confirm applicability, scoring, controls, and residual response for {node.level_2_category}.",
                challenged_fields=["applicability", "impact_scores", "control_mapping", "residual_risk"],
            ).model_dump()
        ]
        record["evidence_references"] = [
            EvidenceReference(
                evidence_id=f"{record['risk_id']}-EVID",
                evidence_type="Process context",
                description="Generated from supplied process context and control inventory.",
                source="Risk Inventory Builder",
            ).model_dump()
        ]
        records.append(record)
    return {"risk_records": records}


def final_assembly_node(state: RiskInventoryState) -> dict[str, Any]:
    if state.get("demo_mode"):
        return {"final_report": load_demo_risk_inventory().model_dump()}
    context = ProcessContext.model_validate(state["input_context"])
    records = [RiskInventoryRecord.model_validate(item) for item in state.get("risk_records", [])]
    summary = ExecutiveSummary(
        headline=f"{context.process_name} risk inventory generated with {len(records)} materialized risk records.",
        key_messages=[
            "Risk inventory records were generated from process context, taxonomy, and controls.",
            "Inherent and residual risk ratings were calculated by deterministic matrices.",
            "Reviewer challenge fields are ready for business validation.",
        ],
        top_residual_risks=[
            f"{record.taxonomy_node.level_2_category}: {record.residual_risk.residual_label}"
            for record in records[:5]
        ],
        recommended_actions=[
            "Review risks without mapped controls.",
            "Validate impact and likelihood rationales with process owners.",
            "Export the workbook for stakeholder review.",
        ],
    )
    loader = MatrixConfigLoader(state.get("config_dir"))
    run = RiskInventoryRun(
        run_id=state.get("run_id", "RI-RUN-001"),
        tenant_id=state.get("tenant_id", ""),
        bank_id=state.get("tenant_id", ""),
        input_context=context,
        records=records,
        executive_summary=summary,
        config_snapshot=loader.config_snapshot(),
        run_manifest={"deterministic": True, "llm_required": False, "record_count": len(records)},
    )
    control_ids = {control.get("control_id", "") for control in state.get("control_inventory", [])}
    findings = RiskInventoryValidator().validate_run(run, control_ids)
    run = run.model_copy(update={"validation_findings": findings})
    return {"final_report": run.model_dump(), "validation_findings": [finding.model_dump() for finding in findings]}


def excel_export_node(state: RiskInventoryState) -> dict[str, Any]:
    report = state.get("final_report")
    if not report or not state.get("export_path"):
        return {}
    run = RiskInventoryRun.model_validate(report)
    path = export_risk_inventory_to_excel(run, state["export_path"])
    return {"export_paths": [str(path)]}


def build_risk_inventory_graph() -> Any:
    """Build the Risk Inventory Builder graph."""
    graph = StateGraph(RiskInventoryState)
    graph.add_node("context_ingestion", context_ingestion_node)
    graph.add_node("taxonomy_applicability", taxonomy_applicability_node)
    graph.add_node("risk_statement_generation", risk_statement_generation_node)
    graph.add_node("exposure_metrics", exposure_metrics_node)
    graph.add_node("impact_assessment", impact_assessment_node)
    graph.add_node("likelihood_assessment", likelihood_assessment_node)
    graph.add_node("inherent_risk_calculator", inherent_risk_calculator_node)
    graph.add_node("control_mapping", control_mapping_node)
    graph.add_node("control_effectiveness", control_effectiveness_node)
    graph.add_node("control_environment_calculator", control_environment_calculator_node)
    graph.add_node("residual_risk_calculator", residual_risk_calculator_node)
    graph.add_node("review_challenge", review_challenge_node)
    graph.add_node("final_assembly", final_assembly_node)
    graph.add_node("excel_export", excel_export_node)

    graph.set_entry_point("context_ingestion")
    graph.add_edge("context_ingestion", "taxonomy_applicability")
    graph.add_edge("taxonomy_applicability", "risk_statement_generation")
    graph.add_edge("risk_statement_generation", "exposure_metrics")
    graph.add_edge("exposure_metrics", "impact_assessment")
    graph.add_edge("impact_assessment", "likelihood_assessment")
    graph.add_edge("likelihood_assessment", "inherent_risk_calculator")
    graph.add_edge("inherent_risk_calculator", "control_mapping")
    graph.add_edge("control_mapping", "control_effectiveness")
    graph.add_edge("control_effectiveness", "control_environment_calculator")
    graph.add_edge("control_environment_calculator", "residual_risk_calculator")
    graph.add_edge("residual_risk_calculator", "review_challenge")
    graph.add_edge("review_challenge", "final_assembly")
    graph.add_edge("final_assembly", "excel_export")
    graph.add_edge("excel_export", END)
    return graph


def load_risk_inventory_taxonomy_node(raw: dict[str, Any]) -> Any:
    from controlnexus.risk_inventory.models import RiskTaxonomyNode

    return RiskTaxonomyNode.model_validate(raw)


def _match_controls(node: Any, controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    common = " ".join(node.common_controls).lower()
    related = {item.lower() for item in node.related_control_types}
    for control in controls:
        text = " ".join(
            [
                str(control.get("control_name", "")),
                str(control.get("name", "")),
                str(control.get("description", "")),
                str(control.get("control_description", "")),
            ]
        ).lower()
        control_type = str(control.get("control_type", "")).lower()
        if control_type in related or any(word in text for word in common.split()[:12]):
            matches.append(control)
    return matches[:4]


def _mapping_from_control(control: dict[str, Any], node: Any) -> ControlMapping:
    name = control.get("control_name") or control.get("name") or control.get("control_id", "Control")
    control_type = control.get("control_type", "")
    description = control.get("description") or control.get("control_description", "")
    design = ControlDesignEffectivenessAssessment(
        rating=ControlEffectivenessRating(control.get("design_rating", "Satisfactory")),
        rationale=f"{name} is designed to address {node.level_2_category}.",
        criteria_results={"mapped_to_root_cause": True},
    )
    operating = ControlOperatingEffectivenessAssessment(
        rating=ControlEffectivenessRating(control.get("operating_rating", "Satisfactory")),
        rationale=f"{name} has operating evidence to be reviewed by the business owner.",
        criteria_results={"evidence_available": bool(description)},
    )
    return ControlMapping(
        control_id=control.get("control_id", name),
        control_name=name,
        control_type=control_type,
        control_description=description,
        mitigation_rationale=f"{name} mitigates {node.level_2_category} based on control type and description matching.",
        mapped_root_causes=normalize_root_cause_names(node.typical_root_causes[:2], node=node, max_items=2),
        coverage_assessment="partial",
        design_effectiveness=design,
        operating_effectiveness=operating,
    )


def _process_specific_risk_statement(
    context: ProcessContext,
    node: Any,
    causes: list[str] | None = None,
) -> str:
    root_cause = (causes or node.typical_root_causes or ["process breakdowns"])[0].lower()
    consequence = _contextual_consequences(context, node)[0].lower()
    product = f" for {context.product}" if context.product else ""
    return (
        f"{context.process_name}{product} may experience {node.level_2_category.lower()} "
        f"if {root_cause} affects the process, resulting in {consequence}."
    )


def _contextual_consequences(context: ProcessContext, node: Any) -> list[str]:
    text = " ".join([context.description, context.product, node.definition]).lower()
    consequences = []
    if any(token in text for token in ("payment", "wire", "customer", "exception")):
        consequences.append("customer impact, delayed payment resolution, or financial loss")
    if any(token in text for token in ("regulatory", "report", "incident", "compliance")):
        consequences.append("regulatory escalation, inaccurate reporting, or compliance breach")
    if any(token in text for token in ("access", "cyber", "data", "unauthorized")):
        consequences.append("unauthorized access, inaccurate data, or loss of confidentiality")
    if any(token in text for token in ("vendor", "third party", "continuity", "outage")):
        consequences.append("service disruption, missed SLAs, or operational resilience impact")
    return consequences or ["financial, customer, regulatory, or operational impact"]


def _metric_value_from_context(metric_name: str, context_description: str) -> str:
    import re

    text = context_description or ""
    lowered = metric_name.lower()
    if any(token in lowered for token in ("volume", "value", "dollar", "amount")):
        match = re.search(r"\$[0-9][0-9,.]*(?:m|mm| million| billion)?", text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    if any(token in lowered for token in ("rate", "breach", "error", "percent")):
        match = re.search(r"\b\d+(?:\.\d+)?%", text)
        if match:
            return match.group(0)
    if any(token in lowered for token in ("count", "exceptions", "cases", "items")):
        match = re.search(r"\b\d+\s+(?:exceptions|payments|cases|items|breaches)\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    if "daily" in text.lower():
        return "Daily exposure indicated in source document"
    return "Not provided"


def _worst(ratings: list[ControlEffectivenessRating]) -> ControlEffectivenessRating:
    if not ratings:
        return ControlEffectivenessRating.INADEQUATE
    rank = {
        ControlEffectivenessRating.STRONG: 1,
        ControlEffectivenessRating.SATISFACTORY: 2,
        ControlEffectivenessRating.IMPROVEMENT_NEEDED: 3,
        ControlEffectivenessRating.INADEQUATE: 4,
    }
    return max(ratings, key=lambda rating: rank[rating])
