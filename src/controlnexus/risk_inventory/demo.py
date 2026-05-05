"""Deterministic demo data loader for Risk Inventory Builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from controlnexus.risk_inventory.calculators import (
    ControlEnvironmentCalculator,
    InherentRiskCalculator,
    ResidualRiskCalculator,
)
from controlnexus.risk_inventory.config import MatrixConfigLoader, read_yaml, resolve_project_root
from controlnexus.risk_inventory.models import (
    ActionItem,
    AgentTraceEvent,
    ApprovalStatus,
    BusinessUnit,
    ControlInventoryEntry,
    ControlDesignEffectivenessAssessment,
    ControlEffectivenessRating,
    ControlMapping,
    ControlOperatingEffectivenessAssessment,
    ControlTaxonomyEntry,
    EvidenceArtifact,
    EvidenceQuality,
    EvidenceReference,
    ExecutiveSummary,
    ExposureMetric,
    ImpactAssessment,
    ImpactDimension,
    ImpactDimensionAssessment,
    ImpactScore,
    KRIDefinition,
    KRIThreshold,
    LikelihoodAssessment,
    LikelihoodScore,
    MaterializationType,
    OpenIssue,
    IssueRecord,
    Process,
    ProcessContext,
    RegulatoryObligation,
    ReviewChallengeRecord,
    ReviewStatus,
    RiskAppetite,
    RiskApplicabilityAssessment,
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskInventoryWorkspace,
    RiskStatement,
    RiskTaxonomyLevel1,
    RootCauseTaxonomyEntry,
)
from controlnexus.risk_inventory.taxonomy import find_applicable_nodes, load_risk_inventory_taxonomy
from controlnexus.risk_inventory.validator import RiskInventoryValidator


DEFAULT_DEMO_BUSINESS_UNIT_ID = "BU-PAYOPS"
DEFAULT_DEMO_PROCESS_ID = "PROC-PAY-EXCEPTION"


def default_demo_fixture_path() -> Path:
    return resolve_project_root() / "sample_data" / "risk_inventory_demo" / "payment_exception_handling.yaml"


def load_demo_risk_inventory(path: Path | str | None = None) -> RiskInventoryRun:
    """Load the deterministic Payment Exception Handling demo run."""
    fixture_path = Path(path) if path else default_demo_fixture_path()
    payload = read_yaml(fixture_path)
    scenario = payload["scenario"]
    controls = {control["control_id"]: control for control in payload.get("controls", [])}
    taxonomy = {node.id: node for node in load_risk_inventory_taxonomy()}

    loader = MatrixConfigLoader()
    inherent_calc = InherentRiskCalculator(loader.inherent_matrix())
    env_calc = ControlEnvironmentCalculator()
    residual_calc = ResidualRiskCalculator(loader.residual_matrix(), loader.management_response_rules())

    source_documents = [f"risk inventory fixture: {fixture_path.name}"]
    source_documents.extend(_scenario_source_documents(payload))
    context = ProcessContext(
        process_id=scenario["process_id"],
        process_name=scenario["process_name"],
        product=scenario["product"],
        business_unit=scenario["business_unit"],
        description=scenario["description"],
        systems=scenario.get("systems", []),
        stakeholders=scenario.get("stakeholders", []),
        source_documents=source_documents,
    )

    records: list[RiskInventoryRecord] = []
    for idx, spec in enumerate(payload.get("risks", []), start=1):
        node = taxonomy[spec["taxonomy_node_id"]]
        impact_rationales = spec.get("impact_rationales", {})
        dimensions = [
            ImpactDimensionAssessment(
                dimension=ImpactDimension(dimension),
                score=ImpactScore(score),
                rationale=impact_rationales.get(dimension)
                or _impact_rationale(node.level_2_category, dimension, score),
            )
            for dimension, score in spec["impact_scores"].items()
        ]
        impact = ImpactAssessment(
            dimensions=dimensions,
            overall_impact_score=ImpactScore(spec["overall_impact_score"]),
            overall_impact_rationale=spec.get(
                "overall_impact_rationale",
                (
                    f"{node.level_2_category} creates material exposure for {context.process_name} "
                    f"because payment volume, customer impact, and regulatory expectations make the highest "
                    f"dimension score relevant to the overall rating."
                ),
            ),
        )
        likelihood = LikelihoodAssessment(
            likelihood_score=LikelihoodScore(spec["likelihood_score"]),
            likelihood_rating=spec.get("likelihood_rating") or _likelihood_label(spec["likelihood_score"]),
            rationale=spec.get(
                "likelihood_rationale",
                (
                    f"Likelihood reflects daily payment exception volume, recurring queue activity, "
                    f"documented exposure metrics, and plausible event drivers in {context.process_name}."
                ),
            ),
            assumptions=spec.get(
                "assumptions",
                [
                    "Exception queues operate daily.",
                    "High-value payment items require same-day or next-day resolution.",
                ],
            ),
        )
        inherent = inherent_calc.calculate(
            impact.overall_impact_score,
            likelihood.likelihood_score,
            rationale=f"Calculated from the configured inherent risk matrix for {impact.overall_impact_score} impact and {likelihood.likelihood_score} likelihood.",
        )
        mappings = [
            _build_control_mapping(controls[control_id], node)
            for control_id in spec.get("mapped_controls", [])
            if control_id in controls
        ]
        design_rating = _aggregate_design_rating(mappings)
        operating_rating = _aggregate_operating_rating(mappings)
        environment = env_calc.calculate(
            design_rating,
            operating_rating,
            rationale=_control_environment_rationale(mappings, design_rating, operating_rating),
        )
        residual = residual_calc.calculate(
            inherent,
            environment,
            rationale=_residual_rationale(
                inherent.inherent_label,
                environment.control_environment_rating.value,
                spec.get("recommended_action", ""),
            ),
            recommended_action=spec.get("recommended_action", ""),
        )
        evidence_references = [
            EvidenceReference(
                evidence_id=reference.get("evidence_id", f"EVID-{idx:03d}"),
                evidence_type=reference.get("evidence_type", "Demo source"),
                description=reference.get("description", ""),
                source=reference.get("source", f"sample_data/risk_inventory_demo/{fixture_path.name}"),
            )
            for reference in spec.get("evidence_references", [])
        ] or [
            EvidenceReference(
                evidence_id=f"EVID-{idx:03d}",
                evidence_type="Demo source",
                description=f"Demo process narrative and mapped control evidence for {node.level_2_category}.",
                source=f"sample_data/risk_inventory_demo/{fixture_path.name}",
            )
        ]
        review = spec.get("review", {})
        appetite_payload = spec.get("risk_appetite")
        risk_appetite = (
            RiskAppetite(
                threshold=appetite_payload.get("threshold", "Medium"),
                statement=appetite_payload.get("statement", ""),
                status=appetite_payload.get("status", "within"),
                category=appetite_payload.get("category", ""),
            )
            if isinstance(appetite_payload, dict)
            else None
        )
        action_plan = [
            ActionItem(
                action=item.get("action", ""),
                owner=item.get("owner", ""),
                due_date=item.get("due_date", ""),
                status=item.get("status", "Planned"),
                priority=item.get("priority", "Medium"),
            )
            for item in spec.get("action_plan", [])
        ]
        coverage_gaps = list(spec.get("coverage_gaps", []))
        review_status_value = review.get("review_status", ReviewStatus.PENDING_REVIEW.value)
        approval_status_value = review.get("approval_status", ApprovalStatus.DRAFT.value)
        try:
            review_status_enum = ReviewStatus(review_status_value)
        except ValueError:
            review_status_enum = ReviewStatus.PENDING_REVIEW
        try:
            approval_status_enum = ApprovalStatus(approval_status_value)
        except ValueError:
            approval_status_enum = ApprovalStatus.DRAFT
        record = RiskInventoryRecord(
            risk_id=spec["risk_id"],
            process_id=context.process_id,
            process_name=context.process_name,
            product=context.product,
            taxonomy_node=node,
            applicability=RiskApplicabilityAssessment(
                materializes=True,
                materialization_type=MaterializationType.PROCESS_SPECIFIC,
                rationale=spec.get(
                    "applicability_rationale",
                    (
                        f"{node.level_2_category} materializes because {context.process_name.lower()} "
                        f"includes {', '.join(node.applicable_process_patterns[:3])} activities and depends on timely, controlled execution."
                    ),
                ),
                confidence=float(spec.get("confidence", 0.86)),
                evidence_refs=evidence_references,
            ),
            risk_statement=RiskStatement(
                risk_description=(spec.get("risk_description") or _risk_description(node, context)).strip(),
                risk_event=spec.get("risk_event")
                or (node.example_risk_statements[0] if node.example_risk_statements else _risk_description(node, context)),
                causes=spec.get("causes") or node.typical_root_causes[:3],
                consequences=spec.get("consequences")
                or [
                    "financial loss or rework",
                    "customer or counterparty impact",
                    "regulatory or management escalation",
                ],
                affected_stakeholders=spec.get("affected_stakeholders") or context.stakeholders,
            ),
            exposure_metrics=_build_exposure_metrics(spec, node, idx),
            impact_assessment=impact,
            likelihood_assessment=likelihood,
            inherent_risk=inherent,
            control_mappings=mappings,
            control_environment=environment,
            residual_risk=residual,
            review_challenges=[
                ReviewChallengeRecord(
                    review_status=review_status_enum,
                    reviewer=review.get("reviewer", "Business process owner"),
                    challenge_comments=review.get("challenge_comments", spec.get("review_comment", "")),
                    challenged_fields=review.get(
                        "challenged_fields",
                        ["applicability", "impact_scores", "control_mapping"],
                    ),
                    ai_original_value=_review_value(review.get("ai_original_value", "")),
                    reviewer_adjusted_value=_review_value(review.get("reviewer_adjusted_value", "")),
                    reviewer_rationale=review.get("reviewer_rationale", ""),
                    approval_status=approval_status_enum,
                )
            ],
            evidence_references=evidence_references,
            risk_appetite=risk_appetite,
            action_plan=action_plan,
            coverage_gaps=coverage_gaps,
            demo_record=True,
        )
        records.append(record)

    summary_payload = payload.get("executive_summary", {})
    summary = ExecutiveSummary(
        headline=summary_payload.get(
            "headline",
            (
                "Payment Exception Handling has a complete demo risk inventory with mapped controls, "
                "matrix-calculated inherent and residual risk, and review-ready management actions."
            ),
        ),
        key_messages=summary_payload.get(
            "key_messages",
            [
                "Six material risks were identified for high-value payment exception handling.",
                "Cybersecurity and regulatory reporting risks require focused review because control evidence or operating consistency is not yet strong.",
                "Residual risk is calculated deterministically and can be challenged by business reviewers.",
            ],
        ),
        top_residual_risks=summary_payload.get("top_residual_risks")
        or [
            f"{record.taxonomy_node.level_2_category}: {record.residual_risk.residual_label}"
            for record in records
            if record.residual_risk.residual_rating.value in {"Medium", "High", "Critical"}
        ],
        recommended_actions=summary_payload.get(
            "recommended_actions",
            [
                "Validate privileged access review frequency for payment exception queues.",
                "Confirm incident reportability thresholds with Compliance.",
                "Collect vendor SLA and SOC evidence for third-party payment support.",
            ],
        ),
    )
    run = RiskInventoryRun(
        run_id=scenario["run_id"],
        tenant_id=scenario["tenant_id"],
        bank_id=scenario["tenant_id"],
        input_context=context,
        records=records,
        executive_summary=summary,
        config_snapshot={
            **loader.config_snapshot(),
            "risk_appetite_framework": payload.get("risk_appetite_framework", {}),
        },
        run_manifest={
            "fixture": str(fixture_path),
            "deterministic": True,
            "llm_required": False,
            "record_count": len(records),
            "evidence_metric_count": sum(len(record.exposure_metrics) for record in records),
            "scenario_basis": payload.get("scenario_basis", []),
        },
        demo_mode=True,
    )
    findings = RiskInventoryValidator(inherent_calc, residual_calc).validate_run(run, set(controls))
    return run.model_copy(update={"validation_findings": findings})


def _risk_description(node: Any, context: ProcessContext) -> str:
    return (
        f"{node.level_2_category} in {context.process_name} may result in {node.definition[0].lower()}"
        f"{node.definition[1:] if len(node.definition) > 1 else ''}"
    )


def _review_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value in (None, ""):
        return ""
    return str(value)


def _scenario_source_documents(payload: dict[str, Any]) -> list[str]:
    documents: list[str] = []
    for source in payload.get("scenario_basis", []):
        if not isinstance(source, dict):
            continue
        title = str(source.get("title", "")).strip()
        url = str(source.get("url", "")).strip()
        if title and url:
            documents.append(f"{title}: {url}")
        elif title:
            documents.append(title)
        elif url:
            documents.append(url)
    return documents


def _control_environment_rationale(
    mappings: list[ControlMapping],
    design_rating: ControlEffectivenessRating,
    operating_rating: ControlEffectivenessRating,
) -> str:
    """Summarize the control environment in reviewer-ready language."""
    partial_controls = [
        mapping.control_name
        for mapping in mappings
        if mapping.coverage_assessment.lower() not in {"full", "strong"}
    ]
    issue_count = sum(len(mapping.open_issues) for mapping in mappings)
    evidence_exceptions = sum(
        int(mapping.evidence_quality.exceptions_noted)
        for mapping in mappings
        if mapping.evidence_quality
    )
    binding_limit = (
        f" Binding limitations remain in {', '.join(partial_controls[:2])}."
        if partial_controls
        else ""
    )
    issue_parts = []
    if issue_count:
        issue_parts.append(_count_phrase(issue_count, "open issue"))
    if evidence_exceptions:
        issue_parts.append(_count_phrase(evidence_exceptions, "testing exception"))
    issue_note = (
        f" Current-period evidence includes {_join_phrase(issue_parts)}."
        if issue_parts
        else " Current-period evidence does not show open control issues for the mapped controls."
    )
    return (
        f"The control environment is {_worse_control_rating(design_rating, operating_rating).value}. "
        f"Design is {design_rating.value} and operating evidence is {operating_rating.value}."
        f"{binding_limit}{issue_note}"
    )


def _residual_rationale(
    inherent_label: str,
    control_environment: str,
    recommended_action: str,
) -> str:
    action = recommended_action.strip().rstrip(".")
    action_note = f" Priority remediation is to {action[0].lower() + action[1:]}." if action else ""
    article = "an" if control_environment[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    return (
        f"Residual exposure remains after applying {article} {control_environment} control environment to {inherent_label} "
        f"inherent risk.{action_note}"
    )


def _worse_control_rating(
    first: ControlEffectivenessRating,
    second: ControlEffectivenessRating,
) -> ControlEffectivenessRating:
    return max([first, second], key=_control_rating_rank)


def _control_rating_rank(rating: ControlEffectivenessRating) -> int:
    return {
        ControlEffectivenessRating.STRONG: 1,
        ControlEffectivenessRating.SATISFACTORY: 2,
        ControlEffectivenessRating.IMPROVEMENT_NEEDED: 3,
        ControlEffectivenessRating.INADEQUATE: 4,
    }[rating]


def _count_phrase(count: int, noun: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"


def _join_phrase(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


def _build_exposure_metrics(spec: dict[str, Any], node: Any, idx: int) -> list[ExposureMetric]:
    metrics = spec.get("exposure_metrics")
    if metrics:
        metric_models: list[ExposureMetric] = []
        for metric in metrics:
            supports = metric.get("supports", ["likelihood", "impact"])
            if isinstance(supports, str):
                supports = [supports]
            metric_models.append(
                ExposureMetric(
                    metric_name=metric.get("metric_name", ""),
                    metric_value=str(metric.get("metric_value", "")),
                    metric_unit=metric.get("metric_unit", ""),
                    description=metric.get("description", ""),
                    source=metric.get("source", "Payment Exception Workflow"),
                    supports=supports,
                )
            )
        return metric_models

    return [
        ExposureMetric(
            metric_name=metric,
            metric_value=_demo_metric_value(metric, idx),
            metric_unit="demo",
            description=f"Demo exposure metric supporting {node.level_2_category}.",
            source="Payment Exception Workflow",
            supports=["likelihood", "impact"],
        )
        for metric in node.common_exposure_metrics[:4]
    ]


def _build_control_mapping(control: dict[str, Any], node: Any) -> ControlMapping:
    design_rating = ControlEffectivenessRating(control.get("design_rating", "Satisfactory"))
    operating_rating = ControlEffectivenessRating(control.get("operating_rating", "Satisfactory"))
    risk_mitigations = control.get("risk_mitigations", {})
    coverage_by_risk = control.get("coverage_by_risk", {})
    evidence_gaps = list(control.get("evidence_gaps", []))
    design = ControlDesignEffectivenessAssessment(
        rating=design_rating,
        rationale=control.get("design_rationale")
        or f"{control['control_name']} is designed to address {node.level_2_category} through {control['control_type']} activity.",
        criteria_results=control.get(
            "design_criteria_results",
            {"mapped_to_root_cause": True, "formalized": True, "sufficient_frequency": True},
        ),
        evidence_gaps=evidence_gaps if design_rating == ControlEffectivenessRating.IMPROVEMENT_NEEDED else [],
    )
    operating = ControlOperatingEffectivenessAssessment(
        rating=operating_rating,
        rationale=control.get("operating_rationale")
        or f"Demo operating assessment is based on available sample evidence for {control['control_name']}.",
        criteria_results=control.get(
            "operating_criteria_results",
            {"operated_consistently": operating_rating != ControlEffectivenessRating.IMPROVEMENT_NEEDED, "evidence_available": True},
        ),
        evidence_gaps=evidence_gaps if operating_rating == ControlEffectivenessRating.IMPROVEMENT_NEEDED else [],
    )
    open_issues = [
        OpenIssue(
            issue_id=issue.get("issue_id", ""),
            description=issue.get("description", ""),
            severity=issue.get("severity", "Medium"),
            age_days=int(issue.get("age_days", 0)),
            owner=issue.get("owner", ""),
            status=issue.get("status", "Open"),
        )
        for issue in control.get("open_issues", [])
    ]
    eq = control.get("evidence_quality")
    evidence_quality = (
        EvidenceQuality(
            rating=eq.get("rating", "Adequate"),
            last_tested=eq.get("last_tested", ""),
            sample_size=int(eq.get("sample_size", 0)),
            exceptions_noted=int(eq.get("exceptions_noted", 0)),
            notes=eq.get("notes", ""),
        )
        if isinstance(eq, dict)
        else None
    )
    mapped_root_causes = control.get("mapped_root_causes_per_risk", {}).get(
        node.id, node.typical_root_causes[:2]
    )
    return ControlMapping(
        control_id=control["control_id"],
        control_name=control["control_name"],
        control_type=control["control_type"],
        control_description=control["description"],
        mitigation_rationale=risk_mitigations.get(
            node.id,
            (
                f"{control['control_name']} mitigates {node.level_2_category} by addressing "
                f"{', '.join(node.typical_root_causes[:2]) or 'key process drivers'}."
            ),
        ),
        mapped_root_causes=mapped_root_causes,
        coverage_assessment=coverage_by_risk.get(
            node.id,
            "strong" if design.rating == ControlEffectivenessRating.STRONG else "partial",
        ),
        design_effectiveness=design,
        operating_effectiveness=operating,
        open_issues=open_issues,
        evidence_quality=evidence_quality,
    )


def _aggregate_design_rating(mappings: list[ControlMapping]) -> ControlEffectivenessRating:
    ratings = [m.design_effectiveness.rating for m in mappings if m.design_effectiveness]
    return _worst_rating(ratings or [ControlEffectivenessRating.SATISFACTORY])


def _aggregate_operating_rating(mappings: list[ControlMapping]) -> ControlEffectivenessRating:
    ratings = [m.operating_effectiveness.rating for m in mappings if m.operating_effectiveness]
    return _worst_rating(ratings or [ControlEffectivenessRating.SATISFACTORY])


def _worst_rating(ratings: list[ControlEffectivenessRating]) -> ControlEffectivenessRating:
    rank = {
        ControlEffectivenessRating.STRONG: 1,
        ControlEffectivenessRating.SATISFACTORY: 2,
        ControlEffectivenessRating.IMPROVEMENT_NEEDED: 3,
        ControlEffectivenessRating.INADEQUATE: 4,
    }
    return max(ratings, key=lambda rating: rank[rating])


def _impact_rationale(category: str, dimension: str, score: int) -> str:
    label = dimension.replace("_", " ")
    return f"{category} has a {score} score for {label} based on the payment exception exposure profile."


def _likelihood_label(score: int) -> str:
    return {1: "Low", 2: "Medium Low", 3: "Medium High", 4: "High"}[score]


def _demo_metric_value(metric: str, idx: int) -> str:
    lowered = metric.lower()
    if "count" in lowered:
        return str(20 + idx * 7)
    if "rate" in lowered or "breach" in lowered:
        return f"{2 + idx}%"
    if "dollar" in lowered or "volume" in lowered:
        return f"${idx * 4.5:.1f}M"
    return "Available in demo workflow"


# ---------------------------------------------------------------------------
# Workspace loader (single-process default demo, broader fixtures explicit)
# ---------------------------------------------------------------------------


def default_workspace_fixture_path() -> Path:
    return resolve_project_root() / "sample_data" / "risk_inventory_demo" / "workspace.yaml"


def load_knowledge_pack(path: Path | str | None = None) -> RiskInventoryWorkspace:
    """Load a modular Risk Inventory knowledge pack.

    ``path`` can point to a workspace YAML file or to a directory containing
    ``workspace.yaml`` plus optional modular sidecar files referenced by
    ``knowledge_pack.files``.
    """
    fixture_path = Path(path) if path else default_workspace_fixture_path()
    if fixture_path.is_dir():
        fixture_path = fixture_path / "workspace.yaml"
    payload = _load_workspace_payload(fixture_path)
    if path is None:
        payload = _default_single_process_demo_payload(payload)
    return _build_workspace_from_payload(fixture_path, payload)


def load_demo_workspace(path: Path | str | None = None) -> RiskInventoryWorkspace:
    """Load the default single-process demo workspace, or an explicit workspace fixture."""
    return load_knowledge_pack(path)


def _default_single_process_demo_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Narrow the broad source pack to the default one-process executive demo."""
    narrowed = dict(payload)
    bank = dict(narrowed.get("bank", {}))
    bank.update(
        {
            "bank_id": "FS-PAYMENT-EXCEPTION-2026Q2",
            "bank_name": "Enterprise Payment Operations",
            "description": (
                "Single-process payment-operations inventory based on public erroneous "
                "wire-transfer lessons and payment-system supervisory guidance."
            ),
        }
    )
    narrowed["bank"] = bank
    narrowed["workspace_id"] = "WS-PAYMENT-EXCEPTION-2026Q2"
    narrowed["business_unit_ids"] = [DEFAULT_DEMO_BUSINESS_UNIT_ID]
    narrowed["process_ids"] = [DEFAULT_DEMO_PROCESS_ID]
    narrowed["_business_unit_filter"] = {DEFAULT_DEMO_BUSINESS_UNIT_ID}
    narrowed["_process_filter"] = {DEFAULT_DEMO_PROCESS_ID}
    narrowed["auto_generate_missing_runs"] = False
    manifest = dict(narrowed.get("knowledge_pack", {}))
    manifest["description"] = "Single-process payment exception risk inventory."
    narrowed["knowledge_pack"] = manifest
    return narrowed


