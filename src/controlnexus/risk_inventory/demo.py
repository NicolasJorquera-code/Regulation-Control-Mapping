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
    ApprovalStatus,
    BusinessUnit,
    ControlDesignEffectivenessAssessment,
    ControlEffectivenessRating,
    ControlMapping,
    ControlOperatingEffectivenessAssessment,
    ControlTaxonomyEntry,
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
    Procedure,
    ProcessContext,
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
from controlnexus.risk_inventory.taxonomy import load_risk_inventory_taxonomy
from controlnexus.risk_inventory.validator import RiskInventoryValidator


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

    context = ProcessContext(
        process_id=scenario["process_id"],
        process_name=scenario["process_name"],
        product=scenario["product"],
        business_unit=scenario["business_unit"],
        description=scenario["description"],
        systems=scenario.get("systems", []),
        stakeholders=scenario.get("stakeholders", []),
        source_documents=["demo fixture: payment_exception_handling.yaml"],
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
            rationale=(
                f"Derived as the worse of aggregate design ({design_rating.value}) and operating "
                f"({operating_rating.value}) effectiveness for mapped controls."
            ),
        )
        residual = residual_calc.calculate(
            inherent,
            environment,
            rationale=(
                f"Residual risk is matrix-calculated from {inherent.inherent_label} inherent risk "
                f"and {environment.control_environment_rating.value} control environment."
            ),
            recommended_action=spec.get("recommended_action", ""),
        )
        evidence_references = [
            EvidenceReference(
                evidence_id=reference.get("evidence_id", f"EVID-{idx:03d}"),
                evidence_type=reference.get("evidence_type", "Demo source"),
                description=reference.get("description", ""),
                source=reference.get("source", "sample_data/risk_inventory_demo/payment_exception_handling.yaml"),
            )
            for reference in spec.get("evidence_references", [])
        ] or [
            EvidenceReference(
                evidence_id=f"EVID-{idx:03d}",
                evidence_type="Demo source",
                description=f"Demo process narrative and mapped control evidence for {node.level_2_category}.",
                source="sample_data/risk_inventory_demo/payment_exception_handling.yaml",
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
                risk_description=_with_root_cause_verbiage(
                    spec.get("risk_description") or _risk_description(node, context),
                    spec.get("causes") or node.typical_root_causes[:3],
                ),
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
                    ai_original_value=review.get("ai_original_value", ""),
                    reviewer_adjusted_value=review.get("reviewer_adjusted_value", ""),
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


def _with_root_cause_verbiage(description: str, causes: list[str]) -> str:
    """Keep root-cause context in the statement while the detailed UI is deferred."""
    clean_description = description.strip()
    if not causes:
        return clean_description
    cause_text = "; ".join(causes[:3])
    if cause_text.lower() in clean_description.lower():
        return clean_description
    return f"{clean_description} Root-cause lens: {cause_text}."


def _build_exposure_metrics(spec: dict[str, Any], node: Any, idx: int) -> list[ExposureMetric]:
    metrics = spec.get("exposure_metrics")
    if metrics:
        return [
            ExposureMetric(
                metric_name=metric.get("metric_name", ""),
                metric_value=str(metric.get("metric_value", "")),
                metric_unit=metric.get("metric_unit", ""),
                description=metric.get("description", ""),
                source=metric.get("source", "Payment Exception Workflow"),
                supports=metric.get("supports", ["likelihood", "impact"]),
            )
            for metric in metrics
        ]

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
# Workspace loader (multi-BU, multi-procedure demo)
# ---------------------------------------------------------------------------


def default_workspace_fixture_path() -> Path:
    return resolve_project_root() / "sample_data" / "risk_inventory_demo" / "workspace.yaml"


def load_demo_workspace(path: Path | str | None = None) -> RiskInventoryWorkspace:
    """Load the multi-BU demo workspace with knowledge-base and per-procedure runs."""
    fixture_path = Path(path) if path else default_workspace_fixture_path()
    payload = read_yaml(fixture_path)

    bank = payload.get("bank", {})
    bus = [BusinessUnit.model_validate(item) for item in payload.get("business_units", [])]
    procedures = [Procedure.model_validate(item) for item in payload.get("procedures", [])]
    risk_l1 = [RiskTaxonomyLevel1.model_validate(item) for item in payload.get("risk_taxonomy_l1", [])]
    control_tax = [ControlTaxonomyEntry.model_validate(item) for item in payload.get("control_taxonomy", [])]
    root_cause_tax = [RootCauseTaxonomyEntry.model_validate(item) for item in payload.get("root_cause_taxonomy", [])]

    kris: list[KRIDefinition] = []
    for item in payload.get("kri_library", []):
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
        run_path = fixture_path.parent / entry["fixture"]
        run = load_demo_risk_inventory(run_path)
        runs.append(run)
        # also collect controls for the bank-wide knowledge-base view
        run_payload = read_yaml(run_path)
        for control in run_payload.get("controls", []):
            aggregated_controls.setdefault(control["control_id"], control)

    # taxonomy L2 nodes (loaded once)
    risk_l2 = load_risk_inventory_taxonomy()

    return RiskInventoryWorkspace(
        workspace_id=payload.get("workspace_id", "WS-DEMO"),
        bank_id=bank.get("bank_id", "DEMO-BANK"),
        bank_name=bank.get("bank_name", "Demo Bank"),
        business_units=bus,
        procedures=procedures,
        risk_taxonomy_l1=risk_l1,
        risk_taxonomy_l2=risk_l2,
        control_taxonomy=control_tax,
        root_cause_taxonomy=root_cause_tax,
        bank_controls=list(aggregated_controls.values()),
        kri_library=kris,
        runs=runs,
    )
