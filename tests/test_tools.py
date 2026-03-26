"""Tests for controlnexus.tools (schemas, implementations, nodes)."""

from __future__ import annotations

from controlnexus.core.models import (
    AffinityMatrix,
    DomainRegistry,
    RiskProfile,
    SectionProfile,
)
from controlnexus.tools.implementations import (
    configure_tools,
    frequency_lookup,
    hierarchy_search,
    memory_retrieval,
    regulatory_lookup,
    taxonomy_validator,
)
from controlnexus.tools.nodes import execute_tool_call, tool_node
from controlnexus.tools.schemas import TOOL_SCHEMAS


# -- Setup ---------------------------------------------------------------------


PLACEMENT_CONFIG = {
    "control_taxonomy": {
        "level_2_by_level_1": {
            "Preventive": ["Authorization", "Third Party Due Diligence", "Segregation of Duties"],
            "Detective": ["Reconciliation", "Exception Reporting", "Verification and Validation"],
            "Contingency Planning": ["Business Continuity Planning and Awareness"],
        }
    }
}

SECTION_PROFILES = {
    "4.0": SectionProfile(
        section_id="4.0",
        domain="sourcing_and_procurement",
        risk_profile=RiskProfile(
            inherent_risk=3, regulatory_intensity=4, control_density=3,
            multiplier=2.3, rationale="test",
        ),
        registry=DomainRegistry(
            roles=["Procurement Analyst", "Vendor Risk Analyst"],
            systems=["Vendor Management Platform"],
            regulatory_frameworks=["OCC Third Party Risk Management", "SOX Compliance"],
        ),
        affinity=AffinityMatrix(
            HIGH=["Third Party Due Diligence", "Authorization"],
            MEDIUM=["Risk Escalation Processes"],
            LOW=["Reconciliation"],
            NONE=[],
        ),
    ),
}


def setup_module():
    configure_tools(PLACEMENT_CONFIG, SECTION_PROFILES)


# -- Schema Tests ---------------------------------------------------------------


class TestSchemas:
    def test_five_schemas_defined(self):
        assert len(TOOL_SCHEMAS) == 5

    def test_all_have_function_name(self):
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
            assert "name" in schema["function"]
            assert "parameters" in schema["function"]

    def test_schema_names(self):
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert names == {
            "taxonomy_validator", "regulatory_lookup",
            "hierarchy_search", "frequency_lookup", "memory_retrieval",
        }


# -- Taxonomy Validator ---------------------------------------------------------


class TestTaxonomyValidator:
    def test_valid_pair(self):
        result = taxonomy_validator("Detective", "Reconciliation")
        assert result["valid"] is True
        assert result["suggestion"] is None

    def test_invalid_pair_with_suggestion(self):
        result = taxonomy_validator("Preventive", "Reconciliation")
        assert result["valid"] is False
        assert result["suggestion"]["correct_level_1"] == "Detective"

    def test_unknown_type(self):
        result = taxonomy_validator("Preventive", "Nonexistent Type")
        assert result["valid"] is False
        assert "Unknown" in result["suggestion"]["reason"]


# -- Regulatory Lookup ----------------------------------------------------------


class TestRegulatoryLookup:
    def test_known_framework(self):
        result = regulatory_lookup("SOX Compliance", "4.0")
        assert result["framework"] == "SOX Compliance"
        assert len(result["applicable_types"]) > 0
        assert "domain" in result

    def test_unknown_section(self):
        result = regulatory_lookup("SOX", "99.0")
        assert "error" in result

    def test_returns_affinity_types(self):
        result = regulatory_lookup("OCC", "4.0")
        assert "Third Party Due Diligence" in result["applicable_types"]


# -- Hierarchy Search -----------------------------------------------------------


class TestHierarchySearch:
    def test_known_section(self):
        result = hierarchy_search("4.0", "procurement")
        assert result["section_id"] == "4.0"
        assert result["domain"] == "sourcing_and_procurement"
        assert len(result["available_roles"]) > 0

    def test_unknown_section(self):
        result = hierarchy_search("99.0", "test")
        assert "error" in result


# -- Frequency Lookup -----------------------------------------------------------


class TestFrequencyLookup:
    def test_reconciliation_monthly(self):
        result = frequency_lookup("Reconciliation", "monthly by the 5th business day")
        assert result["derived_frequency"] == "Monthly"
        assert result["expected_frequency"] == "Monthly"

    def test_authorization_quarterly(self):
        result = frequency_lookup("Authorization", "quarterly review")
        assert result["derived_frequency"] == "Quarterly"
        assert result["expected_frequency"] == "Quarterly"

    def test_generic_type(self):
        result = frequency_lookup("Physical Safeguards", "on demand")
        assert result["expected_frequency"] == "Other"