def _load_workspace_payload(fixture_path: Path) -> dict[str, Any]:
    payload = read_yaml(fixture_path)
    business_unit_filter = payload.get("business_unit_ids")
    process_filter = payload.get("process_ids")
    if business_unit_filter is None and _is_identifier_list(payload.get("business_units")):
        business_unit_filter = list(payload.get("business_units", []))
    if process_filter is None and _is_identifier_list(payload.get("processes")):
        process_filter = list(payload.get("processes", []))

    manifest = payload.get("knowledge_pack", {})
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    for key, relative_path in files.items():
        if not relative_path:
            continue
        sidecar = read_yaml(fixture_path.parent / relative_path)
        if key in {"business_units", "processes", "procedures", "run_fixtures", "kri_library"}:
            payload[key] = sidecar.get(key, sidecar.get("records", []))
        else:
            payload[key] = sidecar.get(key, sidecar.get("records", sidecar))
    if business_unit_filter:
        payload["_business_unit_filter"] = set(str(item) for item in business_unit_filter)
    if process_filter:
        payload["_process_filter"] = set(str(item) for item in process_filter)
    return payload


def _is_identifier_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _build_workspace_from_payload(fixture_path: Path, payload: dict[str, Any]) -> RiskInventoryWorkspace:
    bank = payload.get("bank", {})
    business_unit_filter = payload.get("_business_unit_filter")
    process_filter = payload.get("_process_filter")
    bus = [BusinessUnit.model_validate(item) for item in payload.get("business_units", [])]
    if business_unit_filter:
        bus = [bu for bu in bus if bu.bu_id in business_unit_filter]
    active_bu_ids = {bu.bu_id for bu in bus}
    processes = [
        Process.model_validate(item)
        for item in payload.get("processes", payload.get("procedures", []))
    ]
    if active_bu_ids:
        processes = [process for process in processes if process.bu_id in active_bu_ids]
    if process_filter:
        processes = [process for process in processes if process.process_id in process_filter]
    active_process_ids = {process.process_id for process in processes}
    if active_process_ids:
        bus = [
            bu.model_copy(
                update={
                    "process_ids": [process_id for process_id in bu.process_ids if process_id in active_process_ids],
                    "procedure_ids": [
                        process_id for process_id in bu.procedure_ids if process_id in active_process_ids
                    ],
                }
            )
            for bu in bus
        ]
    risk_l1 = [RiskTaxonomyLevel1.model_validate(item) for item in payload.get("risk_taxonomy_l1", [])]
    control_tax = [ControlTaxonomyEntry.model_validate(item) for item in payload.get("control_taxonomy", [])]
    root_cause_tax = [RootCauseTaxonomyEntry.model_validate(item) for item in payload.get("root_cause_taxonomy", [])]
    issues = [
        IssueRecord.model_validate(_normalize_issue_record(item))
        for item in payload.get("issues", [])
        if not active_process_ids or item.get("process_id", "") in active_process_ids
    ]
    obligations = [
        RegulatoryObligation.model_validate(_normalize_obligation_record(item))
        for item in payload.get("regulatory_obligations", [])
        if not active_process_ids or active_process_ids.intersection(set(item.get("process_ids", [])))
    ]
    evidence_artifacts = [
        EvidenceArtifact.model_validate(_normalize_evidence_record(item))
        for item in payload.get("evidence_artifacts", [])
        if not active_process_ids or item.get("process_id", "") in active_process_ids
    ]

    kris: list[KRIDefinition] = []
    for item in payload.get("kri_library", []):
        item = _normalize_kri_record(item)
        thresholds = item.get("thresholds", {})
        kris.append(
            KRIDefinition(
                kri_id=item["kri_id"],
                kri_name=item["kri_name"],
                risk_taxonomy_id=item["risk_taxonomy_id"],
                metric_definition=item.get("metric_definition", ""),
                formula=item.get("formula", ""),
                unit=item.get("unit", ""),
                measurement_frequency=item.get("measurement_frequency", "Monthly"),
                data_source=item.get("data_source", ""),
                owner=item.get("owner", ""),
                thresholds=KRIThreshold(
                    green=thresholds.get("green", ""),
                    amber=thresholds.get("amber", ""),
                    red=thresholds.get("red", ""),
                ),
                rationale=item.get("rationale", ""),
                escalation_path=item.get("escalation_path", ""),
                use_cases=list(item.get("use_cases", [])),
                placement_guidance=item.get("placement_guidance", ""),
            )
        )

    runs: list[RiskInventoryRun] = []
    aggregated_controls: dict[str, dict[str, Any]] = {}
    for entry in payload.get("run_fixtures", []):
        run_path = _run_fixture_path(fixture_path.parent, entry)
        run = load_demo_risk_inventory(run_path)
        if active_process_ids and run.input_context.process_id not in active_process_ids:
            continue
        runs.append(run)
        # also collect controls for the bank-wide knowledge-base view
        run_payload = read_yaml(run_path)
        for control in run_payload.get("controls", []):
            aggregated_controls.setdefault(control["control_id"], control)

    # taxonomy L2 nodes (loaded once)
    risk_l2 = load_risk_inventory_taxonomy()
    if payload.get("auto_generate_missing_runs", True):
        existing_process_ids = {run.input_context.process_id for run in runs}
        for process in processes:
            if process.process_id in existing_process_ids:
                continue
            bu_name = next(
                (bu.bu_name for bu in bus if bu.bu_id == process.bu_id),
                process.bu_id,
            )
            run = _build_synthetic_process_run(process, bu_name, risk_l2)
            runs.append(run)
            for record in run.records:
                for mapping in record.control_mappings:
                    aggregated_controls.setdefault(
                        mapping.control_id,
                        {
                            "control_id": mapping.control_id,
                            "control_name": mapping.control_name,
                            "control_type": mapping.control_type,
                            "description": mapping.control_description,
                            "owner": process.owner,
                            "frequency": _frequency_from_process(process),
                            "process_ids": [process.process_id],
                            "taxonomy_node_ids": [record.taxonomy_node.id],
                            "design_rating": (
                                mapping.design_effectiveness.rating.value
                                if mapping.design_effectiveness
                                else "Satisfactory"
                            ),
                            "operating_rating": (
                                mapping.operating_effectiveness.rating.value
                                if mapping.operating_effectiveness
                                else "Satisfactory"
                            ),
                        },
                    )

    sidecar_controls = {
        control.get("control_id", ""): control
        for control in payload.get("controls", [])
        if control.get("control_id")
    }
    aggregated_controls.update(sidecar_controls)
    if active_process_ids:
        active_taxonomy_ids = {
            record.taxonomy_node.id
            for run in runs
            for record in run.records
        }
        kris = [kri for kri in kris if kri.risk_taxonomy_id in active_taxonomy_ids]
    control_inventory = [
        ControlInventoryEntry.model_validate(control)
        for control in aggregated_controls.values()
    ]

    return RiskInventoryWorkspace(
        workspace_id=payload.get("workspace_id", "WS-DEMO"),
        bank_id=bank.get("bank_id", "DEMO-FS"),
        bank_name=bank.get("bank_name", "Large Global Bank"),
        business_units=bus,
        processes=processes,
        risk_taxonomy_l1=risk_l1,
        risk_taxonomy_l2=risk_l2,
        control_taxonomy=control_tax,
        root_cause_taxonomy=root_cause_tax,
        bank_controls=list(aggregated_controls.values()),
        control_inventory=control_inventory,
        issues=issues,
        regulatory_obligations=obligations,
        evidence_artifacts=evidence_artifacts,
        risk_appetite_framework=payload.get("risk_appetite_framework", {}),
        kri_library=kris,
        runs=runs,
        agent_trace=_workspace_trace(runs),
        knowledge_pack_manifest={
            "source": str(fixture_path),
            "files": payload.get("knowledge_pack", {}).get("files", {}),
            "auto_generate_missing_runs": payload.get("auto_generate_missing_runs", True),
            "business_unit_count": len(bus),
            "process_count": len(processes),
            "run_count": len(runs),
            "business_unit_filter": sorted(business_unit_filter or []),
            "process_filter": sorted(process_filter or []),
        },
    )


