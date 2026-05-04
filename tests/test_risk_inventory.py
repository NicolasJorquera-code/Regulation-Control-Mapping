"""Tests for Risk Inventory Builder."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from pydantic import ValidationError

from controlnexus.risk_inventory.calculators import (
    ControlEnvironmentCalculator,
    InherentRiskCalculator,
    ResidualRiskCalculator,
)
from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.demo import load_demo_risk_inventory, load_demo_workspace, load_knowledge_pack
from controlnexus.risk_inventory.document_ingest import analyze_process_document
from controlnexus.risk_inventory.export import (
    build_hitl_review_workbook,
    build_risk_inventory_workspace_workbook,
    export_risk_inventory_to_excel,
    risk_inventory_excel_bytes,
    risk_inventory_review_excel_bytes,
    risk_inventory_workspace_excel_bytes,
)
from controlnexus.risk_inventory.graph import build_risk_inventory_graph
from controlnexus.risk_inventory.models import (
    ControlEffectivenessRating,
    ControlEnvironmentAssessment,
    ControlEnvironmentRating,
    ImpactAssessment,
    ImpactDimension,
    ImpactDimensionAssessment,
    ImpactScore,
    InherentRiskAssessment,
    Process,
    ReviewDecision,
    ReviewStatus,
    ApprovalStatus,
    RiskRating,
    RiskInventoryWorkspace,
)
from controlnexus.risk_inventory.services import (
    apply_review_decisions,
    build_control_gaps,
    build_synthetic_control_recommendations,
    run_risk_inventory_workflow,
    validate_knowledge_pack,
)
from controlnexus.risk_inventory.taxonomy import load_risk_inventory_taxonomy
from controlnexus.risk_inventory.tools import build_risk_inventory_tool_executor
from controlnexus.risk_inventory.validator import RiskInventoryValidator


class TestRiskInventoryConfig:
    def test_config_loads(self):
        loader = MatrixConfigLoader()
        assert loader.impact_scales()["dimensions"]
        assert loader.frequency_scale()["scale"]
        assert loader.likelihood_scale()["scale"]
        assert loader.inherent_matrix()["matrix"]
        assert loader.residual_matrix()["matrix"]

    def test_taxonomy_crosswalk_has_required_categories(self):
        nodes = load_risk_inventory_taxonomy()
        categories = {node.level_2_category for node in nodes}
        required = {
            "Business Process Risk",
            "Data Management Risk",
            "IT Security / Cybersecurity Risk",
            "Regulatory Reporting Risk",
            "Third Party Risk",
        }
        assert required.issubset(categories)


class TestRiskInventoryCalculators:
    @pytest.mark.parametrize(
        ("impact", "likelihood", "expected"),
        [
            (1, 1, "Low-1"),
            (1, 4, "Medium-4"),
            (2, 3, "Medium-6"),
            (2, 4, "High-8"),
            (3, 3, "High-9"),
            (3, 4, "Critical-12"),
            (4, 1, "Medium-4"),
            (4, 4, "Critical-16"),
        ],
    )
    def test_inherent_matrix_key_cases(self, impact, likelihood, expected):
        result = InherentRiskCalculator().calculate(impact, likelihood)
        assert result.inherent_label == expected

    def test_inherent_matrix_all_16_combinations(self):
        calc = InherentRiskCalculator()
        expected = {
            1: {1: "Low-1", 2: "Low-2", 3: "Low-3", 4: "Medium-4"},
            2: {1: "Low-2", 2: "Medium-4", 3: "Medium-6", 4: "High-8"},
            3: {1: "Low-3", 2: "Medium-6", 3: "High-9", 4: "Critical-12"},
            4: {1: "Medium-4", 2: "High-8", 3: "Critical-12", 4: "Critical-16"},
        }
        for impact, likelihoods in expected.items():
            for likelihood, label in likelihoods.items():
                result = calc.calculate(impact, likelihood)
                assert result.inherent_score == impact * likelihood
                assert result.inherent_label == label

    @pytest.mark.parametrize(
        ("inherent_label", "environment", "expected"),
        [
            ("Low-1", "Strong", "Low-1"),
            ("Medium-4", "Inadequate", "Medium-20"),
            ("High-8", "Improvement Needed", "Medium-24"),
            ("Critical-12", "Satisfactory", "Medium-24"),
            ("Critical-16", "Inadequate", "Critical-80"),
        ],
    )
    def test_residual_matrix_key_cases(self, inherent_label, environment, expected):
        rating, score = inherent_label.split("-")
        inherent = InherentRiskAssessment(
            impact_score=ImpactScore.MINIMAL,
            likelihood_score=1,
            inherent_score=int(score),
            inherent_rating=RiskRating(rating),
            inherent_label=inherent_label,
        )
        env = ControlEnvironmentAssessment(
            design_rating=ControlEffectivenessRating(environment),
            operating_rating=ControlEffectivenessRating(environment),
            control_environment_rating=ControlEnvironmentRating(environment),
            rationale="test",
        )
        result = ResidualRiskCalculator().calculate(inherent, env)
        assert result.residual_label == expected

    def test_residual_matrix_all_configured_combinations(self):
        expected = {
            "Low-1": {"Strong": "Low-1", "Satisfactory": "Low-2", "Improvement Needed": "Low-3", "Inadequate": "Low-5"},
            "Low-2": {"Strong": "Low-2", "Satisfactory": "Low-4", "Improvement Needed": "Low-6", "Inadequate": "Low-10"},
            "Low-3": {"Strong": "Low-3", "Satisfactory": "Low-6", "Improvement Needed": "Low-9", "Inadequate": "Low-15"},
            "Medium-4": {"Strong": "Low-4", "Satisfactory": "Low-8", "Improvement Needed": "Low-12", "Inadequate": "Medium-20"},
            "Medium-6": {"Strong": "Low-6", "Satisfactory": "Low-12", "Improvement Needed": "Low-18", "Inadequate": "Medium-30"},
            "High-8": {"Strong": "Low-8", "Satisfactory": "Low-16", "Improvement Needed": "Medium-24", "Inadequate": "High-40"},
            "High-9": {"Strong": "Low-9", "Satisfactory": "Low-18", "Improvement Needed": "Medium-27", "Inadequate": "High-45"},
            "Critical-12": {"Strong": "Low-12", "Satisfactory": "Medium-24", "Improvement Needed": "High-36", "Inadequate": "Critical-60"},
            "Critical-16": {"Strong": "Low-16", "Satisfactory": "Medium-32", "Improvement Needed": "High-48", "Inadequate": "Critical-80"},
        }
        calc = ResidualRiskCalculator()
        for inherent_label, environments in expected.items():
            rating, score = inherent_label.split("-")
            inherent = InherentRiskAssessment(
                impact_score=ImpactScore.MINIMAL,
                likelihood_score=1,
                inherent_score=int(score),
                inherent_rating=RiskRating(rating),
                inherent_label=inherent_label,
            )
            for environment, label in environments.items():
                env = ControlEnvironmentAssessment(
                    design_rating=ControlEffectivenessRating(environment),
                    operating_rating=ControlEffectivenessRating(environment),
                    control_environment_rating=ControlEnvironmentRating(environment),
                    rationale="test",
                )
                assert calc.calculate(inherent, env).residual_label == label

    def test_control_environment_uses_worse_rating(self):
        result = ControlEnvironmentCalculator().calculate(
            ControlEffectivenessRating.STRONG,
            ControlEffectivenessRating.IMPROVEMENT_NEEDED,
        )
        assert result.control_environment_rating.value == "Improvement Needed"


class TestRiskInventoryModels:
    def test_impact_overall_below_dimension_requires_justification(self):
        with pytest.raises(ValidationError):
            ImpactAssessment(
                dimensions=[
                    ImpactDimensionAssessment(
                        dimension=ImpactDimension.FINANCIAL,
                        score=ImpactScore.SEVERE,
                        rationale="Severe financial impact.",
                    )
                ],
                overall_impact_score=ImpactScore.MEANINGFUL,
                overall_impact_rationale="Lower overall score.",
            )

    def test_process_alias_accepts_procedure_payload(self):
        process = Process.model_validate(
            {
                "procedure_id": "PROC-LEGACY",
                "procedure_name": "Legacy Named Process",
                "bu_id": "BU-TEST",
                "apqc_crosswalk": {
                    "framework": "APQC Banking PCF",
                    "version": "7.2.2",
                    "process_id": "banking-test",
                    "process_name": "Normalize test process",
                    "confidence": 0.75,
                    "rationale": "Optional crosswalk only.",
                },
            }
        )
        workspace = RiskInventoryWorkspace.model_validate(
            {"workspace_id": "WS-TEST", "procedures": [process.model_dump()]}
        )

        assert process.process_id == "PROC-LEGACY"
        assert process.procedure_name == "Legacy Named Process"
        assert process.apqc_crosswalk["framework"] == "APQC Banking PCF"
        assert workspace.procedures[0].process_name == "Legacy Named Process"


class TestRiskInventoryDemoAndGraph:
    def test_document_ingest_extracts_process_context(self):
        sample_path = Path("sample_data/risk_inventory_demo/payment_exception_policy.md")
        analysis = analyze_process_document(sample_path.name, sample_path.read_bytes())
        assert analysis.process_name == "Payment Exception Handling"
        assert analysis.product == "High-value payment processing"
        assert "Business Process Risk" in analysis.detected_risk_categories
        assert analysis.detected_controls
        assert analysis.exposure_cues

    def test_demo_loader_returns_complete_run(self):
        run = load_demo_risk_inventory()
        assert run.demo_mode is True
        assert run.input_context.process_name == "Payment Exception Handling"
        assert len(run.records) >= 6
        assert all(record.control_mappings for record in run.records)
        assert all(record.residual_risk.residual_label for record in run.records)

    def test_demo_loader_uses_specific_fixture_evidence(self):
        run = load_demo_risk_inventory()
        cyber = next(record for record in run.records if record.taxonomy_node.id == "RIB-CYB")

        assert "generic source pack" in cyber.likelihood_assessment.rationale
        assert cyber.residual_risk.management_response.recommended_action.startswith("Close evidence")
        assert any(metric.metric_name == "Cybersecurity And Privileged Access exposure count" for metric in cyber.exposure_metrics)
        assert any(reference.evidence_id == "EV-PAYEXC-003" for reference in cyber.evidence_references)
        assert run.run_manifest["evidence_metric_count"] >= 20
        assert "Payment Exception Handling captures 8 risk records" in run.executive_summary.headline

    def test_demo_requires_no_llm_and_validates(self):
        run = load_demo_risk_inventory()
        assert run.run_manifest["llm_required"] is False
        findings = RiskInventoryValidator().validate_run(run)
        assert all(finding.severity.value != "error" for finding in findings)

    def test_demo_workspace_has_flagship_process_breadth(self):
        workspace = load_demo_workspace()
        assert workspace.bank_name == "Large Global Bank"
        assert len(workspace.business_units) == 5
        assert len(workspace.processes) == 10
        assert len(workspace.runs) == 10
        assert len(workspace.bank_controls) == 84
        assert sum(len(run.records) for run in workspace.runs) == 74
        assert workspace.knowledge_pack_manifest["auto_generate_missing_runs"] is False
        assert not validate_knowledge_pack(workspace)
        assert all(workspace.run_for_process(process.process_id) for process in workspace.processes)
        assert all(run.records for run in workspace.runs)
        assert any(process.apqc_crosswalk for process in workspace.processes)

    def test_knowledge_pack_loader_alias(self):
        workspace = load_knowledge_pack()
        assert workspace.workspace_id == "WS-LARGE-GLOBAL-BANK"
        assert workspace.knowledge_pack_manifest["process_count"] == 10

    def test_loader_accepts_fixture_path_entries(self):
        workspace = load_knowledge_pack("sample_data/risk_inventory_demo/workspace.yaml")
        assert workspace.runs
        assert {run.input_context.process_id for run in workspace.runs} == {
            process.process_id for process in workspace.processes
        }

    def test_demo_loader_source_documents_use_fixture_name(self):
        run = load_demo_risk_inventory("sample_data/risk_inventory_demo/customer_onboarding.yaml")
        assert run.input_context.source_documents == ["demo fixture: customer_onboarding.yaml"]

    def test_graph_deterministic_path(self):
        graph = build_risk_inventory_graph().compile()
        result = graph.invoke(
            {
                "run_id": "TEST-RI-001",
                "tenant_id": "test",
                "process_context": {
                    "process_id": "PROC-PAY-EXCEPTION",
                    "process_name": "Payment Exception Handling",
                    "product": "High-value payment processing",
                    "business_unit": "Payment Operations",
                    "description": "Daily high-value payment exception process with queue, reconciliation, access, and reporting.",
                    "systems": ["Payment Exception Workflow"],
                    "stakeholders": ["Operations Manager"],
                },
                "control_inventory": [
                    {
                        "control_id": "CTRL-PAY-001",
                        "control_name": "Daily exception queue review",
                        "control_type": "Exception Reporting",
                        "description": "Daily queue review and escalation.",
                    }
                ],
                "max_risks": 3,
            },
            config={"recursion_limit": 200},
        )
        report = result["final_report"]
        assert report["run_id"] == "TEST-RI-001"
        assert len(report["records"]) == 3
        assert report["records"][0]["inherent_risk"]["inherent_label"]

    def test_flagship_workflow_returns_trace_with_no_llm(self):
        workspace = load_demo_workspace()
        run = run_risk_inventory_workflow(
            workspace,
            {"process_id": "PROC-PAY-RECON"},
            llm_enabled=False,
        )
        assert run.input_context.process_id == "PROC-PAY-RECON"
        assert run.events
        assert all(event["mode"] in {"deterministic_fallback", "skipped"} for event in run.events)

    def test_synthetic_control_recommendations_for_gap(self):
        workspace = load_demo_workspace()
        record = next(
            record
            for run in workspace.runs
            for record in run.records
            if build_control_gaps(record)
        )

        gaps = build_control_gaps(record)
        recommendations = build_synthetic_control_recommendations(record, workspace)

        assert gaps
        assert recommendations
        assert recommendations[0].risk_id == record.risk_id
        assert recommendations[0].control_statement

    def test_risk_inventory_tool_executor_lookup(self):
        workspace = load_demo_workspace()
        execute = build_risk_inventory_tool_executor(workspace)

        process_result = execute(
            "knowledge_base_lookup",
            {"entity_type": "process", "entity_id": "PROC-ACCESS-RECERT"},
        )
        matrix_result = execute("scoring_matrix_lookup", {"matrix": "residual"})

        assert process_result["records"][0]["process_name"] == "Privileged Access Recertification"
        assert "matrix" in matrix_result


class TestRiskInventoryControlMappingUiHelpers:
    def test_demo_tab_list_removes_consolidated_tabs(self):
        from controlnexus.ui import risk_inventory_tab

        assert risk_inventory_tab.DEMO_RISK_INVENTORY_TABS == [
            "Knowledge Base",
            "Risk Inventory",
            "Control Mapping",
            "Gap Analysis",
            "Review & Challenge",
            "Executive Report",
        ]
        assert "Control Gap Lab" not in risk_inventory_tab.DEMO_RISK_INVENTORY_TABS
        assert "Process Map" not in risk_inventory_tab.DEMO_RISK_INVENTORY_TABS
        assert "Residual Risk" not in risk_inventory_tab.DEMO_RISK_INVENTORY_TABS
        assert "KRI Program" not in risk_inventory_tab.DEMO_RISK_INVENTORY_TABS
        assert "Agent Run Trace" not in risk_inventory_tab.DEMO_RISK_INVENTORY_TABS

    def test_knowledge_base_tabs_remove_readiness_evidence_and_issues(self):
        from controlnexus.ui import risk_inventory_tab

        assert "Knowledge Pack Readiness" not in risk_inventory_tab.KNOWLEDGE_BASE_TABS
        assert "Evidence" not in risk_inventory_tab.KNOWLEDGE_BASE_TABS
        assert "Issues" not in risk_inventory_tab.KNOWLEDGE_BASE_TABS

    def test_knowledge_base_profile_options_are_generic(self):
        from controlnexus.ui import risk_inventory_tab

        assert risk_inventory_tab.knowledge_base_profile_options() == [
            "Large Global Bank",
            "Local Regional Bank",
            "Digital Payments Institution",
        ]
        assert "MOCK_" + "INSTITUTION_PROFILES" not in vars(risk_inventory_tab)

    def test_profile_workspace_variants_filter_source_pack(self):
        large = load_demo_workspace()
        local = load_demo_workspace("sample_data/risk_inventory_demo/workspace_local_regional_bank.yaml")
        payments = load_demo_workspace("sample_data/risk_inventory_demo/workspace_digital_payments_institution.yaml")

        assert large.bank_name == "Large Global Bank"
        assert local.bank_name == "Local Regional Bank"
        assert payments.bank_name == "Digital Payments Institution"
        assert len(local.processes) < len(large.processes)
        assert len(payments.business_units) < len(large.business_units)
        assert all(local.run_for_process(process.process_id) for process in local.processes)
        assert all(payments.run_for_process(process.process_id) for process in payments.processes)

    def test_bu_risk_capture_rows_show_differentiation(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        rows = risk_inventory_tab.bu_risk_capture_rows(workspace)

        assert len(rows) == len(workspace.business_units)
        assert all(row["Key Source Packs"] for row in rows)
        assert all(row["Capture Rationale"] for row in rows)
        assert len({row["Dominant Captured Risk Types"] for row in rows}) > 1

    def test_bu_divergence_rows_show_level_2_drivers(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        rows = risk_inventory_tab.bu_risk_divergence_rows(workspace)

        assert rows
        assert all(row["Level 2 Risk Category"] for row in rows)
        assert all(row["Enterprise Category"] for row in rows)
        assert all(row["Representative Process"] for row in rows)
        assert "Dominant Risk Category" not in rows[0]

    def test_no_banned_demo_names_in_ui_constants_or_sample_data(self):
        from controlnexus.ui import risk_inventory_tab

        banned = (
            "North" + "star",
            "Meri" + "dian",
            "Harbor" + "line",
            "FICT" + "-FS",
            "north" + "star-demo",
            "demo" + "-bank",
        )
        ui_blob = repr(risk_inventory_tab.KNOWLEDGE_BASE_PROFILES)
        sample_blob = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path("sample_data/risk_inventory_demo").rglob("*")
            if path.is_file() and path.suffix in {".yaml", ".yml", ".md"}
        )

        assert not any(term in ui_blob for term in banned)
        assert not any(term in sample_blob for term in banned)

    def test_risk_workbench_rows_include_every_selected_run_risk(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None

        rows = risk_inventory_tab.risk_inventory_workbench_rows(run, workspace)

        assert len(rows) == len(run.records)
        assert {row["Risk Record ID"] for row in rows} == {record.risk_id for record in run.records}
        assert all("Frequency" in row for row in rows)
        assert all("Residual Risk" in row for row in rows)
        assert all(isinstance(row["Gaps"], int) for row in rows)
        assert all(row["Validation Level"] for row in rows)
        assert all(row["Required Reviewer"] for row in rows)

    def test_selected_risk_detail_contains_consolidated_profile(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None
        record = run.records[0]

        detail = risk_inventory_tab.selected_risk_detail(record, workspace)

        expected_keys = {
            "risk_id",
            "business_unit",
            "risk_statement",
            "root_causes",
            "impact_score",
            "frequency_score",
            "inherent_risk",
            "residual_risk",
            "management_response",
            "mitigation_plan",
            "controls",
            "control_gaps",
            "synthetic_controls",
            "kris",
            "evidence",
            "issues",
            "review",
            "apqc_crosswalk",
            "validation",
        }
        assert expected_keys.issubset(detail)
        assert detail["risk_id"] == record.risk_id
        assert detail["business_unit"]
        assert detail["frequency_score"] == int(record.likelihood_assessment.likelihood_score)
        assert detail["mitigation_plan"] == record.residual_risk.management_response.recommended_action
        assert isinstance(detail["controls"], list)
        assert isinstance(detail["kris"], list)
        assert isinstance(detail["evidence"], list)
        assert isinstance(detail["review"], dict)
        assert detail["validation"]["validation_level"]

    def test_impact_frequency_heatmap_marks_selected_cell(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None
        record = run.records[0]

        rows = risk_inventory_tab.impact_frequency_heatmap_rows(record)
        selected = [row for row in rows if row["Selected"]]

        assert len(rows) == 16
        assert len(selected) == 1
        assert selected[0]["Impact"] == int(record.impact_assessment.overall_impact_score)
        assert selected[0]["Frequency"] == int(record.likelihood_assessment.likelihood_score)
        assert selected[0]["Label"] == record.inherent_risk.inherent_label

    def test_portfolio_heatmap_rows_aggregate_business_unit_and_category(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        rows = risk_inventory_tab.portfolio_heatmap_rows(workspace)
        payment_bu = next(bu for bu in workspace.business_units if bu.bu_name == "Payment Operations")
        payment_rows = risk_inventory_tab.portfolio_heatmap_rows(workspace, payment_bu.bu_id)
        category_count = len({record.taxonomy_node.level_1_category for run in workspace.runs for record in run.records})

        assert rows
        assert len(rows) == len(workspace.business_units) * category_count
        assert {row["Business Unit"] for row in payment_rows} == {"Payment Operations"}
        assert any(row["Risk Records"] > 0 for row in rows)
        assert all(row["Heat"] in {"None", "Low", "Elevated", "Medium", "High"} for row in rows)

    def test_workspace_aggregated_inventory_rows_are_table_ready(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        rows = risk_inventory_tab.workspace_aggregated_inventory_rows(workspace)

        assert len(rows) == sum(len(run.records) for run in workspace.runs)
        assert list(rows[0])[:4] == [
            "Risk Record ID",
            "Risk Subcategory",
            "Residual Risk Rating",
            "Business Unit",
        ]
        assert all(row["Risk Subcategory"] for row in rows)
        assert all(row["High+ Residual"] in {"Yes", "No"} for row in rows)
        assert all(isinstance(row["Control Gaps"], int) for row in rows)

    def test_workspace_risk_inventory_render_does_not_render_divergence_table(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        calls = []

        monkeypatch.setattr(risk_inventory_tab.st, "markdown", lambda *args, **kwargs: None)
        monkeypatch.setattr(risk_inventory_tab, "_render_workspace_inventory_summary", lambda *args, **kwargs: None)
        monkeypatch.setattr(risk_inventory_tab, "_render_prominent_table", lambda rows: calls.append(("inventory", len(rows))))
        monkeypatch.setattr(risk_inventory_tab, "_render_portfolio_heatmap", lambda rows: calls.append(("heatmap", len(rows))))
        monkeypatch.setattr(risk_inventory_tab, "_render_bu_difference_cards", lambda *args, **kwargs: calls.append(("breakdown", 1)))
        monkeypatch.setattr(
            risk_inventory_tab,
            "bu_risk_divergence_rows",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("divergence table should not render")),
        )

        risk_inventory_tab._render_workspace_aggregated_inventory(workspace, None)

        assert calls[0][0] == "inventory"
        assert ("breakdown", 1) in calls

    def test_risk_inventory_tab_does_not_include_redundant_detail_expanders(self):
        source = Path("src/controlnexus/ui/risk_inventory_tab.py").read_text(encoding="utf-8")

        assert "Controls and Coverage" not in source
        assert "Evidence and Source Trace" not in source
        assert "Issues and Open Findings" not in source
        assert "Mitigation Plan" not in source
        assert "Review and Challenge" not in source
        assert "_render_selected_risk_drawer" not in source

    def test_table_column_labels_are_professionalized(self):
        from controlnexus.ui import risk_inventory_tab

        assert risk_inventory_tab._display_column_label("gap_type") == "Gap Type"
        assert risk_inventory_tab._display_column_label("existing_control_ids") == "Existing Control IDs"
        assert risk_inventory_tab._display_column_label("kri_id") == "KRI ID"
        assert risk_inventory_tab._display_column_label("Risk Record ID") == "Risk Record ID"

    def test_process_header_facts_are_limited_to_business_unit_and_process(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None
        captured = {}

        monkeypatch.setattr(risk_inventory_tab.st, "markdown", lambda *args, **kwargs: None)
        monkeypatch.setattr(risk_inventory_tab, "_render_fact_block", lambda facts: captured.update(facts))

        risk_inventory_tab._render_process_command_header(run, workspace)

        assert set(captured) == {"Business Unit", "Process"}
        assert captured["Business Unit"] == "Payment Operations"
        assert captured["Process"] == "Payment Exception Handling"

    def test_risk_header_focuses_on_statement_not_color_badges(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        record = load_demo_risk_inventory().records[0]
        rendered = []

        monkeypatch.setattr(
            risk_inventory_tab.st,
            "markdown",
            lambda body, **kwargs: rendered.append(body),
        )

        risk_inventory_tab._render_risk_header(record)

        body = rendered[0]
        assert "ri-risk-statement-focus" in body
        assert record.risk_statement.risk_description[:40] in body
        assert "Inherent Risk:" not in body
        assert "Residual Risk:" not in body
        assert "Management Response:" not in body

    def test_risk_inventory_browser_no_longer_renders_summary_strip(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None
        rows = risk_inventory_tab.risk_inventory_workbench_rows(run, workspace)
        markdown_calls = []

        class Selection:
            rows: list[int] = []

        class Event:
            selection = Selection()

        monkeypatch.setattr(
            risk_inventory_tab.st,
            "markdown",
            lambda body, **kwargs: markdown_calls.append(body),
        )
        monkeypatch.setattr(risk_inventory_tab.st, "dataframe", lambda *args, **kwargs: Event())

        risk_inventory_tab._render_risk_inventory_browser(rows, run.records[0].risk_id)

        assert not any("ri-inventory-summary" in str(call) for call in markdown_calls)

    def test_review_dossier_helper_returns_validation_context(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None
        record = run.records[0]

        queue_rows = risk_inventory_tab.review_validation_rows(run, workspace)
        dossier = risk_inventory_tab.selected_review_dossier(record, workspace)
        validation = risk_inventory_tab.required_validation_level(record, workspace)

        assert len(queue_rows) == len(run.records)
        assert all(row["Validation Level"] for row in queue_rows)
        assert validation["required_reviewer"]
        assert dossier["validation"]["validation_level"]
        assert dossier["controls"] is not None
        assert dossier["gaps"] is not None
        assert dossier["source_trace"]
        assert dossier["checklist"]
        assert dossier["scoring_rationale"]
        assert "synthetic_controls" in dossier
        assert dossier["level_2_category"] == record.taxonomy_node.level_2_category
        assert "deterministic" in dossier["bank_context_alignment"].lower()

    def test_neutral_callout_helper_uses_grey_callout_class(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        calls = []

        monkeypatch.setattr(
            risk_inventory_tab.st,
            "markdown",
            lambda body, **kwargs: calls.append({"body": body, **kwargs}),
        )

        risk_inventory_tab._render_neutral_callout("Choose a process focus.")

        assert "ri-neutral-callout" in calls[0]["body"]
        assert calls[0]["unsafe_allow_html"] is True

    def test_workspace_control_mapping_rows_filter_by_business_unit(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        all_rows = risk_inventory_tab._workspace_control_mapping_rows(workspace)
        payment_ops = next(bu for bu in workspace.business_units if bu.bu_name == "Payment Operations")
        payment_rows = risk_inventory_tab._workspace_control_mapping_rows(workspace, payment_ops.bu_id)

        assert len(all_rows) == sum(len(run.records) for run in workspace.runs)
        assert payment_rows
        assert len(payment_rows) < len(all_rows)
        assert {row["Business Unit"] for row in payment_rows} == {"Payment Operations"}
        assert all(row["Enterprise Risk Category"] for row in payment_rows)
        assert all(isinstance(row["Mapped Controls"], int) for row in payment_rows)

    def test_workspace_control_mapping_matrix_summarizes_bu_and_risk_category(self):
        from controlnexus.ui import risk_inventory_tab

        workspace = load_demo_workspace()
        rows = risk_inventory_tab._workspace_control_mapping_rows(workspace)
        matrix = risk_inventory_tab._workspace_control_mapping_matrix_rows(rows)
        category_rows = risk_inventory_tab._workspace_control_mapping_category_rows(rows)

        assert len(matrix) == len({row["Business Unit"] for row in rows})
        assert all(row["Risk Records"] > 0 for row in matrix)
        assert all("Mapped Controls" in row for row in matrix)
        assert any(row["Enterprise Risk Category"] == "Operational" for row in category_rows)
        assert sum(row["Risk Records"] for row in category_rows) == len(rows)

    def test_run_control_mapping_rows_include_coverage_depth(self):
        from controlnexus.ui import risk_inventory_tab

        run = load_demo_risk_inventory()
        rows = risk_inventory_tab._run_control_mapping_rows(run)

        assert rows
        assert all(row["Control Objective"] for row in rows)
        assert all(row["Risk Coverage Rationale"] for row in rows)
        assert all("Mapped Root Causes" in row for row in rows)
        assert all("Evidence Quality" in row for row in rows)
        assert all("Design Rationale" in row for row in rows)
        assert all("Operating Rationale" in row for row in rows)


class TestRiskInventoryExcelExport:
    def test_export_bytes_contains_required_sheets(self):
        data = risk_inventory_excel_bytes(load_demo_risk_inventory())
        assert len(data) > 1000

    def test_export_creates_expected_sheets(self, tmp_path):
        path = export_risk_inventory_to_excel(load_demo_risk_inventory(), tmp_path / "risk_inventory.xlsx")
        wb = openpyxl.load_workbook(path)
        assert {
            "Executive Summary",
            "BU Risk Heatmap",
            "Risk Inventory",
            "Risk Statements and Root Causes",
            "Control Coverage and Gaps",
            "Synthetic Control Recs",
            "Residual Risk Mgmt Actions",
            "KRI Program",
            "Source Trace Config Snapshot",
            "Inherent Risk Assessment",
            "Control Mapping",
            "Control Effectiveness",
            "Residual Risk Assessment",
            "Review and Challenge",
            "Scoring Matrices",
            "Configuration Snapshot",
            "Validation Findings",
        }.issubset(set(wb.sheetnames))
        assert wb["Risk Inventory"].data_validations.count > 0

    def test_workspace_export_creates_demo_artifact_sheets(self):
        workspace = load_demo_workspace()
        wb = build_risk_inventory_workspace_workbook(workspace)

        assert {
            "Cover",
            "Executive Summary",
            "BU Risk Heatmap",
            "BU Risk Breakdown",
            "Process Risk Inventory",
            "Risk Detail Dossier",
            "Control Gap Summary",
            "Synthetic Control Recs",
            "KRI Dashboard",
            "Review & Challenge",
            "Reviewer Decision Log",
            "Source Trace",
            "Config Snapshot",
        }.issubset(set(wb.sheetnames))
        process_ids = {
            row[1]
            for row in wb["Process Risk Inventory"].iter_rows(min_row=2, values_only=True)
            if row and row[1]
        }
        business_units = {
            row[0]
            for row in wb["Executive Summary"].iter_rows(min_row=2, values_only=True)
            if row and row[0]
        }
        assert len(process_ids) == 10
        assert len(business_units) == 5

    def test_workspace_export_has_formatting_validations_and_trace(self):
        workspace = load_demo_workspace()
        decision = ReviewDecision(
            risk_id=workspace.runs[0].records[0].risk_id,
            reviewer="Senior Risk Reviewer",
            review_status=ReviewStatus.APPROVED,
            approval_status=ApprovalStatus.APPROVED,
            challenge_comments="Approved after evidence review.",
            reviewer_rationale="Scoring is supported by configured evidence.",
            final_approved_value="Approve",
        )
        wb = build_risk_inventory_workspace_workbook(workspace, [decision])

        assert wb["Cover"]["A1"].value == "Risk Inventory Builder"
        assert wb["Cover"]["A1"].fill.fgColor.rgb in {"00161616", "FF161616"}
        assert wb["Review & Challenge"].data_validations.count > 0
        assert wb["Reviewer Decision Log"].data_validations.count > 0
        assert wb["KRI Dashboard"].max_row > 1
        assert wb["Source Trace"].max_row > 1
        assert wb["Config Snapshot"].max_row > 1
        heat_values = [
            cell.fill.fgColor.rgb
            for row in wb["BU Risk Heatmap"].iter_rows(min_row=2)
            for cell in row
            if cell.fill.fill_type == "solid"
        ]
        assert heat_values
        decisions = [
            row
            for row in wb["Reviewer Decision Log"].iter_rows(min_row=2, values_only=True)
            if row and row[0] == decision.risk_id
        ]
        assert decisions and decisions[0][3] == "Senior Risk Reviewer"

    def test_workspace_export_bytes_contains_artifact(self):
        data = risk_inventory_workspace_excel_bytes(load_demo_workspace())
        assert len(data) > 2000

    def test_hitl_review_workbook_has_review_assets(self):
        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None

        wb = build_hitl_review_workbook(run, workspace)

        assert {
            "HITL Cover",
            "Validation Queue",
            "Review Checklist",
            "Rationale Breakdown",
            "Control Suggestions",
            "Evidence KRI Trace",
            "Reviewer Decision Log",
        }.issubset(set(wb.sheetnames))
        assert wb["HITL Cover"]["A2"].value == "Human-in-the-Loop Review Workbook"
        assert wb["Validation Queue"].data_validations.count > 0
        assert wb["Review Checklist"].max_row > len(run.records)
        assert wb["Rationale Breakdown"].max_row == len(run.records) + 1
        assert wb["Reviewer Decision Log"].data_validations.count > 0

    def test_hitl_review_excel_bytes_contains_workbook(self):
        workspace = load_demo_workspace()
        run = workspace.run_for_process("PROC-PAY-EXCEPTION")
        assert run is not None

        data = risk_inventory_review_excel_bytes(run, workspace)
        wb = openpyxl.load_workbook(BytesIO(data))

        assert len(data) > 2000
        assert "Review Checklist" in wb.sheetnames
        assert "Final Decision" in [cell.value for cell in wb["Validation Queue"][1]]

    def test_review_decision_applied_to_export_run(self):
        run = load_demo_risk_inventory()
        decision = ReviewDecision(
            risk_id=run.records[0].risk_id,
            reviewer="Senior Risk Reviewer",
            review_status=ReviewStatus.APPROVED,
            approval_status=ApprovalStatus.APPROVED,
            challenge_comments="Approved after evidence review.",
            reviewer_rationale="Scoring is supported by the fixture evidence.",
            final_approved_value="Residual rating approved",
        )

        updated = apply_review_decisions(run, [decision])
        review = updated.records[0].review_challenges[0]

        assert review.reviewer == "Senior Risk Reviewer"
        assert review.review_status == ReviewStatus.APPROVED
        assert review.approval_status == ApprovalStatus.APPROVED
        assert review.final_approved_value == "Residual rating approved"

    def test_streamlit_download_keys_include_location(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        run = load_demo_risk_inventory()
        calls = []

        monkeypatch.setattr(risk_inventory_tab, "risk_inventory_excel_bytes", lambda received_run: b"xlsx")

        def fake_download_button(label, **kwargs):
            calls.append({"label": label, **kwargs})
            return False

        monkeypatch.setattr(risk_inventory_tab.st, "download_button", fake_download_button)

        risk_inventory_tab._download_export(run, "overview")
        risk_inventory_tab._download_export(run, "executive")

        keys = [call["key"] for call in calls]
        assert keys == [f"ri_xlsx_overview_{run.run_id}", f"ri_xlsx_executive_{run.run_id}"]
        assert len(set(keys)) == 2

    def test_review_tab_download_uses_hitl_workbook(self, monkeypatch):
        from controlnexus.ui import risk_inventory_tab

        run = load_demo_risk_inventory()
        calls = []

        monkeypatch.setattr(
            risk_inventory_tab,
            "risk_inventory_review_excel_bytes",
            lambda received_run, workspace, decisions: b"hitl-xlsx",
        )

        def fake_download_button(label, **kwargs):
            calls.append({"label": label, **kwargs})
            return False

        monkeypatch.setattr(risk_inventory_tab.st, "download_button", fake_download_button)
        monkeypatch.setattr(risk_inventory_tab.st, "caption", lambda *args, **kwargs: None)

        risk_inventory_tab._download_review_workbook(run)

        assert calls[0]["label"] == "Download HITL Review Workbook"
        assert calls[0]["key"] == f"ri_review_xlsx_{run.run_id}"
        assert calls[0]["file_name"] == f"{run.run_id}_hitl_review_workbook.xlsx"
