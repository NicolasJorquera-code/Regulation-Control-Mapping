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
        mock_client.chat_completion = AsyncMock(
            return_value={
                "choices": [{"message": {"content": '{"result": true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        )
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

    def test_prose_wrapped_code_fence(self):
        """Granite-style: prose text followed by ```json ... ```."""
        text = (
            'Based on the tool results, here is the JSON:\n\n'
            '```json\n'
            '{"hierarchy_id": "11.0.1.1", "control_type": "Reconciliation"}\n'
            '```'
        )
        result = BaseAgent.parse_json(text)
        assert result["hierarchy_id"] == "11.0.1.1"
        assert result["control_type"] == "Reconciliation"

    def test_prose_wrapped_code_fence_with_trailing_text(self):
        text = (
            'Here is the narrative:\n\n'
            '```json\n'
            '{"who": "Manager", "what": "reviews"}\n'
            '```\n\n'
            'I hope this meets your requirements.'
        )
        result = BaseAgent.parse_json(text)
        assert result["who"] == "Manager"

    def test_bare_json_in_prose(self):
        """JSON embedded in prose without code fences."""
        text = 'Here is the result: {"key": "value"} end.'
        result = BaseAgent.parse_json(text)
        assert result == {"key": "value"}

class TestExtractText:
    def test_standard_response(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        payload = {"choices": [{"message": {"content": "hello"}}]}
        assert agent._extract_text_from_openai_style(payload) == "hello"

    def test_list_content_blocks(self):
        ctx = AgentContext()
        agent = _DummyAgent(ctx)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "part1"},
                            {"type": "output_text", "text": "part2"},
                        ]
                    }
                }
            ]
        }
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
    mock_client.chat_completion = AsyncMock(
        return_value={
            "choices": [{"message": {"content": '{"placeholder": true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )
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


# -- XML tool-call simulation loop ---------------------------------------------


class TestCallLlmWithXmlTools:
    """Tests for BaseAgent.call_llm_with_xml_tools()."""

    async def test_no_tool_calls_returns_immediately(self):
        """If the LLM returns no <tool_call> blocks, return the text as-is."""
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            return_value={
                "choices": [{"message": {"content": '{"control_type": "Reconciliation"}'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            }
        )
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        result = await agent.call_llm_with_xml_tools(
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            tool_executor=lambda name, args: {"error": "should not be called"},
        )

        assert result["_tool_calls_count"] == 0
        assert '{"control_type": "Reconciliation"}' in result["content"]

    async def test_single_tool_call_round(self):
        """LLM emits a tool call on round 1, then a final JSON on round 2."""
        round1_text = (
            "Let me look up placements.\n"
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Reconciliation"}</arguments>\n'
            "</tool_call>"
        )
        round2_text = '{"control_type": "Reconciliation", "placement": "Detective"}'

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            side_effect=[
                {
                    "choices": [{"message": {"content": round1_text}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 30},
                },
                {
                    "choices": [{"message": {"content": round2_text}}],
                    "usage": {"prompt_tokens": 80, "completion_tokens": 25},
                },
            ]
        )
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        executed_tools: list[dict] = []

        def tool_executor(name: str, args: dict) -> dict:
            executed_tools.append({"name": name, "args": args})
            return {"placements": ["Detective"]}

        result = await agent.call_llm_with_xml_tools(
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            tool_executor=tool_executor,
        )

        assert result["_tool_calls_count"] == 1
        assert len(executed_tools) == 1
        assert executed_tools[0]["name"] == "placement_lookup"
        assert "Detective" in result["content"]

    async def test_multiple_tool_calls_in_one_round(self):
        """LLM emits two tool calls in a single response."""
        round1_text = (
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Auth"}</arguments>\n'
            "</tool_call>\n"
            "<tool_call>\n"
            "<name>method_lookup</name>\n"
            "<arguments>{}</arguments>\n"
            "</tool_call>"
        )
        round2_text = '{"placement": "Preventive", "method": "Manual"}'

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            side_effect=[
                {
                    "choices": [{"message": {"content": round1_text}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 30},
                },
                {
                    "choices": [{"message": {"content": round2_text}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 25},
                },
            ]
        )
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        executed_tools: list[str] = []

        def tool_executor(name: str, args: dict) -> dict:
            executed_tools.append(name)
            return {"result": "ok"}

        result = await agent.call_llm_with_xml_tools(
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            tool_executor=tool_executor,
        )

        assert result["_tool_calls_count"] == 2
        assert "placement_lookup" in executed_tools
        assert "method_lookup" in executed_tools

    async def test_max_tool_rounds_respected(self):
        """If the LLM keeps emitting tool calls, we stop after max_tool_rounds."""
        tool_call_text = (
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Rec"}</arguments>\n'
            "</tool_call>"
        )
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            return_value={
                "choices": [{"message": {"content": tool_call_text}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            }
        )
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        result = await agent.call_llm_with_xml_tools(
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            tool_executor=lambda name, args: {"result": "ok"},
            max_tool_rounds=2,
        )

        assert result["_tool_calls_count"] == 2
        assert mock_client.chat_completion.call_count == 2

    async def test_no_client_raises(self):
        """call_llm_with_xml_tools raises when no client is configured."""
        ctx = AgentContext(client=None)
        agent = _DummyAgent(ctx)
        with pytest.raises(ExternalServiceException, match="No LLM client"):
            await agent.call_llm_with_xml_tools(
                messages=[],
                tool_executor=lambda name, args: {},
            )

    async def test_token_accounting(self):
        """Token usage is accumulated across rounds."""
        round1_text = (
            "<tool_call>\n<name>a</name>\n<arguments>{}</arguments>\n</tool_call>"
        )
        round2_text = '{"done": true}'

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            side_effect=[
                {
                    "choices": [{"message": {"content": round1_text}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                },
                {
                    "choices": [{"message": {"content": round2_text}}],
                    "usage": {"prompt_tokens": 200, "completion_tokens": 30},
                },
            ]
        )
        ctx = AgentContext(client=mock_client)
        agent = _DummyAgent(ctx)

        await agent.call_llm_with_xml_tools(
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            tool_executor=lambda name, args: {},
        )

        assert agent.total_input_tokens == 300
        assert agent.total_output_tokens == 80


# -- PolicyIngestionAgent -------------------------------------------------------


class TestPolicyIngestionAgent:
    """Tests for the PolicyIngestionAgent stub."""

    async def test_registered(self):
        assert "PolicyIngestionAgent" in AGENT_REGISTRY

    async def test_no_policy_text_returns_empty(self):
        from controlnexus.agents.policy_ingestion import PolicyIngestionAgent

        ctx = AgentContext()
        agent = PolicyIngestionAgent(ctx)
        result = await agent.execute()
        assert result["processes"] == []
        assert result["risks"] == []
        assert result["risk_instances"] == []
        assert result["provenance"] == ""

    async def test_with_policy_text_no_llm(self):
        from controlnexus.agents.policy_ingestion import PolicyIngestionAgent

        ctx = AgentContext()
        agent = PolicyIngestionAgent(ctx)
        result = await agent.execute(policy_text="Some policy document text.")
        assert result["processes"] == []
        assert "stub" in result["provenance"]

    async def test_with_policy_text_and_llm_stub(self, mock_context):
        from controlnexus.agents.policy_ingestion import PolicyIngestionAgent

        agent = PolicyIngestionAgent(mock_context)
        result = await agent.execute(policy_text="Some policy.", llm_enabled=True)
        assert result["processes"] == []
        assert "stub" in result["provenance"]