def _run_fixture_path(base_path: Path, entry: Any) -> Path:
    if isinstance(entry, str):
        relative_path = entry
    elif isinstance(entry, dict):
        relative_path = entry.get("fixture") or entry.get("fixture_path") or entry.get("path")
    else:
        relative_path = None
    if not relative_path:
        raise ValueError(f"Run fixture entry must include fixture or fixture_path: {entry!r}")
    return base_path / str(relative_path)


def _normalize_issue_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("title", normalized.get("description", normalized.get("issue_id", "Issue")))
    normalized.setdefault("source", normalized.get("identified_by", "Demo source pack"))
    return normalized


def _normalize_obligation_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("name", normalized.get("description", normalized.get("obligation_id", "Obligation")))
    if "citation" not in normalized and "citation_high_level" in normalized:
        normalized["citation"] = normalized["citation_high_level"]
    normalized.setdefault("risk_taxonomy_ids", normalized.get("risk_taxonomy_id", []))
    normalized.setdefault("control_expectations", normalized.get("control_ids", []))
    return normalized


def _normalize_evidence_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("name", normalized.get("description", normalized.get("evidence_id", "Evidence")))
    if "artifact_type" not in normalized and "evidence_type" in normalized:
        normalized["artifact_type"] = normalized["evidence_type"]
    if "source_system" not in normalized and "source" in normalized:
        normalized["source_system"] = normalized["source"]
    normalized.setdefault("owner", "Process Owner")
    normalized.setdefault("retention", "7 years")
    normalized.setdefault("sample_period", normalized.get("last_refreshed", "Current period"))
    return normalized


