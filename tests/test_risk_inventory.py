"""Tests for Risk Inventory Builder."""

from __future__ import annotations

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
from controlnexus.risk_inventory.demo import load_demo_risk_inventory, load_demo_workspace
from controlnexus.risk_inventory.document_ingest import analyze_process_document
from controlnexus.risk_inventory.export import export_risk_inventory_to_excel, risk_inventory_excel_bytes
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
    RiskRating,
)
from controlnexus.risk_inventory.taxonomy import load_risk_inventory_taxonomy
from controlnexus.risk_inventory.validator import RiskInventoryValidator


class TestRiskInventoryConfig:
    def test_config_loads(self):
        loader = MatrixConfigLoader()
        assert loader.impact_scales()["dimensions"]
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

        assert "seven aged exceptions" in cyber.likelihood_assessment.rationale
        assert cyber.residual_risk.management_response.recommended_action.startswith("Accelerate closure")
        assert any(metric.metric_name == "access review exceptions" and metric.metric_value == "7" for metric in cyber.exposure_metrics)
        assert any(reference.evidence_id == "PAYEX-EVID-003" for reference in cyber.evidence_references)
        assert run.run_manifest["evidence_metric_count"] >= 20
        assert "one high residual access risk" in run.executive_summary.headline

    def test_demo_requires_no_llm_and_validates(self):
        run = load_demo_risk_inventory()
        assert run.run_manifest["llm_required"] is False
        findings = RiskInventoryValidator().validate_run(run)
        assert all(finding.severity.value != "error" for finding in findings)

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


class TestRiskInventoryControlMappingUiHelpers:
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


class TestRiskInventoryExcelExport:
    def test_export_bytes_contains_required_sheets(self):
        data = risk_inventory_excel_bytes(load_demo_risk_inventory())
        assert len(data) > 1000

    def test_export_creates_expected_sheets(self, tmp_path):
        path = export_risk_inventory_to_excel(load_demo_risk_inventory(), tmp_path / "risk_inventory.xlsx")
        wb = openpyxl.load_workbook(path)
        assert {
            "Executive Summary",
            "Risk Inventory",
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