# -- Memory Retrieval -----------------------------------------------------------


class TestMemoryRetrieval:
    def test_no_memory_configured(self):
        result = memory_retrieval("test query")
        assert result["similar_controls"] == []
        assert "error" in result


# -- Tool Node ------------------------------------------------------------------


class TestToolNode:
    def test_execute_tool_call_valid(self):
        result = execute_tool_call("taxonomy_validator", {"level_1": "Detective", "level_2": "Reconciliation"})
        assert result["valid"] is True

    def test_execute_tool_call_unknown(self):
        result = execute_tool_call("nonexistent_tool", {})
        assert "error" in result

    def test_tool_node_processes_messages(self):
        state = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "taxonomy_validator",
                                "arguments": '{"level_1": "Detective", "level_2": "Reconciliation"}',
                            },
                        }
                    ],
                }
            ]
        }
        result = tool_node(state)
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "tool"
        assert result["messages"][0]["tool_call_id"] == "call_1"

    def test_tool_node_no_tool_calls(self):
        state = {"messages": [{"role": "assistant", "content": "hello"}]}
        result = tool_node(state)
        assert result["messages"] == []

    def test_tool_node_empty_messages(self):
        result = tool_node({"messages": []})
        assert result["messages"] == []


# -- DomainConfig-aware tool tests (lookup tools for slim-prompt mode) ---------

from pathlib import Path

from controlnexus.core.domain_config import load_domain_config
from controlnexus.tools.domain_tools import (
    build_domain_tool_executor,
    dc_evidence_rules_lookup,
    dc_exemplar_lookup,
    dc_method_lookup,
    dc_placement_lookup,
)

_COMMUNITY_BANK = Path(__file__).resolve().parent.parent / "config" / "profiles" / "community_bank_demo.yaml"


class TestDomainLookupTools:
    """Tests for the 4 new lookup tools used in slim-prompt mode."""

    @classmethod
    def setup_class(cls):
        cls.config = load_domain_config(_COMMUNITY_BANK)

    def test_placement_lookup_returns_placements(self):
        result = dc_placement_lookup("Authorization", config=self.config)
        assert "placements" in result
        assert len(result["placements"]) > 0
        assert all("name" in p for p in result["placements"])
        assert all("description" in p for p in result["placements"])

    def test_placement_lookup_flags_allowed(self):
        result = dc_placement_lookup("Authorization", config=self.config)
        # At least one placement should be allowed for Authorization
        allowed = [p for p in result["placements"] if p.get("allowed_for_type")]
        assert len(allowed) >= 1

    def test_placement_lookup_unknown_type(self):
        result = dc_placement_lookup("NonexistentType", config=self.config)
        assert result["allowed_categories"] == []

    def test_method_lookup_returns_methods(self):
        result = dc_method_lookup(config=self.config)
        assert "methods" in result
        assert len(result["methods"]) > 0
        assert all("name" in m for m in result["methods"])

    def test_evidence_rules_lookup_known_type(self):
        result = dc_evidence_rules_lookup("Authorization", config=self.config)
        assert "evidence_criteria" in result
        assert len(result["evidence_criteria"]) > 0

    def test_evidence_rules_lookup_unknown_type(self):
        result = dc_evidence_rules_lookup("UnknownType", config=self.config)
        # Should return default criteria
        assert "evidence_criteria" in result
        assert len(result["evidence_criteria"]) >= 2

    def test_exemplar_lookup_known_section(self):
        # Get first available section from config
        if self.config.process_areas:
            section_id = self.config.process_areas[0].id
            result = dc_exemplar_lookup(section_id, config=self.config)
            assert "exemplars" in result
            assert "section_id" in result

    def test_exemplar_lookup_unknown_section(self):
        result = dc_exemplar_lookup("99.0", config=self.config)
        assert "error" in result
        assert result["exemplars"] == []

    def test_executor_dispatches_new_tools(self):
        executor = build_domain_tool_executor(self.config)
        result = executor("placement_lookup", {"control_type": "Authorization"})
        assert "placements" in result

        result = executor("method_lookup", {})
        assert "methods" in result

        result = executor("evidence_rules_lookup", {"control_type": "Authorization"})
        assert "evidence_criteria" in result