def _normalize_kri_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("metric_definition", normalized.get("description", "Demo KRI definition"))
    normalized.setdefault("thresholds", {})
    return normalized


def _build_synthetic_process_run(
    process: Process,
    bu_name: str,
    risk_l2: list[Any],
) -> RiskInventoryRun:
    """Build a deterministic complete run for configured processes without fixtures."""
    loader = MatrixConfigLoader()
    inherent_calc = InherentRiskCalculator(loader.inherent_matrix())
    env_calc = ControlEnvironmentCalculator()
    residual_calc = ResidualRiskCalculator(loader.residual_matrix(), loader.management_response_rules())

    context = ProcessContext(
        process_id=process.process_id,
        process_name=process.process_name,
        product=process.description.split(".")[0][:90] if process.description else "Financial services process",
        business_unit=bu_name,
        description=process.description,
        systems=process.related_systems,
        stakeholders=[process.owner or "Business Process Owner", bu_name, "Operational Risk"],
        source_documents=[f"synthetic knowledge pack process: {process.process_id}"],
    )
    process_text = " ".join(
        [
            process.process_name,
            process.description,
            " ".join(process.related_systems),
            " ".join(process.event_triggers),
            " ".join(process.data_objects),
        ]
    )
    nodes = find_applicable_nodes(process_text, risk_l2, include_all_if_none=True)[:4]
    records: list[RiskInventoryRecord] = []
    generated_controls: dict[str, dict[str, Any]] = {}

    for idx, node in enumerate(nodes, start=1):
        impact_score = ImpactScore.SEVERE if idx == 1 and process.criticality == "Critical" else ImpactScore.SIGNIFICANT
        likelihood_score = LikelihoodScore.HIGH if "daily" in process.cadence.lower() and idx == 1 else LikelihoodScore.MEDIUM_HIGH
        dimensions = []
        likely_dims = {str(dim.value if hasattr(dim, "value") else dim) for dim in node.likely_impact_dimensions}
        for dimension in ImpactDimension:
            score = impact_score if dimension.value in likely_dims else ImpactScore.MEANINGFUL
            dimensions.append(
                ImpactDimensionAssessment(
                    dimension=dimension,
                    score=score,
                    rationale=(
                        f"{node.level_2_category} has {score} {dimension.value.replace('_', ' ')} "
                        f"exposure in {process.process_name} based on process criticality, systems, and event triggers."
                    ),
                )
            )
        impact = ImpactAssessment(
            dimensions=dimensions,
            overall_impact_score=max((item.score for item in dimensions), default=ImpactScore.MEANINGFUL),
            overall_impact_rationale=(
                f"{process.process_name} is {process.criticality.lower()} and depends on "
                f"{', '.join(process.related_systems[:2]) or 'configured systems'}, making the highest "
                "material impact dimension the conservative inherent-risk input."
            ),
        )
        likelihood = LikelihoodAssessment(
            likelihood_score=likelihood_score,
            likelihood_rating=_likelihood_label(int(likelihood_score)),
            rationale=(
                f"Likelihood reflects {process.cadence.lower() or 'recurring'} execution, "
                f"{', '.join(process.event_triggers[:2]) or 'configured triggers'}, and dependency on "
                f"{', '.join(process.related_systems[:2]) or 'manual workflow'}."
            ),
            assumptions=[
                "Synthetic fixture generated from process metadata.",
                "Exposure metrics should be replaced with institution-specific production measures.",
            ],
        )
        inherent = inherent_calc.calculate(
            impact.overall_impact_score,
            likelihood.likelihood_score,
            rationale="Calculated from configured inherent risk matrix using synthetic process metadata.",
        )

        mappings: list[ControlMapping] = []
        if idx < 4:
            control_type = node.related_control_types[0] if node.related_control_types else "Risk and Compliance Assessments"
            control_id = f"CTRL-{process.process_id.replace('PROC-', '').replace('-', '')[:12]}-{idx:03d}"
            control = {
                "control_id": control_id,
                "control_name": f"{process.process_name} {control_type}",
                "control_type": control_type,
                "description": (
                    f"{process.owner or 'Process owner'} performs {control_type.lower()} for "
                    f"{process.process_name} to address {node.level_2_category.lower()} drivers."
                ),
                "design_rating": "Satisfactory" if idx != 2 else "Improvement Needed",
                "operating_rating": "Satisfactory" if idx != 3 else "Improvement Needed",
                "coverage_by_risk": {node.id: "partial" if idx in {2, 3} else "strong"},
                "mapped_root_causes_per_risk": {node.id: node.typical_root_causes[:2]},
                "open_issues": [
                    {
                        "issue_id": f"ISS-{process.process_id.replace('PROC-', '')}-{idx:02d}",
                        "description": f"Sample issue for {node.level_2_category} evidence calibration.",
                        "severity": "Medium",
                        "age_days": 28 + idx * 5,
                        "owner": process.owner or "Process Owner",
                    }
                ]
                if idx == 3
                else [],
                "evidence_quality": {
                    "rating": "Adequate" if idx != 3 else "Needs Refresh",
                    "last_tested": "2026-03-31",
                    "sample_size": 25,
                    "exceptions_noted": 1 if idx == 3 else 0,
                    "notes": "Synthetic evidence profile for demo workflow.",
                },
            }
            generated_controls[control_id] = {
                **control,
                "owner": process.owner,
                "frequency": _frequency_from_process(process),
                "process_ids": [process.process_id],
                "taxonomy_node_ids": [node.id],
            }
            mappings = [_build_control_mapping(control, node)]

        design_rating = _aggregate_design_rating(mappings) if mappings else ControlEffectivenessRating.INADEQUATE
        operating_rating = _aggregate_operating_rating(mappings) if mappings else ControlEffectivenessRating.INADEQUATE
        environment = env_calc.calculate(
            design_rating,
            operating_rating,
            rationale=(
                f"Control environment uses the conservative worse-of design ({design_rating.value}) "
                f"and operating ({operating_rating.value}) rule."
            ),
        )
        residual = residual_calc.calculate(
            inherent,
            environment,
            rationale=(
                f"Residual risk is matrix-calculated from {inherent.inherent_label} inherent risk "
                f"and {environment.control_environment_rating.value} control environment."
            ),
            recommended_action=(
                f"Validate synthetic coverage and collect production evidence for {node.level_2_category}."
            ),
        )
        evidence = [
            EvidenceReference(
                evidence_id=f"EVID-{process.process_id}-{idx:02d}",
                evidence_type="Synthetic knowledge pack",
                description=f"Process metadata and generated control evidence for {node.level_2_category}.",
                source=f"sample_data/risk_inventory_demo/workspace.yaml::{process.process_id}",
            )
        ]
        record = RiskInventoryRecord(
            risk_id=f"RI-{process.process_id.replace('PROC-', '')}-{idx:03d}",
            process_id=process.process_id,
            process_name=process.process_name,
            product=context.product,
            taxonomy_node=node,
            applicability=RiskApplicabilityAssessment(
                materializes=True,
                materialization_type=MaterializationType.PROCESS_SPECIFIC,
                rationale=(
                    f"{node.level_2_category} materializes because {process.process_name} includes "
                    f"{', '.join(node.applicable_process_patterns[:3]) or 'configured financial-services risk drivers'}."
                ),
                confidence=0.78,
                evidence_refs=evidence,
            ),
            risk_statement=RiskStatement(
                risk_description=_with_root_cause_verbiage(
                    _risk_description(node, context),
                    node.typical_root_causes[:3],
                ),
                risk_event=node.example_risk_statements[0] if node.example_risk_statements else _risk_description(node, context),
                causes=node.typical_root_causes[:3],
                consequences=[
                    "financial loss, rework, or delayed service delivery",
                    "regulatory, customer, or executive escalation",
                ],
                affected_stakeholders=context.stakeholders,
            ),
            exposure_metrics=_build_exposure_metrics({}, node, idx),
            impact_assessment=impact,
            likelihood_assessment=likelihood,
            inherent_risk=inherent,
            control_mappings=mappings,
            control_environment=environment,
            residual_risk=residual,
            review_challenges=[
                ReviewChallengeRecord(
                    review_status=ReviewStatus.PENDING_REVIEW,
                    reviewer=process.owner or "Business process owner",
                    challenge_comments=(
                        f"Confirm applicability, evidence, and residual response for {node.level_2_category}."
                    ),
                    challenged_fields=["applicability", "control_mapping", "residual_risk"],
                    approval_status=ApprovalStatus.DRAFT,
                )
            ],
            evidence_references=evidence,
            risk_appetite=RiskAppetite(
                threshold="Medium",
                statement=f"{node.level_2_category} should remain Medium or below after control validation.",
                status="outside" if residual.residual_rating.value in {"High", "Critical"} else "within",
                category=node.level_2_category,
            ),
            action_plan=[
                ActionItem(
                    action=f"Validate generated coverage for {node.level_2_category}.",
                    owner=process.owner or "Process Owner",
                    due_date="2026-06-30",
                    priority="High" if residual.residual_rating.value in {"High", "Critical"} else "Medium",
                )
            ],
            coverage_gaps=[] if mappings and idx == 1 else [
                f"Coverage for {node.level_2_category} requires production evidence and root-cause validation."
            ],
            demo_record=True,
        )
        records.append(record)

    run = RiskInventoryRun(
        run_id=f"DEMO-RI-{process.process_id.replace('PROC-', '')}-SYN",
        tenant_id="reference-pack",
        bank_id="reference-pack",
        input_context=context,
        records=records,
        executive_summary=ExecutiveSummary(
            headline=(
                f"{process.process_name} generated {len(records)} risk records with deterministic "
                "inherent/residual scoring and synthetic control coverage where fixture detail is pending."
            ),
            key_messages=[
                f"{bu_name} risk profile is differentiated through process metadata and taxonomy matching.",
                "Synthetic controls are flagged for business validation before acceptance.",
                "Residual risk remains matrix-calculated and review-ready.",
            ],
            top_residual_risks=[
                f"{record.taxonomy_node.level_2_category}: {record.residual_risk.residual_label}"
                for record in records
                if record.residual_risk.residual_rating.value in {"Medium", "High", "Critical"}
            ],
            recommended_actions=[
                "Replace synthetic exposure metrics with production measures.",
                "Validate mapped controls and evidence with process owners.",
                "Approve or challenge residual ratings in the HITL review phase.",
            ],
        ),
        config_snapshot=loader.config_snapshot(),
        run_manifest={
            "fixture": "synthetic knowledge pack generation",
            "deterministic": True,
            "llm_required": False,
            "record_count": len(records),
            "generated_controls": list(generated_controls),
        },
        demo_mode=True,
        events=[event.model_dump() for event in _run_trace(process.process_name, records)],
    )
    findings = RiskInventoryValidator(inherent_calc, residual_calc).validate_run(run, set(generated_controls))
    return run.model_copy(update={"validation_findings": findings})


