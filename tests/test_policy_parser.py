"""
Tests for the Policy / Procedure ingest path (Phase 2 hybrid model).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from regrisk.core.constants import (
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_PROCEDURE_STEP,
)
from regrisk.ingest.policy_parser import (
    SOURCE_INVENTORY_SHEET,
    detect_source_inventory,
    group_policy_obligations,
    parse_policy_excel,
)


def _write_inventory(path: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SOURCE_INVENTORY_SHEET, index=False)
    return path


@pytest.fixture
def policy_workbook(tmp_path: Path) -> Path:
    rows = [
        {
            "Source_ID": "POL-CRED-014",
            "Source_Type": "Policy_Requirement",
            "Source_Title": "Credit Concentration Limits",
            "Source_Document_Name": "Enterprise Credit Risk Policy v3.2",
            "Source_Section": "Section 4.2",
            "Source_Text": "Single-name exposures shall not exceed 10% of Tier 1.",
            "Source_Owner": "Chief Credit Officer",
            "Business_Unit": "Wholesale Banking",
            "Effective_Date": "2025-07-01",
            "Review_Date": "2026-07-01",
            "Version": "3.2",
            "Parent_Source_ID": "",
            "Requirement_Type": "Threshold",
            "Source_Confidence": 0.95,
            "Regulation_Links": "12 CFR 252.34",
        },
        {
            "Source_ID": "POL-CRED-014.P1",
            "Source_Type": "Procedure_Step",
            "Source_Title": "Concentration Limit Monitoring",
            "Source_Document_Name": "Enterprise Credit Risk Policy v3.2",
            "Source_Text": "Compliance reviews exceptions weekly.",
            "Source_Owner": "Compliance Officer",
            "Business_Unit": "Wholesale Banking",
            "Parent_Source_ID": "POL-CRED-014",
            "Procedure_ID": "PROC-CRED-014.P1",
            "Procedure_Title": "Weekly Exception Review",
            "Procedure_Step": "Step 1: Pull exception report; Step 2: review with desk head.",
            "Source_Confidence": 0.9,
        },
    ]
    return _write_inventory(tmp_path / "policies.xlsx", rows)


def test_detect_source_inventory_true(policy_workbook: Path):
    assert detect_source_inventory(str(policy_workbook)) is True


def test_detect_source_inventory_false_for_missing_sheet(tmp_path: Path):
    other = tmp_path / "other.xlsx"
    pd.DataFrame({"X": [1]}).to_excel(other, sheet_name="Other", index=False)
    assert detect_source_inventory(str(other)) is False


def test_parse_policy_excel_emits_obligations(policy_workbook: Path):
    name, obligations = parse_policy_excel(str(policy_workbook))
    assert name == "Enterprise Credit Risk Policy v3.2"
    assert len(obligations) == 2
    cit_to_ob = {o.citation: o for o in obligations}

    pol = cit_to_ob["POL-CRED-014"]
    assert pol.source_type == SOURCE_TYPE_POLICY_REQUIREMENT
    assert pol.source_id == "POL-CRED-014"
    assert pol.parent_source_id is None
    assert pol.requirement_type == "Threshold"
    assert pol.source_confidence == 0.95
    assert pol.source_metadata["regulation_links"] == ["12 CFR 252.34"]
    assert pol.source_metadata["source_owner"] == "Chief Credit Officer"

    proc = cit_to_ob["POL-CRED-014.P1"]
    assert proc.source_type == SOURCE_TYPE_PROCEDURE_STEP
    assert proc.parent_source_id == "POL-CRED-014"
    # Procedure abstract should default to its operational step text
    assert "Step 1" in proc.abstract


def test_group_policy_obligations_buckets_by_parent(policy_workbook: Path):
    _, obligations = parse_policy_excel(str(policy_workbook))
    groups = group_policy_obligations(obligations)
    assert len(groups) == 1
    g = groups[0]
    assert g.obligation_count == 2
    # Parent (policy) should be first in the group for classifier context
    assert g.obligations[0].source_type == SOURCE_TYPE_POLICY_REQUIREMENT


def test_blank_source_id_rows_are_skipped(tmp_path: Path):
    rows = [
        {
            "Source_ID": "",
            "Source_Type": "Policy_Requirement",
            "Source_Title": "Blank",
            "Source_Text": "Should be skipped.",
        },
        {
            "Source_ID": "POL-X-001",
            "Source_Type": "Policy_Requirement",
            "Source_Title": "Real",
            "Source_Text": "Should be kept.",
        },
    ]
    wb = _write_inventory(tmp_path / "p.xlsx", rows)
    _, obligations = parse_policy_excel(str(wb))
    assert [o.citation for o in obligations] == ["POL-X-001"]
