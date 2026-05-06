"""Tests for Modular Knowledge Base tab data preparation."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.domain_config import load_domain_config
from controlnexus.ui.modular_tab import (
    prepare_business_units_table,
    prepare_control_taxonomy_tables,
    prepare_processes_table,
    prepare_risk_taxonomy_tables,
)


PROFILES_DIR = Path(__file__).resolve().parents[2] / "config" / "profiles"
BANKING_STANDARD = PROFILES_DIR / "banking_standard.yaml"


def test_banking_standard_modular_kb_row_counts() -> None:
    config = load_domain_config(BANKING_STANDARD)

    business_unit_rows = prepare_business_units_table(config)
    process_rows = prepare_processes_table(config)
    risk_level_1_rows, risk_level_2_rows = prepare_risk_taxonomy_tables(config)
    control_tables = prepare_control_taxonomy_tables(config)

    assert len(business_unit_rows) == 17
    assert business_unit_rows[0]["Head"] == "Head of Retail Banking"
    assert business_unit_rows[0]["Employees"] == "—"

    assert len(process_rows) == 13
    assert len(risk_level_1_rows) == 9
    assert len(risk_level_2_rows) == 114

    assert len(control_tables["control_types"]) == 25
    assert len(control_tables["placements"]) == 3
    assert len(control_tables["methods"]) == 3


@pytest.mark.parametrize(
    "profile_name",
    [
        "banking_standard.yaml",
        "community_bank_demo.yaml",
        "community_bank_pivot_demo.yaml",
        "healthcare_demo.yaml",
    ],
)
def test_modular_kb_data_prep_accepts_valid_profiles(profile_name: str) -> None:
    config = load_domain_config(PROFILES_DIR / profile_name)

    assert isinstance(prepare_business_units_table(config), list)
    assert isinstance(prepare_processes_table(config), list)
    assert isinstance(prepare_risk_taxonomy_tables(config), tuple)
    assert isinstance(prepare_control_taxonomy_tables(config), dict)
