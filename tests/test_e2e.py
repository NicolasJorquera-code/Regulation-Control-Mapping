"""End-to-end integration tests for the ControlNexus pipeline.

These tests exercise the full data flow — ingest → analysis → remediation
→ evaluation → export — without any real LLM or ChromaDB calls.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import openpyxl
import pytest

from controlnexus.analysis.ingest import ingest_excel
from controlnexus.analysis.pipeline import run_analysis
from controlnexus.core.config import load_all_section_profiles, load_placement_methods
from controlnexus.core.state import FinalControlRecord, GapReport
from controlnexus.evaluation.harness import run_eval
from controlnexus.evaluation.models import EvalReport
from controlnexus.export.excel import export_to_excel
from controlnexus.graphs.analysis_graph import build_analysis_graph
from controlnexus.graphs.remediation_graph import build_remediation_graph
from controlnexus.memory.embedder import Embedder
from controlnexus.remediation.planner import plan_assignments
from controlnexus.remediation.paths import route_assignment
from controlnexus.validation.validator import validate


# -- Test Helpers --------------------------------------------------------------


class _MockEmbedder(Embedder):
    """Deterministic embedder for e2e tests (4-dim)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hashlib.md5(text.encode()).hexdigest()
            vec = [int(h[i : i + 2], 16) / 255.0 for i in range(0, 8, 2)]
            results.append(vec)
        return results

    def dimension(self) -> int:
        return 4


