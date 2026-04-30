"""Tests for DomainConfig model loading, validation, and computed properties."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.domain_config import (
    AffinityConfig,
    BusinessUnitConfig,
    ControlTypeConfig,
    DomainConfig,
    ProcessAreaConfig,
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
        assert config.narrative_field_names() == ["who", "what", "when", "where", "why", "full_description"]

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
        """Type codes in DomainConfig should match TYPE_CODE_MAP from constants.py for shared types."""
        from controlnexus.core.constants import TYPE_CODE_MAP

        dc_codes = config.type_code_map()
        for type_name, expected_code in TYPE_CODE_MAP.items():
            if type_name not in dc_codes:
                continue  # type exists in constants but not in this config profile
            assert dc_codes[type_name] == expected_code, (
                f"Code mismatch for '{type_name}': DomainConfig={dc_codes.get(type_name)}, legacy={expected_code}"
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
            assert len(ct.placement_categories) >= 1, f"Control type '{ct.name}' has no placement category"

    def test_section_registries_populated(self, config: DomainConfig):
        for pa in config.process_areas:
            assert len(pa.registry.roles) > 0, f"Section '{pa.id}' has no roles"
            assert len(pa.registry.systems) > 0, f"Section '{pa.id}' has no systems"

    def test_section_exemplars_present(self, config: DomainConfig):
        for pa in config.process_areas:
            assert len(pa.exemplars) >= 1, f"Section '{pa.id}' has no exemplars"


# ── Two-Tier Risk Taxonomy Tests ──────────────────────────────────────────────

PIVOT_DEMO = PROFILES_DIR / "community_bank_pivot_demo.yaml"


class TestTwoTierRiskTaxonomy:
    """Test new models: RiskLevel1Category, MitigationLink, ResolvedRisk."""

    def test_mitigation_link_creation(self):
        from controlnexus.core.domain_config import MitigationLink

        link = MitigationLink(control_type="Authorization", effectiveness=0.8, line_of_defense=2)
        assert link.control_type == "Authorization"
        assert link.effectiveness == 0.8
        assert link.line_of_defense == 2

    def test_mitigation_link_defaults(self):
        from controlnexus.core.domain_config import MitigationLink

        link = MitigationLink(control_type="Auth")
        assert link.effectiveness == 1.0
        assert link.line_of_defense is None

    def test_mitigation_link_frozen(self):
        from controlnexus.core.domain_config import MitigationLink

        link = MitigationLink(control_type="Auth")
        with pytest.raises(Exception):
            link.control_type = "Other"

    def test_risk_level1_category(self):
        from controlnexus.core.domain_config import RiskLevel1Category

        cat = RiskLevel1Category(
            name="Operational", code="OPS", definition="Operational risks",
            sub_groups=["IT", "Fraud", "People"],
        )
        assert cat.code == "OPS"
        assert len(cat.sub_groups) == 3

    def test_risk_catalog_entry_two_tier(self):
        from controlnexus.core.domain_config import MitigationLink, RiskCatalogEntry

        entry = RiskCatalogEntry(
            id="OPS-001", name="IT Failure",
            level_1="Operational", level_1_code="OPS", sub_group="IT",
            default_mitigating_links=[
                MitigationLink(control_type="Automated Rules", effectiveness=0.9),
            ],
            grounding="BCBS",
        )
        assert entry.level_1 == "Operational"
        assert entry.sub_group == "IT"
        assert len(entry.default_mitigating_links) == 1

    def test_risk_catalog_entry_legacy_coercion(self):
        """Legacy category + default_mitigating_types should coerce to new schema."""
        from controlnexus.core.domain_config import RiskCatalogEntry

        entry = RiskCatalogEntry(
            id="R-1", name="Test",
            category="Operational",
            default_mitigating_types=["Auth", "Rec"],
        )
        assert entry.level_1 == "Operational"
        assert len(entry.default_mitigating_links) == 2
        assert entry.default_mitigating_links[0].control_type == "Auth"

    def test_risk_instance_legacy_coercion(self):
        """Legacy mitigated_by_types should coerce to mitigating_links."""
        from controlnexus.core.domain_config import RiskInstance

        ri = RiskInstance(
            risk_id="R1",
            mitigated_by_types=["Authorization", "Reconciliation"],
        )
        assert len(ri.mitigating_links) == 2
        assert ri.mitigating_type_names == ["Authorization", "Reconciliation"]

    def test_risk_instance_direct_links(self):
        """Direct mitigating_links should work without coercion."""
        from controlnexus.core.domain_config import MitigationLink, RiskInstance

        ri = RiskInstance(
            risk_id="R1",
            mitigating_links=[
                MitigationLink(control_type="Auth", effectiveness=0.8),
            ],
        )
        assert len(ri.mitigating_links) == 1
        assert ri.mitigating_links[0].effectiveness == 0.8
        assert ri.mitigating_type_names == ["Auth"]

    def test_resolved_risk_frozen(self):
        from controlnexus.core.domain_config import ResolvedRisk

        rr = ResolvedRisk(
            risk_id="R1", risk_name="Test", level_1="Ops",
            severity=4, selected_control_type="Auth",
        )
        assert rr.severity == 4
        with pytest.raises(Exception):
            rr.severity = 5

    def test_process_config_apqc_migration(self):
        """Legacy apqc_section_id should migrate to domain_metadata."""
        from controlnexus.core.domain_config import ProcessConfig

        proc = ProcessConfig(
            id="P1", name="Test", apqc_section_id="4.0",
        )
        assert proc.domain_metadata == {"apqc_section_id": "4.0"}
        assert proc.hierarchy_id == "4.0"
        assert proc.effective_section_id == "4.0"

    def test_process_config_domain_metadata(self):
        """Direct domain_metadata should work."""
        from controlnexus.core.domain_config import ProcessConfig

        proc = ProcessConfig(
            id="P1", name="Test",
            domain_metadata={"apqc_section_id": "5.0", "custom": "val"},
            hierarchy_id="5.0",
        )
        assert proc.effective_section_id == "5.0"
        assert proc.domain_metadata["custom"] == "val"

    def test_bu_processes_computed(self):
        """BU.processes should be computed from ProcessConfig.owner_bu_ids."""
        from controlnexus.core.domain_config import ProcessConfig

        config = _minimal_config(
            business_units=[
                BusinessUnitConfig(id="BU-1", name="Retail"),
                BusinessUnitConfig(id="BU-2", name="Ops"),
            ],
            processes=[
                ProcessConfig(id="P1", name="Lending", owner_bu_ids=["BU-1"]),
                ProcessConfig(id="P2", name="Settlement", owner_bu_ids=["BU-1", "BU-2"]),
            ],
        )
        assert config.bu_processes("BU-1") == ["P1", "P2"]
        assert config.bu_processes("BU-2") == ["P2"]

    def test_pivot_demo_loads_with_legacy_fields(self):
        """community_bank_pivot_demo.yaml uses legacy fields and should load cleanly."""
        config = load_domain_config(PIVOT_DEMO)
        assert len(config.processes) == 2
        assert len(config.risk_catalog) == 3
        proc = config.get_process("PROC-LENDING")
        assert proc is not None
        assert proc.effective_section_id == "1.0"
        assert len(proc.risks) == 1
        assert proc.risks[0].mitigating_type_names == ["Authorization"]

    def test_cross_ref_validates_l1_categories(self):
        """Unknown level_1 in risk_catalog should be caught by validator."""
        from controlnexus.core.domain_config import RiskCatalogEntry, RiskLevel1Category

        with pytest.raises(ValueError, match="level_1.*not in declared categories"):
            _minimal_config(
                risk_level_1_categories=[
                    RiskLevel1Category(name="Operational", code="OPS", definition="ops"),
                ],
                risk_catalog=[
                    RiskCatalogEntry(id="R1", name="Test", level_1="Unknown"),
                ],
            )

    def test_cross_ref_validates_mitigating_links(self):
        """Unknown control type in default_mitigating_links should be caught."""
        from controlnexus.core.domain_config import MitigationLink, RiskCatalogEntry

        with pytest.raises(ValueError, match="unknown type.*Nonexistent"):
            _minimal_config(
                risk_catalog=[
                    RiskCatalogEntry(
                        id="R1", name="Test",
                        default_mitigating_links=[
                            MitigationLink(control_type="Nonexistent"),
                        ],
                    ),
                ],
            )


# ── Healthcare Fixture Tests ──────────────────────────────────────────────────

HEALTHCARE_DEMO = PROFILES_DIR / "healthcare_demo.yaml"


class TestHealthcareFixture:
    """Verify healthcare_demo.yaml loads and demonstrates domain-agnosticism."""

    def test_loads_without_error(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        assert config.name == "healthcare-demo"

    def test_has_non_banking_control_types(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        type_names = {ct.name for ct in config.control_types}
        assert "Access Control" in type_names
        assert "Clinical Review" in type_names
        assert "Reconciliation" not in type_names

    def test_processes_use_domain_metadata(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        ehr = config.get_process("PROC-EHR")
        assert ehr is not None
        assert ehr.domain_metadata.get("system_class") == "EHR"
        assert "apqc_section_id" not in ehr.domain_metadata

    def test_hierarchy_ids_are_non_apqc(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        for proc in config.processes:
            assert not proc.hierarchy_id[0].isdigit(), (
                f"Process {proc.id} hierarchy_id '{proc.hierarchy_id}' "
                f"looks APQC-like, should be domain-specific"
            )

    def test_risk_catalog_has_l1_categories(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        assert len(config.risk_level_1_categories) == 2
        cat_names = {c.name for c in config.risk_level_1_categories}
        assert "Regulatory Compliance" in cat_names
        assert "Operational" in cat_names

    def test_risk_mitigation_links_coerced(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        ehr = config.get_process("PROC-EHR")
        assert ehr is not None
        risk = ehr.risks[0]
        assert risk.mitigating_type_names == ["Access Control", "Audit Trail"]

    def test_bu_processes_computed(self):
        config = load_domain_config(HEALTHCARE_DEMO)
        clin_procs = config.bu_processes("BU-CLIN")
        assert "PROC-EHR" in clin_procs
        assert "PROC-MEDADMIN" in clin_procs

    def test_assignment_matrix_builds(self):
        from controlnexus.graphs.forge_modular_helpers import build_assignment_matrix

        config = load_domain_config(HEALTHCARE_DEMO)
        assignments = build_assignment_matrix(config, target_count=5)
        assert len(assignments) > 0
        for a in assignments:
            assert a["control_type"] in {"Access Control", "Audit Trail", "Clinical Review", "Incident Reporting"}


# ── DomainProfile Tests ───────────────────────────────────────────────────────


class TestDomainProfile:
    """Test DomainProfile and DomainProfileRegistry."""

    def test_profile_creation(self):
        from controlnexus.core.domain_profile import DomainProfile

        config = _minimal_config()
        profile = DomainProfile(name="test", config=config)
        assert profile.name == "test"
        assert profile.risk_catalog_size == 0
        assert profile.l1_category_count == 0

    def test_default_control_id_builder(self):
        from controlnexus.core.domain_profile import DefaultControlIdBuilder

        builder = DefaultControlIdBuilder()
        assert builder.build_id("4.1", "REC", 1) == "CTRL-0401-REC-001"
        assert builder.build_id("12.3", "AUT", 42) == "CTRL-1203-AUT-042"

    def test_registry_manual_register(self):
        from controlnexus.core.domain_profile import DomainProfile, DomainProfileRegistry

        config = _minimal_config()
        profile = DomainProfile(name="test", config=config)
        registry = DomainProfileRegistry()
        registry.register("test", profile)
        assert registry.get("test") is profile
        assert "test" in registry.available_domains

    def test_registry_get_unknown_returns_none(self):
        from controlnexus.core.domain_profile import DomainProfileRegistry

        registry = DomainProfileRegistry()
        assert registry.get("nonexistent") is None

    def test_registry_default_builder(self):
        from controlnexus.core.domain_profile import DomainProfileRegistry

        registry = DomainProfileRegistry()
        builder = registry.get_builder("anything")
        assert builder.build_id("1.0", "TST", 1) == "CTRL-0100-TST-001"
