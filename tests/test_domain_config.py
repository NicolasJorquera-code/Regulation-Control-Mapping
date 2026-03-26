"""Tests for DomainConfig model loading, validation, and computed properties."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.domain_config import (
    AffinityConfig,
    BusinessUnitConfig,
    ControlTypeConfig,
    DomainConfig,
    FrequencyTier,
    PlacementConfig,
    ProcessAreaConfig,
    RegistryConfig,
    RiskProfileConfig,
    load_domain_config,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"
COMMUNITY_BANK = PROFILES_DIR / "community_bank_demo.yaml"
BANKING_STANDARD = PROFILES_DIR / "banking_standard.yaml"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _minimal_config(**overrides) -> DomainConfig:
    """Build a minimal valid DomainConfig for testing."""
    defaults = {
        "control_types": [
            ControlTypeConfig(name="Authorization", definition="Approval step."),
        ],
    }
    defaults.update(overrides)
    return DomainConfig(**defaults)


# ── Loading Tests ─────────────────────────────────────────────────────────────


class TestDomainConfigLoading:
    """Test YAML -> DomainConfig parsing and validation."""

    def test_minimal_config_loads(self):
        config = load_domain_config(COMMUNITY_BANK)
        assert config.name == "community-bank-demo"
        assert len(config.control_types) == 3
        assert len(config.business_units) == 2
        assert len(config.process_areas) == 2

    def test_banking_standard_loads(self):
        config = load_domain_config(BANKING_STANDARD)
        assert config.name == "banking-standard"
        assert len(config.control_types) == 25
        assert len(config.business_units) == 17
        assert len(config.process_areas) == 13

    def test_empty_control_types_raises(self):
        with pytest.raises(Exception):
            DomainConfig(control_types=[])

    def test_unknown_bu_control_type_raises(self):
        with pytest.raises(ValueError, match="unknown control type"):
            DomainConfig(
                control_types=[ControlTypeConfig(name="Auth", definition="d")],
                business_units=[
                    BusinessUnitConfig(
                        id="BU-1",
                        name="Test",
                        key_control_types=["NonExistent"],
                    )
                ],
            )

    def test_unknown_placement_category_raises(self):
        with pytest.raises(ValueError, match="unknown placement"):
            DomainConfig(
                control_types=[
                    ControlTypeConfig(
                        name="Auth",
                        definition="d",
                        placement_categories=["Proactive"],
                    )
                ],
            )

    def test_unknown_frequency_tier_raises(self):
        with pytest.raises(ValueError, match="unknown frequency tier"):
            DomainConfig(
                control_types=[
                    ControlTypeConfig(
                        name="Auth",
                        definition="d",
                        min_frequency_tier="Hourly",
                    )
                ],
            )

    def test_unknown_bu_section_raises(self):
        with pytest.raises(ValueError, match="unknown section"):
            DomainConfig(
                control_types=[ControlTypeConfig(name="Auth", definition="d")],
                process_areas=[
                    ProcessAreaConfig(id="1.0", name="Section One"),
                ],
                business_units=[
                    BusinessUnitConfig(
                        id="BU-1",
                        name="Test",
                        primary_sections=["99.0"],
                    )
                ],
            )

    def test_unknown_affinity_type_raises(self):
        with pytest.raises(ValueError, match="unknown type"):
            DomainConfig(
                control_types=[ControlTypeConfig(name="Auth", definition="d")],
                process_areas=[
                    ProcessAreaConfig(
                        id="1.0",
                        name="Section One",
                        affinity=AffinityConfig(HIGH=["Nonexistent"]),
                    ),
                ],
            )

    def test_defaults_filled(self):
        config = _minimal_config()
        assert len(config.placements) == 3
        assert len(config.methods) == 3
        assert len(config.frequency_tiers) == 6
        assert len(config.narrative.fields) == 6
        assert len(config.quality_ratings) == 4

    def test_custom_narrative_fields(self):
        from controlnexus.core.domain_config import NarrativeConstraints, NarrativeField

        config = _minimal_config(
            narrative=NarrativeConstraints(
                fields=[
                    NarrativeField(name="who"),
                    NarrativeField(name="key_report"),
                ],
                word_count_min=20,
                word_count_max=100,
            )
        )
        assert config.narrative_field_names() == ["who", "key_report"]
        assert config.narrative.word_count_min == 20


# ── Computed Property Tests ───────────────────────────────────────────────────


class TestDomainConfigHelpers:
    """Test computed properties that replace hardcoded constants."""

    def test_type_code_map_uses_config_codes(self):
        config = _minimal_config(
            control_types=[
                ControlTypeConfig(name="Auth", definition="d", code="ATH"),
            ]
        )
        assert config.type_code_map() == {"Auth": "ATH"}

    def test_type_code_map_auto_generates_missing_codes(self):
        config = _minimal_config(
            control_types=[
                ControlTypeConfig(name="Reconciliation", definition="d"),
            ]
        )
        codes = config.type_code_map()
        assert codes["Reconciliation"]  # non-empty generated code
        assert len(codes["Reconciliation"]) <= 3

    def test_min_frequency_types_monthly(self):
        config = _minimal_config(
            control_types=[
                ControlTypeConfig(name="Rec", definition="d", min_frequency_tier="Monthly"),
                ControlTypeConfig(name="Auth", definition="d", min_frequency_tier="Quarterly"),
                ControlTypeConfig(name="Doc", definition="d"),
            ]
        )
        monthly_types = config.min_frequency_types("Monthly")
        assert monthly_types == {"Rec"}

    def test_min_frequency_types_quarterly(self):
        config = _minimal_config(
            control_types=[
                ControlTypeConfig(name="Rec", definition="d", min_frequency_tier="Monthly"),
                ControlTypeConfig(name="Auth", definition="d", min_frequency_tier="Quarterly"),
                ControlTypeConfig(name="Doc", definition="d"),
            ]
        )
        quarterly_types = config.min_frequency_types("Quarterly")
        assert quarterly_types == {"Rec", "Auth"}

    def test_section_ids(self):
        config = _minimal_config(
            process_areas=[
                ProcessAreaConfig(id="1.0", name="S1"),
                ProcessAreaConfig(id="2.0", name="S2"),
            ]
        )
        assert config.section_ids() == ["1.0", "2.0"]

    def test_get_process_area(self):
        config = _minimal_config(
            process_areas=[
                ProcessAreaConfig(id="1.0", name="Vision"),
            ]
        )
        pa = config.get_process_area("1.0")
        assert pa is not None
        assert pa.name == "Vision"

    def test_get_process_area_missing(self):
        config = _minimal_config()
        assert config.get_process_area("99.0") is None

    def test_placement_names(self):
        config = _minimal_config()
        assert config.placement_names() == ["Preventive", "Detective", "Contingency Planning"]

    def test_method_names(self):
        config = _minimal_config()
        assert config.method_names() == ["Automated", "Manual", "Automated with Manual Component"]

    def test_narrative_field_names(self):
        config = _minimal_config()
        assert config.narrative_field_names() == [
            "who", "what", "when", "where", "why", "full_description"
        ]

    def test_frequency_tier_rank(self):
        config = _minimal_config()
        assert config.frequency_tier_rank("Daily") == 1
        assert config.frequency_tier_rank("Monthly") == 3
        assert config.frequency_tier_rank("Annual") == 6
        assert config.frequency_tier_rank("Unknown") is None


# ── Banking Standard Parity Tests ─────────────────────────────────────────────


class TestBankingStandardParity:
    """Verify banking_standard.yaml reproduces the legacy hardcoded values."""

    @pytest.fixture()
    def config(self) -> DomainConfig:
        return load_domain_config(BANKING_STANDARD)

    def test_type_codes_match_legacy(self, config: DomainConfig):
        """Type codes in DomainConfig should match TYPE_CODE_MAP from constants.py."""
        from controlnexus.core.constants import TYPE_CODE_MAP

        dc_codes = config.type_code_map()
        for type_name, expected_code in TYPE_CODE_MAP.items():
            assert dc_codes.get(type_name) == expected_code, (
                f"Code mismatch for '{type_name}': "
                f"DomainConfig={dc_codes.get(type_name)}, legacy={expected_code}"
            )

    def test_monthly_types_match_legacy(self, config: DomainConfig):
        """min_frequency_types('Monthly') should match MONTHLY_OR_BETTER_TYPES."""
        from controlnexus.analysis.scanners import MONTHLY_OR_BETTER_TYPES

        dc_monthly = config.min_frequency_types("Monthly")
        assert dc_monthly == MONTHLY_OR_BETTER_TYPES

    def test_quarterly_types_include_monthly(self, config: DomainConfig):
        """min_frequency_types('Quarterly') should be a superset of monthly types."""
        from controlnexus.analysis.scanners import (
            MONTHLY_OR_BETTER_TYPES,
            QUARTERLY_OR_BETTER_TYPES,
        )

        dc_quarterly = config.min_frequency_types("Quarterly")
        expected = MONTHLY_OR_BETTER_TYPES | QUARTERLY_OR_BETTER_TYPES
        assert dc_quarterly == expected

    def test_all_sections_present(self, config: DomainConfig):
        ids = set(config.section_ids())
        assert len(ids) == 13

    def test_all_types_have_placement_category(self, config: DomainConfig):
        for ct in config.control_types:
            assert len(ct.placement_categories) >= 1, (
                f"Control type '{ct.name}' has no placement category"
            )

    def test_section_registries_populated(self, config: DomainConfig):
        for pa in config.process_areas:
            assert len(pa.registry.roles) > 0, f"Section '{pa.id}' has no roles"
            assert len(pa.registry.systems) > 0, f"Section '{pa.id}' has no systems"

    def test_section_exemplars_present(self, config: DomainConfig):
        for pa in config.process_areas:
            assert len(pa.exemplars) >= 1, f"Section '{pa.id}' has no exemplars"