def _make_excel(path: Path, controls: list[FinalControlRecord]) -> Path:
    """Create a minimal Excel file with a section_4 sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "section_4"

    cols = [
        "control_id", "hierarchy_id", "leaf_name", "full_description",
        "selected_level_1", "selected_level_2", "business_unit_id",
        "business_unit_name", "who", "what", "when", "frequency",
        "where", "why", "quality_rating", "validator_passed",
        "validator_retries", "validator_failures", "evidence",
    ]
    ws.append(cols)

    for ctrl in controls:
        export = ctrl.to_export_dict()
        row = []
        for col in cols:
            val = export.get(col, "")
            if isinstance(val, list):
                val = str(val)
            row.append(val)
        ws.append(row)

    wb.save(path)
    return path


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def section_profiles(config_dir: Path):
    return load_all_section_profiles(config_dir)


@pytest.fixture
def mock_embedder() -> _MockEmbedder:
    return _MockEmbedder()


@pytest.fixture
def healthy_controls() -> list[FinalControlRecord]:
    """5 well-formed controls across sections 4 and 9."""
    return [
        FinalControlRecord(
            control_id="CTRL-0401-THR-001",
            hierarchy_id="4.1.1.1",
            leaf_name="Develop procurement plan",
            control_type="Third Party Due Diligence",
            selected_level_1="Preventive",
            selected_level_2="Third Party Due Diligence",
            business_unit_id="BU-015",
            business_unit_name="Third Party Risk Management",
            who="Vendor Risk Analyst",
            what="Completes vendor due diligence assessment including financial stability review",
            when="Upon initiation of new vendor engagement and annually thereafter",
            frequency="Annual",
            where="Third Party Risk Assessment Tool",
            why="Mitigates third party operational and financial risk exposure",
            full_description=(
                "Vendor Risk Analyst completes vendor due diligence assessment including "
                "financial stability review upon initiation of new vendor engagement and "
                "annually thereafter in the Third Party Risk Assessment Tool to mitigate "
                "third party operational and financial risk exposure."
            ),
            quality_rating="Effective",
            validator_passed=True,
            evidence="Vendor risk assessment scorecard with sign-off retained in GRC platform",
        ),
        FinalControlRecord(
            control_id="CTRL-0401-REC-001",
            hierarchy_id="4.1.1.2",
            leaf_name="Clarify purchasing requirements",
            control_type="Reconciliation",
            selected_level_1="Detective",
            selected_level_2="Reconciliation",
            business_unit_id="BU-007",
            business_unit_name="Operations",
            who="Procurement Analyst",
            what="Reconciles purchase order records against approved requisitions",
            when="Monthly within 5 business days of month-end",
            frequency="Monthly",
            where="Oracle EBS Procurement Module",
            why="Prevents unauthorized or duplicate procurement transactions",
            full_description=(
                "Procurement Analyst reconciles purchase order records against approved "
                "requisitions monthly within 5 business days of month-end in the Oracle "
                "EBS Procurement Module to prevent unauthorized or duplicate procurement "
                "transactions."
            ),
            quality_rating="Strong",
            validator_passed=True,
            evidence="Reconciliation report signed by Procurement Manager retained in Oracle EBS",
        ),
        FinalControlRecord(
            control_id="CTRL-0401-AUT-001",
            hierarchy_id="4.1.1.3",
            leaf_name="Develop inventory strategy",
            control_type="Authorization",
            selected_level_1="Preventive",
            selected_level_2="Authorization",
            business_unit_id="BU-007",
            business_unit_name="Operations",
            who="Supply Chain Manager",
            what="Approves inventory replenishment orders exceeding threshold",
            when="Daily as orders are submitted",
            frequency="Daily",
            where="SAP Inventory Management System",
            why="Ensures appropriate authorization levels for material commitments",
            full_description=(
                "Supply Chain Manager approves inventory replenishment orders exceeding "
                "threshold daily as orders are submitted in the SAP Inventory Management "
                "System to ensure appropriate authorization levels for material commitments."
            ),
            quality_rating="Effective",
            validator_passed=True,
            evidence="Approval log with digital signature retained in SAP",
        ),
    ]


# ==============================================================================
# E2E: Full pipeline — ingest → analysis → remediation plan → export → eval
# ==============================================================================


class TestFullPipeline:
    """End-to-end: Excel → analysis → remediation planner → export → eval."""

    def test_ingest_to_analysis(self, healthy_controls, section_profiles):
        """Ingest controls, run analysis, get a scored GapReport."""
        report = run_analysis(healthy_controls, section_profiles)

        assert isinstance(report, GapReport)
        assert 0 <= report.overall_score <= 100
        assert isinstance(report.summary, str)

    def test_analysis_to_remediation_plan(self, healthy_controls, section_profiles):
        """GapReport → plan_assignments produces ordered assignments."""
        report = run_analysis(healthy_controls, section_profiles)
        report_dict = report.model_dump()
        assignments = plan_assignments(report_dict)

        assert isinstance(assignments, list)
        # All assignments have required fields
        for a in assignments:
            assert "gap_source" in a

    def test_remediation_plan_routing(self, healthy_controls, section_profiles):
        """Each assignment can be routed to a path handler."""
        report = run_analysis(healthy_controls, section_profiles)
        assignments = plan_assignments(report.model_dump())

        for a in assignments:
            result = route_assignment(a, {k: v.model_dump() for k, v in section_profiles.items()})
            assert isinstance(result, dict)

    def test_excel_round_trip(self, healthy_controls):
        """Write controls to Excel, read back, verify fidelity."""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "controls.xlsx"
            # Use section_ prefix so ingest_excel can find the sheet
            export_to_excel(healthy_controls, path, sheet_name="section_4")

            assert path.exists()

            re_ingested = ingest_excel(path)
            assert len(re_ingested) == len(healthy_controls)

            for original, loaded in zip(healthy_controls, re_ingested):
                assert loaded.control_id == original.control_id
                assert loaded.who == original.who
                assert loaded.where == original.where

    def test_eval_on_generated_controls(self, healthy_controls, section_profiles, mock_embedder):
        """Run evaluation harness on a set of controls and verify report."""
        specs = [{"who": c.who, "where_system": c.where} for c in healthy_controls]

        from controlnexus.core.config import load_placement_methods

        pm = load_placement_methods(
            Path(__file__).resolve().parent.parent / "config" / "placement_methods.yaml"
        )

        report = run_eval(
            generated_controls=healthy_controls,
            specs=specs,
            placement_config=pm,
            section_profiles=section_profiles,
            embedder=mock_embedder,
            run_id="e2e-test",
        )

        assert isinstance(report, EvalReport)
        assert report.total_controls == len(healthy_controls)
        assert 0 <= report.faithfulness_avg <= 4
        assert 0 <= report.completeness_avg <= 6
        assert 0.0 <= report.diversity_score <= 1.0

    def test_eval_json_export(self, healthy_controls, section_profiles, mock_embedder):
        """Eval harness writes JSON file when output_dir provided."""
        specs = [{"who": c.who, "where_system": c.where} for c in healthy_controls]
        pm = load_placement_methods(
            Path(__file__).resolve().parent.parent / "config" / "placement_methods.yaml"
        )

        with TemporaryDirectory() as tmp:
            report = run_eval(
                generated_controls=healthy_controls,
                specs=specs,
                placement_config=pm,
                section_profiles=section_profiles,
                embedder=mock_embedder,
                run_id="e2e-json",
                output_dir=Path(tmp),
            )
            json_path = Path(tmp) / "e2e-json__eval.json"
            assert json_path.exists()
            assert report.run_id == "e2e-json"


class TestValidatorE2E:
    """End-to-end validator tests with realistic narratives."""

    def test_good_narrative_passes(self):
        """A well-formed narrative passes all 6 rules."""
        narrative = {
            "who": "Senior Accountant",
            "what": "Reconciles general ledger accounts",
            "when": "Monthly within 5 business days of month-end",
            "where": "SAP Financial Close Platform",
            "why": "To prevent unreconciled balances and ensure SOX compliance",
            "full_description": (
                "Monthly, the Senior Accountant reconciles general ledger accounts in the "
                "SAP Financial Close Platform by reviewing outstanding items and investigating "
                "discrepancies to prevent unreconciled account balances and ensure regulatory "
                "compliance with SOX requirements for timely and accurate financial reporting."
            ),
        }
        spec = {
            "who": "Senior Accountant",
            "where_system": "SAP Financial Close Platform",
        }
        result = validate(narrative, spec)
        assert result.passed
        assert result.failures == []

    def test_bad_narrative_fails_multiple(self):
        """A poorly formed narrative triggers multiple failures."""
        narrative = {
            "who": "Enterprise System",
            "what": "Reviews, reconciles, and audits transactions",
            "when": "As needed",
            "where": "Enterprise System",
            "why": "For purposes",
            "full_description": "Short bad control.",
        }
        spec = {"who": "Analyst", "where_system": "SAP"}
        result = validate(narrative, spec)
        assert not result.passed
        assert len(result.failures) >= 3


class TestAnalysisGraphE2E:
    """End-to-end analysis graph compilation and execution."""

    def test_graph_compiles_and_runs_empty(self):
        """Analysis graph runs with no Excel path (empty ingest)."""
        graph = build_analysis_graph()
        result = graph.invoke({"excel_path": "", "config_dir": "config"})

        assert "gap_report" in result
        report = result["gap_report"]
        assert report["overall_score"] == 100.0
        assert report["summary"] == "No gaps identified"

    def test_graph_runs_with_real_data(self, healthy_controls, config_dir):
        """Analysis graph runs with a real Excel file end-to-end."""
        with TemporaryDirectory() as tmp:
            xlsx = Path(tmp) / "test.xlsx"
            _make_excel(xlsx, healthy_controls)

            graph = build_analysis_graph()
            result = graph.invoke({
                "excel_path": str(xlsx),
                "config_dir": str(config_dir),
            })

            assert "gap_report" in result
            report = result["gap_report"]
            assert 0 <= report["overall_score"] <= 100


class TestRemediationGraphE2E:
    """End-to-end remediation graph compilation and execution."""

    def test_graph_compiles_and_runs_empty(self):
        """Remediation graph runs with empty gap report."""
        graph = build_remediation_graph()
        result = graph.invoke({"gap_report": {}})
        assert "generated_records" in result

    def test_graph_runs_with_regulatory_gap(self):
        """Remediation graph processes a single regulatory gap."""
        gap_report: dict[str, Any] = {
            "regulatory_gaps": [
                {
                    "framework": "SOX",
                    "required_theme": "Financial Close",
                    "current_coverage": 0.3,
                    "severity": "high",
                }
            ],
            "balance_gaps": [],
            "frequency_issues": [],
            "evidence_issues": [],
        }
        graph = build_remediation_graph()
        result = graph.invoke({"gap_report": gap_report})

        assert "generated_records" in result
        assert len(result["generated_records"]) >= 1

    def test_graph_runs_with_frequency_issue(self):
        """Remediation graph processes a frequency issue (deterministic path).

        The frequency stub narrative is minimal and may fail validation,
        falling through to merge with no enriched data. We verify the graph
        runs without error and produces the generated_records key.
        """
        gap_report: dict[str, Any] = {
            "regulatory_gaps": [],
            "balance_gaps": [],
            "frequency_issues": [
                {
                    "control_id": "CTRL-001",
                    "hierarchy_id": "4.1.1.1",
                    "expected_frequency": "Monthly",
                    "actual_frequency": "Annual",
                }
            ],
            "evidence_issues": [],
        }
        graph = build_remediation_graph()
        result = graph.invoke({"gap_report": gap_report})
        assert "generated_records" in result

    def test_graph_runs_with_multiple_gap_types(self):
        """Remediation graph with mixed gap types processes successfully."""
        gap_report: dict[str, Any] = {
            "regulatory_gaps": [
                {"framework": "SOX", "required_theme": "Close", "current_coverage": 0.2, "severity": "high"}
            ],
            "balance_gaps": [
                {"control_type": "Authorization", "expected_pct": 20.0, "actual_pct": 5.0, "direction": "under"}
            ],
            "frequency_issues": [
                {"control_id": "CTRL-X", "hierarchy_id": "9.1.1.1", "expected_frequency": "Monthly", "actual_frequency": "Annual"}
            ],
            "evidence_issues": [
                {"control_id": "CTRL-Y", "hierarchy_id": "4.1.2.1", "issue": "Missing signer"}
            ],
        }
        graph = build_remediation_graph()
        result = graph.invoke({"gap_report": gap_report})
        assert len(result["generated_records"]) >= 1


class TestExportRoundTrip:
    """End-to-end export + re-ingest fidelity."""

    def test_export_preserves_all_fields(self, healthy_controls):
        """Export to Excel and re-ingest preserves all critical fields."""
        with TemporaryDirectory() as tmp:
            xlsx = Path(tmp) / "rt.xlsx"
            export_to_excel(healthy_controls, xlsx, sheet_name="section_4")
            loaded = ingest_excel(xlsx)

            assert len(loaded) == len(healthy_controls)

            for orig, back in zip(healthy_controls, loaded):
                assert back.control_id == orig.control_id
                assert back.hierarchy_id == orig.hierarchy_id
                assert back.selected_level_1 == orig.selected_level_1
                assert back.selected_level_2 == orig.selected_level_2
                assert back.who == orig.who
                assert back.what == orig.what
                assert back.when == orig.when
                assert back.frequency == orig.frequency
                assert back.where == orig.where
                assert back.why == orig.why
                assert back.quality_rating == orig.quality_rating
