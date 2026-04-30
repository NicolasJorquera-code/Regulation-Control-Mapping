"""Tests for controlnexus.agents.config_proposer (deterministic fallback paths)."""

from __future__ import annotations

import pytest

from controlnexus.agents import AGENT_REGISTRY, AgentContext, ConfigProposerAgent
from controlnexus.analysis.register_analyzer import RegisterSummary
from controlnexus.exceptions import AgentExecutionException


# ── Registry ──────────────────────────────────────────────────────────────────


class TestConfigProposerRegistry:
    def test_registered(self):
        assert "ConfigProposerAgent" in AGENT_REGISTRY
        assert AGENT_REGISTRY["ConfigProposerAgent"] is ConfigProposerAgent


# ── Deterministic fallback (no LLM client) ────────────────────────────────────


class TestDeterministicFallback:
    """All tests run with client=None so the agent takes deterministic paths."""

    @pytest.fixture
    def agent(self) -> ConfigProposerAgent:
        ctx = AgentContext(client=None)
        return ConfigProposerAgent(ctx, name="test-proposer")

    @pytest.fixture
    def sample_summary(self) -> RegisterSummary:
        return RegisterSummary(
            row_count=10,
            unique_control_types=["Access Review", "Reconciliation", "Change Management"],
            unique_business_units=[
                {"id": "BU-001", "name": "Retail Banking"},
                {"id": "BU-002", "name": "Risk Management"},
            ],
            unique_sections=[
                {"id": "1.0", "name": "Lending"},
                {"id": "2.0", "name": "Treasury"},
            ],
            unique_placements=["Preventive", "Detective"],
            unique_methods=["Automated", "Manual"],
            frequency_values=["Daily", "Monthly"],
            role_mentions=["Analyst", "Manager"],
            system_mentions=["LOS", "Bloomberg"],
            regulatory_mentions=["SOX", "Basel III"],
            sample_descriptions=["Daily access review", "Monthly reconciliation"],
        )

    @pytest.mark.asyncio
    async def test_full_mode_returns_valid_dict(self, agent: ConfigProposerAgent, sample_summary: RegisterSummary):
        result = await agent.execute(mode="full", register_summary=sample_summary)
        assert "name" in result
        assert "control_types" in result
        assert "business_units" in result
        assert "process_areas" in result
        assert len(result["control_types"]) == 3
        assert len(result["business_units"]) == 2

    @pytest.mark.asyncio
    async def test_full_mode_types_match_input(self, agent: ConfigProposerAgent, sample_summary: RegisterSummary):
        result = await agent.execute(mode="full", register_summary=sample_summary)
        type_names = [ct["name"] for ct in result["control_types"]]
        assert "Access Review" in type_names
        assert "Reconciliation" in type_names

    @pytest.mark.asyncio
    async def test_full_mode_sections_match_input(self, agent: ConfigProposerAgent, sample_summary: RegisterSummary):
        result = await agent.execute(mode="full", register_summary=sample_summary)
        pa_names = [pa["name"] for pa in result["process_areas"]]
        assert any("Lending" in n for n in pa_names)

    @pytest.mark.asyncio
    async def test_section_autofill_mode(self, agent: ConfigProposerAgent):
        result = await agent.execute(
            mode="section_autofill",
            section_name="Lending",
            control_type_names=["Access Review", "Reconciliation"],
            config_context={"name": "test", "description": "Test org"},
        )
        assert "risk_profile" in result
        assert "affinity" in result
        assert "registry" in result
        rp = result["risk_profile"]
        assert 1 <= rp.get("inherent_risk", 0) <= 5

    @pytest.mark.asyncio
    async def test_enrich_mode(self, agent: ConfigProposerAgent):
        result = await agent.execute(mode="enrich", type_names=["Access Review", "Change Management"])
        assert "control_types" in result
        enriched = result["control_types"]
        assert len(enriched) == 2
        for ct in enriched:
            assert "name" in ct
            assert "definition" in ct
            assert "code" in ct

    @pytest.mark.asyncio
    async def test_unknown_mode_raises(self, agent: ConfigProposerAgent):
        with pytest.raises(AgentExecutionException, match="Unknown mode"):
            await agent.execute(mode="invalid_mode")


# ── Full-mode output can create DomainConfig ──────────────────────────────────


class TestFullModeValidation:
    """Verify deterministic output can be loaded by DomainConfig."""

    @pytest.mark.asyncio
    async def test_domain_config_roundtrip(self):
        from controlnexus.core.domain_config import DomainConfig

        ctx = AgentContext(client=None)
        agent = ConfigProposerAgent(ctx)
        summary = RegisterSummary(
            row_count=5,
            unique_control_types=["Policy Review"],
            unique_business_units=[{"id": "BU-001", "name": "Compliance"}],
            unique_sections=[{"id": "1.0", "name": "Governance"}],
            unique_placements=["Preventive"],
            unique_methods=["Manual"],
            frequency_values=["Annual"],
        )
        result = await agent.execute(mode="full", register_summary=summary)
        # Should be loadable by DomainConfig
        config = DomainConfig(**result)
        assert config.name
        assert len(config.control_types) >= 1
