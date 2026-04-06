"""Tests for controlnexus.remediation (planner, paths) and new agents."""

from __future__ import annotations

from unittest.mock import AsyncMock

from controlnexus.agents import AGENT_REGISTRY, AgentContext, AdversarialReviewer, DifferentiationAgent
from controlnexus.remediation.planner import plan_assignments
from controlnexus.remediation.paths import (
    prepare_balance_path,
    prepare_evidence_fix,
    prepare_frequency_fix,
    prepare_regulatory_path,
    route_assignment,
)


# -- Planner Tests --------------------------------------------------------------


class TestPlanAssignments:
    def test_empty_report(self):
        assignments = plan_assignments({})
        assert assignments == []

    def test_regulatory_gaps_first(self):
        report = {
            "regulatory_gaps": [{"framework": "SOX", "required_theme": "SOX"}],
            "balance_gaps": [{"control_type": "Reconciliation", "direction": "under"}],
            "frequency_issues": [],
            "evidence_issues": [],
        }
        assignments = plan_assignments(report)
        assert len(assignments) == 2
        assert assignments[0]["gap_source"] == "regulatory"
        assert assignments[1]["gap_source"] == "balance"

    def test_all_gap_types(self):
        report = {
            "regulatory_gaps": [{"framework": "SOX"}],
            "balance_gaps": [{"control_type": "Auth", "direction": "under"}],
            "frequency_issues": [{"control_id": "C1"}],
            "evidence_issues": [{"control_id": "C2"}],
        }
        assignments = plan_assignments(report)
        sources = [a["gap_source"] for a in assignments]
        assert "regulatory" in sources
        assert "balance" in sources
        assert "frequency" in sources
        assert "evidence" in sources

    def test_over_represented_balance_skipped(self):
        report = {
            "balance_gaps": [{"control_type": "Auth", "direction": "over"}],
        }
        assignments = plan_assignments(report)
        assert len(assignments) == 0  # "over" is not remediated


# -- Paths Tests ---------------------------------------------------------------


class TestPaths:
    def test_regulatory_path(self):
        result = prepare_regulatory_path({"framework": "SOX"}, {})
        assert result["path"] == "regulatory"
        assert "SOX" in result["framework"]

    def test_balance_path(self):
        result = prepare_balance_path({"control_type": "Reconciliation"})
        assert result["path"] == "balance"
        assert result["control_type"] == "Reconciliation"

    def test_frequency_fix(self):
        result = prepare_frequency_fix(
            {
                "control_id": "C1",
                "expected_frequency": "Monthly",
            }
        )
        assert result["path"] == "frequency"
        assert result["fix"]["frequency"] == "Monthly"

    def test_evidence_fix(self):
        result = prepare_evidence_fix({"control_id": "C1", "issue": "missing artifact"})
        assert result["path"] == "evidence"

    def test_route_assignment(self):
        assert route_assignment({"gap_source": "regulatory"})["path"] == "regulatory"
        assert route_assignment({"gap_source": "balance"})["path"] == "balance"
        assert route_assignment({"gap_source": "frequency"})["path"] == "frequency"
        assert route_assignment({"gap_source": "evidence"})["path"] == "evidence"
        assert route_assignment({"gap_source": "unknown"})["path"] == "unknown"


# -- New Agent Tests ------------------------------------------------------------


class TestAgentRegistry:
    def test_adversarial_reviewer_registered(self):
        assert "AdversarialReviewer" in AGENT_REGISTRY

    def test_differentiation_agent_registered(self):
        assert "DifferentiationAgent" in AGENT_REGISTRY


class TestAdversarialReviewer:
    async def test_no_llm_fallback(self):
        ctx = AgentContext(client=None)
        agent = AdversarialReviewer(ctx)
        result = await agent.execute(
            control={"who": "Analyst", "full_description": "Test"},
            spec={},
        )
        assert result["overall_assessment"] == "Satisfactory"
        assert result["weaknesses"] == []

    async def test_with_mocked_llm(self):
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"weaknesses": [{"issue": "vague", "suggestion": "be specific"}], "overall_assessment": "Needs Improvement", "rewrite_guidance": "Improve specificity"}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
        ctx = AgentContext(client=mock_client)
        agent = AdversarialReviewer(ctx)
        result = await agent.execute(control={}, spec={})
        assert len(result["weaknesses"]) == 1


class TestDifferentiationAgent:
    async def test_no_llm_fallback(self):
        ctx = AgentContext(client=None)
        agent = DifferentiationAgent(ctx)
        result = await agent.execute(
            control={"full_description": "Original text", "who": "Analyst"},
            existing_control="Existing similar text",
            spec={},
        )
        assert "Additionally" in result["full_description"]

    async def test_with_mocked_llm(self):
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"who": "Analyst", "what": "new action", "when": "weekly", "where": "system", "why": "risk", "full_description": "A different control."}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
        ctx = AgentContext(client=mock_client)
        agent = DifferentiationAgent(ctx)
        result = await agent.execute(control={}, existing_control="", spec={})
        assert result["what"] == "new action"