def _frequency_from_process(process: Process) -> str:
    cadence = process.cadence.lower()
    if "daily" in cadence or "continuous" in cadence:
        return "Daily"
    if "weekly" in cadence:
        return "Weekly"
    if "monthly" in cadence:
        return "Monthly"
    if "quarter" in cadence:
        return "Quarterly"
    return "Event-driven"


def _run_trace(process_name: str, records: list[RiskInventoryRecord]) -> list[AgentTraceEvent]:
    return [
        AgentTraceEvent(
            stage="Synthetic Fixture Generation",
            agent="DeterministicKnowledgePackAgent",
            summary=f"Generated {len(records)} review-ready records for {process_name}.",
            inputs_used=["process metadata", "risk taxonomy", "scoring matrices"],
            output_refs=[record.risk_id for record in records],
        )
    ]


def _workspace_trace(runs: list[RiskInventoryRun]) -> list[AgentTraceEvent]:
    return [
        AgentTraceEvent(
            stage="Knowledge Pack Assembly",
            agent="KnowledgePackLoader",
            summary=f"Assembled {len(runs)} process risk inventory runs for the flagship demo workspace.",
            inputs_used=["workspace.yaml", "run fixtures", "risk inventory config"],
            output_refs=[run.run_id for run in runs],
        )
    ]
