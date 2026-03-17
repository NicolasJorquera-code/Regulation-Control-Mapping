"""Tests for controlnexus.agents (base, registry, and concrete agents)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from typing import Any

import pytest

from controlnexus.agents import (
    AGENT_REGISTRY,
    AgentContext,
    BaseAgent,
    EnricherAgent,
    NarrativeAgent,
    SpecAgent,
)
from controlnexus.exceptions import ExternalServiceException, ValidationException


# -- Registry -------------------------------------------------------------------


class TestAgentRegistry:
    def test_all_agents_registered(self):
        assert "SpecAgent" in AGENT_REGISTRY
        assert "NarrativeAgent" in AGENT_REGISTRY
        assert "EnricherAgent" in AGENT_REGISTRY

    def test_registry_maps_to_classes(self):
        assert AGENT_REGISTRY["SpecAgent"] is SpecAgent
        assert AGENT_REGISTRY["NarrativeAgent"] is NarrativeAgent
        assert AGENT_REGISTRY["EnricherAgent"] is EnricherAgent


# -- AgentContext ---------------------------------------------------------------


class TestAgentContext:
    def test_defaults(self):
        ctx = AgentContext()
        assert ctx.client is None
        assert ctx.temperature == 0.2
        assert ctx.max_tokens == 1400


# -- BaseAgent ------------------------------------------------------------------


class _DummyAgent(BaseAgent):
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {"dummy": True}


class TestBaseAgent:
    def test_name_defaults_to_class(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        assert agent.name == "_DummyAgent"

    def test_custom_name(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx, name="Custom")
        assert agent.name == "Custom"

    async def test_call_llm_no_client_raises(self):
        ctx = AgentContext(client=None)
        agent = _DummyAgent(ctx)
        with pytest.raises(ExternalServiceException, match="No LLM client"):
            await agent.call_llm("sys", "user")

    async def test_call_llm_tracks_tokens(self):
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": '{"result": true}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        })
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        result = await agent.call_llm("system", "user")
        assert agent.call_count == 1
        assert agent.total_input_tokens == 100
        assert agent.total_output_tokens == 50
        assert '{"result": true}' in result


class TestParseJson:
    def test_plain_json(self):
        result = BaseAgent.parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced_json(self):
        result = BaseAgent.parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(ValidationException, match="Failed to parse"):
            BaseAgent.parse_json("not json at all")


class TestExtractText:
    def test_standard_response(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        payload = {"choices": [{"message": {"content": "hello"}}]}
        assert agent._extract_text_from_openai_style(payload) == "hello"

    def test_list_content_blocks(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        payload = {"choices": [{"message": {"content": [
            {"text": "part1"},
            {"type": "output_text", "text": "part2"},
        ]}}]}
        assert "part1" in agent._extract_text_from_openai_style(payload)
        assert "part2" in agent._extract_text_from_openai_style(payload)

    def test_empty_choices_returns_str(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        payload = {"choices": []}
        result = agent._extract_text_from_openai_style(payload)
        assert isinstance(result, str)


# -- Concrete Agents (smoke tests with mocked LLM) -----------------------------


@pytest.fixture
def mock_context():
    mock_client = AsyncMock()
    mock_client.chat_completion = AsyncMock(return_value={
        "choices": [{"message": {"content": '{"placeholder": true}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })
    return AgentContext(client=mock_client, model="test-model")


class TestSpecAgent:
    async def test_execute_returns_parsed_json(self, mock_context):
        agent = SpecAgent(mock_context)
        result = await agent.execute(
            leaf={"hierarchy_id": "4.1.1"},
            control_type="Preventive",
            type_definition="...",
            registry={},
            placement_defs={},
            method_defs={},
            taxonomy_constraints={},
            diversity_context={},
        )
        assert result == {"placeholder": True}


class TestNarrativeAgent:
    async def test_execute_returns_parsed_json(self, mock_context):
        agent = NarrativeAgent(mock_context)
        result = await agent.execute(
            locked_spec={"hierarchy_id": "4.1.1"},
            standards={},
            phrase_bank_cfg={},
            exemplars=[],
            regulatory_context=[],
        )
        assert result == {"placeholder": True}

    async def test_retry_appendix_appended(self, mock_context):
        agent = NarrativeAgent(mock_context)
        await agent.execute(
            locked_spec={"hierarchy_id": "4.1.1"},
            standards={},
            phrase_bank_cfg={},
            exemplars=[],
            regulatory_context=[],
            retry_appendix="ATTEMPT 2/3. Previous failures:\n- VAGUE_WHEN",
        )
        call_args = mock_context.client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_msg = messages[-1]["content"]
        assert "ATTEMPT 2/3" in user_msg


class TestEnricherAgent:
    async def test_execute_returns_parsed_json(self, mock_context):
        agent = EnricherAgent(mock_context)
        result = await agent.execute(
            validated_control={"hierarchy_id": "4.1.1"},
            rating_criteria_cfg={},
            nearest_neighbors=[],
        )
        assert result == {"placeholder": True}
