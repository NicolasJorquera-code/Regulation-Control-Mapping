"""Shared pytest fixtures for ControlNexus tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.config import load_section_profile, load_standards, load_taxonomy_catalog, load_placement_methods
from controlnexus.core.models import SectionProfile, TaxonomyCatalog
from controlnexus.core.state import FinalControlRecord


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def config_dir(project_root: Path) -> Path:
    return project_root / "config"


@pytest.fixture
def taxonomy_path(config_dir: Path) -> Path:
    return config_dir / "taxonomy.yaml"


@pytest.fixture
def taxonomy_catalog(taxonomy_path: Path) -> TaxonomyCatalog:
    return load_taxonomy_catalog(taxonomy_path)


@pytest.fixture
def section_4_profile(config_dir: Path) -> SectionProfile:
    return load_section_profile(config_dir / "sections" / "section_4.yaml")


@pytest.fixture
def standards(config_dir: Path) -> dict:
    return load_standards(config_dir / "standards.yaml")


@pytest.fixture
def placement_methods(config_dir: Path) -> dict:
    return load_placement_methods(config_dir / "placement_methods.yaml")


@pytest.fixture
def sample_controls() -> list[FinalControlRecord]:
    """Build a small set of sample FinalControlRecord objects for testing."""
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
            validator_retries=0,
            validator_failures=[],
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
            validator_retries=0,
            validator_failures=[],
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
            validator_retries=0,
            validator_failures=[],
            evidence="Approval log with digital signature retained in SAP",
        ),
        FinalControlRecord(
            control_id="CTRL-0901-REC-001",
            hierarchy_id="9.1.1.1",
            leaf_name="Perform general accounting",
            control_type="Reconciliation",
            selected_level_1="Detective",
            selected_level_2="Reconciliation",
            business_unit_id="BU-011",
            business_unit_name="Finance/Accounting",
            who="Senior Accountant",
            what="Reconciles intercompany balances",
            when="Monthly within 5 business days of month-end",
            frequency="Monthly",
            where="Oracle EBS General Ledger",
            why="Prevent undetected intercompany discrepancies",
            full_description=(
                "Senior Accountant reconciles intercompany balances monthly within 5 "
                "business days of month-end in Oracle EBS General Ledger to prevent "
                "undetected intercompany discrepancies."
            ),
            quality_rating="Satisfactory",
            validator_passed=True,
            validator_retries=0,
            validator_failures=[],
            evidence="Reconciliation worksheet approved by Controller retained in SharePoint",
        ),
        FinalControlRecord(
            control_id="CTRL-0401-THR-002",
            hierarchy_id="4.1.2.1",
            leaf_name="Seek sourcing opportunities",
            control_type="Third Party Due Diligence",
            selected_level_1="Preventive",
            selected_level_2="Third Party Due Diligence",
            business_unit_id="BU-015",
            business_unit_name="Third Party Risk Management",
            who="Control Owner",
            what="Reviews vendor performance",
            when="As needed",
            frequency="Other",
            where="Enterprise System",
            why="Risk management",
            full_description="Control Owner reviews vendor performance as needed.",
            quality_rating="Needs Improvement",
            validator_passed=False,
            validator_retries=2,
            validator_failures=["VAGUE_WHEN", "WORD_COUNT_OUT_OF_RANGE"],
            evidence="Documentation on file",
        ),
    ]
