"""Tests for DomainConfig-aware tool implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.domain_config import (
    AffinityConfig,
    ControlTypeConfig,
    DomainConfig,
    PlacementConfig,
    ProcessAreaConfig,
    RegistryConfig,
    RiskProfileConfig,
    load_domain_config,
)
from controlnexus.tools.domain_tools import (
    build_domain_tool_executor,
    dc_frequency_lookup,
    dc_hierarchy_search,
    dc_memory_retrieval,
    dc_regulatory_lookup,
    dc_taxonomy_validator,
)

# ── Paths & Fixtures ─────────────────────────────────────────────────────────

PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"
COMMUNITY_BANK = PROFILES_DIR / "community_bank_demo.yaml"


@pytest.fixture
def config() -> DomainConfig:
    return load_domain_config(COMMUNITY_BANK)


@pytest.fixture
def minimal_config() -> DomainConfig:
    return DomainConfig(
        name="test",
        control_types=[
            ControlTypeConfig(
                name="Authorization",
                definition="Approval step",
                code="AUT",
                min_frequency_tier="Quarterly",
                placement_categories=["Preventive"],
            ),
            ControlTypeConfig(
                name="Reconciliation",
                definition="Record comparison",
                code="REC",
                min_frequency_tier="Monthly",
                placement_categories=["Detective"],
            ),
        ],
        placements=[
            PlacementConfig(name="Preventive"),
            PlacementConfig(name="Detective"),
        ],
        process_areas=[
            ProcessAreaConfig(
                id="1.0",
                name="Lending",
                domain="lending",
                risk_profile=RiskProfileConfig(multiplier=1.2),
                affinity=AffinityConfig(
                    HIGH=["Authorization"],
                    MEDIUM=["Reconciliation"],
                ),
                registry=RegistryConfig(
                    roles=["Loan Officer", "Credit Analyst", "Branch Manager"],
                    systems=["LOS", "Credit Platform"],
                    evidence_artifacts=["Loan form", "Credit report"],
                    event_triggers=["Application submitted"],
                    regulatory_frameworks=["SOX", "OCC Guidelines"],
                ),
            ),
        ],
    )


# ── Taxonomy Validator ────────────────────────────────────────────────────────


class TestDcTaxonomyValidator:
    def test_valid_pair(self, minimal_config):
        result = dc_taxonomy_validator("Preventive", "Authorization", config=minimal_config)
        assert result["valid"] is True
        assert result["suggestion"] is None

    def test_invalid_pair_suggests_correct(self, minimal_config):
        result = dc_taxonomy_validator("Preventive", "Reconciliation", config=minimal_config)
        assert result["valid"] is False
        assert result["suggestion"]["correct_level_1"] == "Detective"

    def test_unknown_type(self, minimal_config):
        result = dc_taxonomy_validator("Preventive", "Nonexistent", config=minimal_config)
        assert result["valid"] is False
        assert "Unknown" in result["suggestion"]["reason"]

    def test_with_real_config(self, config):
        result = dc_taxonomy_validator("Preventive", "Authorization", config=config)
        assert result["valid"] is True


# ── Regulatory Lookup ─────────────────────────────────────────────────────────


class TestDcRegulatoryLookup:
    def test_known_section(self, minimal_config):
        result = dc_regulatory_lookup("SOX", "1.0", config=minimal_config)
        assert result["section_id"] == "1.0"
        assert result["domain"] == "lending"
        assert "SOX" in result["required_themes"]
        assert "Authorization" in result["applicable_types"]

    def test_unknown_section(self, minimal_config):
        result = dc_regulatory_lookup("SOX", "99.0", config=minimal_config)
        assert "error" in result

    def test_framework_partial_match(self, minimal_config):
        result = dc_regulatory_lookup("OCC", "1.0", config=minimal_config)
        assert len(result["required_themes"]) > 0


# ── Hierarchy Search ──────────────────────────────────────────────────────────


class TestDcHierarchySearch:
    def test_known_section_no_keyword(self, minimal_config):
        result = dc_hierarchy_search("1.0", "", config=minimal_config)
        assert result["domain"] == "lending"
        assert "Loan Officer" in result["available_roles"]

    def test_keyword_filters_roles(self, minimal_config):
        result = dc_hierarchy_search("1.0", "Credit", config=minimal_config)
        assert "Credit Analyst" in result["available_roles"]

    def test_unknown_section(self, minimal_config):
        result = dc_hierarchy_search("99.0", "test", config=minimal_config)
        assert "error" in result

    def test_evidence_included(self, minimal_config):
        result = dc_hierarchy_search("1.0", "", config=minimal_config)
        assert "available_evidence" in result
        assert len(result["available_evidence"]) > 0


# ── Frequency Lookup ──────────────────────────────────────────────────────────


class TestDcFrequencyLookup:
    def test_monthly_trigger(self, minimal_config):
        result = dc_frequency_lookup("Reconciliation", "monthly review", config=minimal_config)
        assert result["derived_frequency"] == "Monthly"
        assert result["expected_frequency"] == "Monthly"

    def test_quarterly_trigger(self, minimal_config):
        result = dc_frequency_lookup("Authorization", "quarterly approval", config=minimal_config)
        assert result["derived_frequency"] == "Quarterly"
        assert result["expected_frequency"] == "Quarterly"

    def test_no_match_returns_other(self, minimal_config):
        result = dc_frequency_lookup("Authorization", "on demand", config=minimal_config)
        assert result["derived_frequency"] == "Other"

    def test_unknown_type_returns_other_expected(self, minimal_config):
        result = dc_frequency_lookup("Nonexistent", "daily check", config=minimal_config)
        assert result["derived_frequency"] == "Daily"
        assert result["expected_frequency"] == "Other"


# ── Memory Retrieval ──────────────────────────────────────────────────────────


class TestDcMemoryRetrieval:
    def test_no_memory_returns_error(self):
        result = dc_memory_retrieval("test query", memory=None)
        assert result["similar_controls"] == []
        assert "error" in result


# ── Tool Executor ─────────────────────────────────────────────────────────────


class TestBuildDomainToolExecutor:
    def test_dispatches_taxonomy_validator(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("taxonomy_validator", {"level_1": "Preventive", "level_2": "Authorization"})
        assert result["valid"] is True

    def test_dispatches_regulatory_lookup(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("regulatory_lookup", {"framework": "SOX", "section_id": "1.0"})
        assert result["domain"] == "lending"

    def test_dispatches_hierarchy_search(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("hierarchy_search", {"section_id": "1.0", "keyword": ""})
        assert "available_roles" in result

    def test_dispatches_frequency_lookup(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("frequency_lookup", {"control_type": "Reconciliation", "trigger": "monthly"})
        assert result["derived_frequency"] == "Monthly"

    def test_dispatches_memory_retrieval(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("memory_retrieval", {"query_text": "test"})
        assert "error" in result  # no memory configured

    def test_unknown_tool_returns_error(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        result = executor("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_tool_exception_returns_error(self, minimal_config):
        executor = build_domain_tool_executor(minimal_config)
        # Pass wrong args to trigger an exception
        result = executor("taxonomy_validator", {})
        assert "error" in result
