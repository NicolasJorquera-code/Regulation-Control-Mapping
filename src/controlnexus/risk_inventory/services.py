"""Service layer for the Risk Inventory Builder flagship workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from controlnexus.risk_inventory.models import (
    AgentTraceEvent,
    ReviewChallengeRecord,
    ReviewDecision,
    RiskControlGap,
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskInventoryWorkspace,
    SyntheticControlRecommendation,
    ValidationFinding,
    ValidationSeverity,
)


def build_synthetic_control_recommendations(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None = None,
) -> list[SyntheticControlRecommendation]:
    """Recommend controls when mapped coverage does not fully defend the risk."""
    gaps = _control_gap_reasons(record)
    if not gaps:
        return list(record.synthetic_control_recommendations)

    existing_types = {mapping.control_type for mapping in record.control_mappings if mapping.control_type}
    recommended_type = _recommended_control_type(record, existing_types)
    owner = _suggested_owner(record, workspace)
    frequency = _suggested_frequency(record)
    root_causes = record.risk_statement.causes or record.taxonomy_node.typical_root_causes[:3]
    evidence = _expected_evidence(recommended_type, record)
    risk_event = (record.risk_statement.risk_event or record.risk_statement.risk_description).rstrip(".")
    consequences = record.risk_statement.consequences[:2]
    primary_causes = root_causes[:3]
    cause_phrase = ", ".join(primary_causes) if primary_causes else record.taxonomy_node.level_2_category.lower()
    consequence_phrase = (
        f" before it leads to {', '.join(consequences).rstrip('.').lower()}"
        if consequences
        else ""
    )

    control_name = _synthetic_control_name(record, recommended_type)
    statement = (
        f"{owner} performs a {frequency.lower()} {recommended_type.lower()} control over {record.process_name} "
        f"to detect and prevent \"{risk_event}\" by monitoring {cause_phrase}, escalating exceptions to risk management, "
        f"and ensuring corrective action is documented{consequence_phrase}."
    )
    if record.control_mappings:
        existing_names = ", ".join(mapping.control_name for mapping in record.control_mappings[:3])
        coverage_phrase = (
            f"Existing controls ({existing_names}) do not fully address {gaps[0]}; this synthetic control closes "
            f"that gap by directly targeting {cause_phrase}."
        )
    else:
        coverage_phrase = (
            f"No controls are currently mapped to this risk, so this synthetic control provides first-line coverage "
            f"of {cause_phrase}."
        )
    rationale = (
        f"Recommended because {gaps[0]}. {coverage_phrase} The control is designed to interrupt the path from "
        f"{cause_phrase} to \"{risk_event}\" and produce audit-ready evidence."
    )
    priority = "High" if record.residual_risk.residual_rating.value in {"High", "Critical"} else "Medium"
    return [
        SyntheticControlRecommendation(
            recommendation_id=f"SYN-{record.risk_id}-001",
            risk_id=record.risk_id,
            control_name=control_name,
            control_type=recommended_type,
            control_statement=statement,
            rationale=rationale,
            addressed_root_causes=primary_causes,
            suggested_owner=owner,
            frequency=frequency,
            expected_evidence=evidence,
            priority=priority,
        )
    ]


def _synthetic_control_name(record: RiskInventoryRecord, control_type: str) -> str:
    """Build a control name that ties back to the specific risk event and process."""
    event = (record.risk_statement.risk_event or record.taxonomy_node.level_2_category).strip().rstrip(".")
    keywords = [token for token in event.split() if len(token) > 3][:4]
    summary = " ".join(keywords).title() if keywords else record.taxonomy_node.level_2_category
    return f"{summary} {control_type}".strip()


def build_control_gaps(record: RiskInventoryRecord) -> list[RiskControlGap]:
    """Return structured control gaps for a risk record."""
    reasons = _control_gap_reasons(record)
    if not reasons:
        return list(record.control_gaps)
    return [
        RiskControlGap(
            gap_id=f"GAP-{record.risk_id}-{idx:02d}",
            risk_id=record.risk_id,
            gap_type=_gap_type(reason),
            severity="High" if record.residual_risk.residual_rating.value in {"High", "Critical"} else "Medium",
            description=reason,
            root_causes=(record.risk_statement.causes or record.taxonomy_node.typical_root_causes)[:3],
            existing_control_ids=[mapping.control_id for mapping in record.control_mappings],
            recommendation=_gap_recommendation(record, reason),
        )
        for idx, reason in enumerate(reasons, start=1)
    ]


def _gap_recommendation(record: RiskInventoryRecord, reason: str) -> str:
    """Recommend how to improve the controls already mapped in the Control Mapping tab."""
    gap_type = _gap_type(reason)
    mappings = record.control_mappings
    risk_event = (record.risk_statement.risk_event or record.risk_statement.risk_description).rstrip(".")

    if not mappings:
        return (
            f"No controls are currently mapped to this risk. Add a preventive control over "
            f"{record.process_name} that directly interrupts \"{risk_event}\" and produces audit-ready evidence."
        )

    primary = mappings[0]
    primary_name = primary.control_name
    other_names = [m.control_name for m in mappings[1:3]]
    others_clause = f" and align it with {', '.join(other_names)}" if other_names else ""

    if gap_type == "Effectiveness Weakness":
        weak = next(
            (
                m
                for m in mappings
                if (m.design_effectiveness and m.design_effectiveness.rating.value in {"Improvement Needed", "Inadequate"})
                or (m.operating_effectiveness and m.operating_effectiveness.rating.value in {"Improvement Needed", "Inadequate"})
            ),
            primary,
        )
        return (
            f"Strengthen {weak.control_name}: tighten its design (defined criteria, sample size, reviewer sign-off) "
            f"and operating cadence so it reliably detects \"{risk_event}\"{others_clause}."
        )
    if gap_type == "Partial Coverage":
        return (
            f"Extend {primary_name} to cover the residual scope (root causes: "
            f"{', '.join((record.risk_statement.causes or record.taxonomy_node.typical_root_causes)[:2]) or 'primary drivers'})"
            f"{others_clause}, or add a complementary control that closes the uncovered path."
        )
    if gap_type == "Outside Appetite":
        return (
            f"Residual risk is outside appetite. Increase the frequency and rigor of {primary_name}"
            f"{others_clause} (e.g. shorter cadence, broader sample, dual review) until residual returns within appetite."
        )
    return (
        f"Add or strengthen controls beyond {primary_name}{others_clause} to bring \"{risk_event}\" within appetite."
    )


def validate_knowledge_pack(workspace: RiskInventoryWorkspace) -> list[ValidationFinding]:
    """Validate cross-references in a loaded knowledge pack."""
    findings: list[ValidationFinding] = []
    process_ids = {process.process_id for process in workspace.processes}
    run_process_ids = {run.input_context.process_id for run in workspace.runs}
    bu_ids = {bu.bu_id for bu in workspace.business_units}
    taxonomy_ids = {node.id for node in workspace.risk_taxonomy_l2}
    control_ids = {control.control_id for control in workspace.control_inventory}

    for bu in workspace.business_units:
        for process_id in bu.process_ids:
            if process_id not in process_ids:
                findings.append(
                    _pack_finding(
                        "business_units",
                        f"Business unit {bu.bu_id} references missing process {process_id}.",
                        "Add the process or remove the stale relationship.",
                    )
                )

    for process in workspace.processes:
        if process.bu_id not in bu_ids:
            findings.append(
                _pack_finding(
                    "processes",
                    f"Process {process.process_id} references unknown business unit {process.bu_id}.",
                    "Map the process to a configured business unit.",
                )
            )
        if process.process_id not in run_process_ids:
            findings.append(
                _pack_finding(
                    "runs",
                    f"Process {process.process_id} has no generated risk inventory run.",
                    "Create a fixture or enable deterministic synthetic run generation.",
                    severity=ValidationSeverity.INFO,
                )
            )

    for kri in workspace.kri_library:
        if kri.risk_taxonomy_id not in taxonomy_ids:
            findings.append(
                _pack_finding(
                    "kri_library",
                    f"KRI {kri.kri_id} references unknown risk taxonomy node {kri.risk_taxonomy_id}.",
                    "Update the KRI taxonomy mapping.",
                )
            )

    for artifact in workspace.evidence_artifacts:
        if artifact.control_id and artifact.control_id not in control_ids:
            findings.append(
                _pack_finding(
                    "evidence_artifacts",
                    f"Evidence {artifact.evidence_id} references unknown control {artifact.control_id}.",
                    "Map the evidence to a configured control.",
                    severity=ValidationSeverity.INFO,
                )
            )

    return findings


def run_risk_inventory_workflow(
    workspace: RiskInventoryWorkspace,
    scope: dict[str, Any] | None = None,
    *,
    llm_enabled: bool = False,
) -> RiskInventoryRun:
    """Return a workflow-ready run for a process scope with trace metadata."""
    scope = scope or {}
    process_id = str(scope.get("process_id") or scope.get("procedure_id") or "")
    run = workspace.run_for_process(process_id) if process_id else (workspace.runs[0] if workspace.runs else None)
    if run is None:
        raise ValueError(f"No risk inventory run found for process scope: {process_id or '<default>'}")
    mode = "live_llm" if llm_enabled else "deterministic_fallback"
    events = [event.model_dump() for event in default_agent_trace_events(run, mode=mode)]
    return run.model_copy(update={"events": events})


def default_agent_trace_events(run: RiskInventoryRun, *, mode: str = "deterministic_fallback") -> list[AgentTraceEvent]:
    """Build a visible, repeatable agent trace for a completed run."""
    record_count = len(run.records)
    control_count = sum(len(record.control_mappings) for record in run.records)
    return [
        AgentTraceEvent(
            stage="Data Intake and Knowledge Pack Validation",
            agent="KnowledgePackValidator",
            mode=mode,
            summary=f"Loaded {run.input_context.process_name} with {record_count} risk records.",
            inputs_used=run.input_context.source_documents,
            output_refs=[run.run_id],
        ),
        AgentTraceEvent(
            stage="Taxonomy Applicability",
            agent="TaxonomyApplicabilityAgent",
            mode=mode,
            summary="Selected materialized risk taxonomy nodes from process context and configured patterns.",
            inputs_used=["risk_taxonomy_l2", "process_context"],
            output_refs=[record.taxonomy_node.id for record in run.records],
        ),
        AgentTraceEvent(
            stage="Risk Statement Generation",
            agent="RiskStatementAgent",
            mode=mode,
            summary="Generated executive risk statements with root-cause wording.",
            inputs_used=["risk_taxonomy_l2", "root_cause_taxonomy", "process_context"],
            output_refs=[record.risk_id for record in run.records],
        ),
        AgentTraceEvent(
            stage="Control Coverage Mapping",
            agent="ControlCoverageAgent",
            mode=mode,
            summary=f"Mapped {control_count} existing controls and identified coverage gaps.",
            inputs_used=["control_inventory", "risk_statements"],
            tools_called=["control_inventory_search"],
            output_refs=[record.risk_id for record in run.records if record.coverage_gaps],
        ),
        AgentTraceEvent(
            stage="Residual Risk Calculation",
            agent="ResidualRiskCalculator",
            mode="deterministic_fallback",
            summary="Calculated residual risk from matrix-controlled inherent risk and control environment ratings.",
            inputs_used=["inherent_risk_matrix", "residual_risk_matrix", "management_response_rules"],
        ),
        AgentTraceEvent(
            stage="Review and Executive Synthesis",
            agent="ExecutiveSynthesisAgent",
            mode=mode,
            summary="Prepared review/challenge fields, recommended actions, and executive workbook outputs.",
            inputs_used=["review_challenge_config", "validation_findings"],
            validation_findings=[finding.message for finding in run.validation_findings],
        ),
    ]


def apply_review_decisions(
    run: RiskInventoryRun,
    decisions: list[ReviewDecision] | list[dict[str, Any]],
) -> RiskInventoryRun:
    """Return a copy of *run* with session-state HITL decisions applied."""
    decision_by_risk = {
        decision.risk_id: decision
        for decision in [
            item if isinstance(item, ReviewDecision) else ReviewDecision.model_validate(item)
            for item in decisions
        ]
    }
    if not decision_by_risk:
        return run

    updated_records: list[RiskInventoryRecord] = []
    for record in run.records:
        decision = decision_by_risk.get(record.risk_id)
        if not decision:
            updated_records.append(record)
            continue
        existing = record.review_challenges[0] if record.review_challenges else ReviewChallengeRecord()
        updated_review = existing.model_copy(
            update={
                "reviewer": decision.reviewer or existing.reviewer,
                "review_status": decision.review_status,
                "approval_status": decision.approval_status,
                "challenge_comments": decision.challenge_comments,
                "reviewer_adjusted_value": decision.reviewer_adjusted_value,
                "reviewer_rationale": decision.reviewer_rationale,
                "final_approved_value": decision.final_approved_value,
                "approval_timestamp": decision.decided_at,
            }
        )
        updated_records.append(record.model_copy(update={"review_challenges": [updated_review]}))
    return run.model_copy(update={"records": updated_records})


def _control_gap_reasons(record: RiskInventoryRecord) -> list[str]:
    reasons: list[str] = []
    if not record.control_mappings:
        reasons.append("no existing controls are mapped to this materialized risk")
    if record.coverage_gaps:
        reasons.extend(gap for gap in record.coverage_gaps if "root cause" not in gap.lower())
    weak_mappings = [
        mapping
        for mapping in record.control_mappings
        if mapping.coverage_assessment.lower() in {"partial", "weak", "none"}
    ]
    if weak_mappings:
        reasons.append("mapped controls provide only partial or weak coverage")
    ineffective = [
        mapping
        for mapping in record.control_mappings
        if (
            mapping.design_effectiveness
            and mapping.design_effectiveness.rating.value in {"Improvement Needed", "Inadequate"}
        )
        or (
            mapping.operating_effectiveness
            and mapping.operating_effectiveness.rating.value in {"Improvement Needed", "Inadequate"}
        )
    ]
    if ineffective:
        reasons.append("design or operating effectiveness is below satisfactory")
    if record.risk_appetite and record.risk_appetite.status == "outside":
        reasons.append("residual risk is outside appetite")
    if record.residual_risk.residual_rating.value in {"High", "Critical"}:
        reasons.append("residual risk remains high enough to require management action")
    return list(dict.fromkeys(reasons))


def _recommended_control_type(record: RiskInventoryRecord, existing_types: set[str]) -> str:
    related = [item for item in record.taxonomy_node.related_control_types if item not in existing_types]
    if related:
        return related[0]
    if "Data" in record.taxonomy_node.level_2_category:
        return "Reconciliation"
    if "Cyber" in record.taxonomy_node.level_2_category or "Privacy" in record.taxonomy_node.level_2_category:
        return "System and Application Restrictions"
    if "Third Party" in record.taxonomy_node.level_2_category:
        return "Third Party Due Diligence"
    return "Risk and Compliance Assessments"


def _suggested_owner(record: RiskInventoryRecord, workspace: RiskInventoryWorkspace | None) -> str:
    if workspace:
        process = next((p for p in workspace.processes if p.process_id == record.process_id), None)
        if process and process.owner:
            return process.owner
    return record.residual_risk.management_response.owner or "Business Process Owner"


def _suggested_frequency(record: RiskInventoryRecord) -> str:
    if record.residual_risk.residual_rating.value in {"High", "Critical"}:
        return "Weekly"
    if record.inherent_risk.inherent_rating.value in {"High", "Critical"}:
        return "Monthly"
    return "Quarterly"


def _expected_evidence(control_type: str, record: RiskInventoryRecord) -> str:
    if control_type == "Reconciliation":
        return "Signed reconciliation report with exceptions, preparer, approver, and retention location."
    if "Application Restrictions" in control_type:
        return "Access review extract, exception disposition, owner sign-off, and IAM ticket evidence."
    if control_type == "Third Party Due Diligence":
        return "Vendor review package with SLA dashboard, SOC review, issue log, and approval evidence."
    return f"{record.taxonomy_node.level_2_category} assessment with owner sign-off and evidence retained in the GRC platform."


def _gap_type(reason: str) -> str:
    lowered = reason.lower()
    if "no existing" in lowered:
        return "Missing Control"
    if "effectiveness" in lowered:
        return "Effectiveness Weakness"
    if "appetite" in lowered:
        return "Outside Appetite"
    return "Partial Coverage"


def _pack_finding(
    field_name: str,
    message: str,
    recommendation: str,
    *,
    severity: ValidationSeverity = ValidationSeverity.WARNING,
) -> ValidationFinding:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return ValidationFinding(
        finding_id=f"PACK-{field_name}-{stamp}",
        severity=severity,
        field_name=field_name,
        message=message,
        recommendation=recommendation,
    )
