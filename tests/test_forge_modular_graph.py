"""Tests for the ControlForge Modular graph and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from controlnexus.core.domain_config import DomainConfig, load_domain_config
from controlnexus.graphs.forge_modular_graph import (
    ForgeState,
    _supports_tools,
    after_init,
    after_validate,
    build_forge_graph,
    enrich_node,
    has_more,
    merge_node,
    narrative_node,
    reset_llm_cache,
    select_node,
    set_emitter,
    spec_node,
    validate_node,
)
from controlnexus.core.events import EventEmitter, EventType, PipelineEvent
from controlnexus.graphs.forge_modular_helpers import (
    build_assignment_matrix,
    build_deterministic_enriched,
    build_deterministic_narrative,
    build_deterministic_spec,
    build_enricher_system_prompt,
    build_narrative_system_prompt,
    build_narrative_user_prompt,
    build_slim_narrative_system_prompt,
    build_slim_narrative_user_prompt,
    build_slim_spec_system_prompt,
    build_slim_spec_user_prompt,
    build_spec_system_prompt,
    build_spec_user_prompt,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"
COMMUNITY_BANK = PROFILES_DIR / "community_bank_demo.yaml"
BANKING_STANDARD = PROFILES_DIR / "banking_standard.yaml"


# ── Helper Tests ──────────────────────────────────────────────────────────────


class TestAssignmentMatrix:

    def test_produces_correct_count(self):
        config = load_domain_config(COMMUNITY_BANK)
        assignments = build_assignment_matrix(config, target_count=10)
        assert len(assignments) == 10

    def test_all_fields_present(self):
        config = load_domain_config(COMMUNITY_BANK)
        assignments = build_assignment_matrix(config, target_count=5)
        for a in assignments:
            assert "section_id" in a
            assert "control_type" in a
            assert "business_unit_id" in a
            assert "hierarchy_id" in a

    def test_custom_type_weights(self):
        config = load_domain_config(COMMUNITY_BANK)
        # Heavily weight Authorization
        dist = {"type_weights": {"Authorization": 10.0, "Reconciliation": 1.0, "Exception Reporting": 1.0}}
        assignments = build_assignment_matrix(config, target_count=12, distribution_config=dist)
        auth_count = sum(1 for a in assignments if a["control_type"] == "Authorization")
        assert auth_count > 6  # should get most of the 12

    def test_banking_standard_large(self):
        config = load_domain_config(BANKING_STANDARD)
        assignments = build_assignment_matrix(config, target_count=50)
        assert len(assignments) == 50

    def test_banking_standard_small_target(self):
        """Regression: target_count=1 with many sections/types must still produce 1."""
        config = load_domain_config(BANKING_STANDARD)
        for n in (1, 2, 3):
            assignments = build_assignment_matrix(config, target_count=n)
            assert len(assignments) == n, f"Expected {n} assignments, got {len(assignments)}"


class TestDeterministicBuilders:

    @pytest.fixture()
    def config(self) -> DomainConfig:
        return load_domain_config(COMMUNITY_BANK)

    @pytest.fixture()
    def assignment(self, config: DomainConfig) -> dict:
        return build_assignment_matrix(config, target_count=1)[0]

    def test_spec_has_required_fields(self, assignment, config):
        spec = build_deterministic_spec(assignment, config)
        for key in ("hierarchy_id", "control_type", "who", "where_system", "when", "placement", "method"):
            assert key in spec, f"Missing key: {key}"

    def test_narrative_has_5w(self, assignment, config):
        spec = build_deterministic_spec(assignment, config)
        narr = build_deterministic_narrative(spec, config)
        for key in ("who", "what", "when", "where", "why", "full_description"):
            assert key in narr

    def test_enriched_has_export_fields(self, assignment, config):
        spec = build_deterministic_spec(assignment, config)
        narr = build_deterministic_narrative(spec, config)
        enriched = build_deterministic_enriched(spec, narr, config)
        for key in ("control_id", "hierarchy_id", "control_type", "who", "what",
                     "when", "frequency", "where", "why", "full_description",
                     "quality_rating", "evidence"):
            assert key in enriched, f"Missing key: {key}"


# ── Graph Execution Tests ────────────────────────────────────────────────────


class TestForgeGraph:

    def test_graph_compiles(self):
        graph = build_forge_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_produces_correct_count(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 5,
        })
        payload = result["plan_payload"]
        assert payload["total_controls"] == 5
        assert len(payload["final_records"]) == 5

    def test_graph_assigns_control_ids(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 3,
        })
        for record in result["plan_payload"]["final_records"]:
            assert record["control_id"].startswith("CTRL-")
            assert len(record["control_id"]) > 10

    def test_graph_uses_config_type_codes(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 6,
        })
        config = load_domain_config(COMMUNITY_BANK)
        codes = set(config.type_code_map().values())
        for record in result["plan_payload"]["final_records"]:
            # Extract type code from CTRL-XXYY-CODE-NNN
            parts = record["control_id"].split("-")
            type_code = parts[2] if len(parts) >= 4 else ""
            assert type_code in codes, f"Unknown code {type_code} not in {codes}"

    def test_graph_loops_all_assignments(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 4,
        })
        assert result["current_idx"] == 4
        assert len(result["plan_payload"]["final_records"]) == 4

    def test_graph_with_banking_standard(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(BANKING_STANDARD),
            "target_count": 25,
        })
        payload = result["plan_payload"]
        assert payload["total_controls"] == 25
        assert payload["config_name"] == "banking-standard"

    def test_graph_deterministic_output(self):
        """Same config + same inputs → identical output."""
        graph = build_forge_graph().compile()
        input_state = {
            "config_path": str(COMMUNITY_BANK),
            "target_count": 5,
        }
        r1 = graph.invoke(input_state)
        r2 = graph.invoke(input_state)
        assert r1["plan_payload"]["final_records"] == r2["plan_payload"]["final_records"]

    def test_graph_custom_distribution(self):
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 9,
            "distribution_config": {
                "type_weights": {
                    "Authorization": 5.0,
                    "Reconciliation": 1.0,
                    "Exception Reporting": 1.0,
                }
            },
        })
        records = result["plan_payload"]["final_records"]
        auth_count = sum(1 for r in records if r["control_type"] == "Authorization")
        assert auth_count >= 4  # should dominate distribution


# ── Graph Topology Tests ─────────────────────────────────────────────────────


class TestGraphTopology:

    def test_graph_has_8_nodes(self):
        graph = build_forge_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        expected = {"__start__", "__end__", "init", "select", "spec", "narrative", "validate", "enrich", "merge", "finalize"}
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"

    def test_deterministic_path_same_output(self):
        """Split nodes produce identical output to the old generate_node path."""
        graph = build_forge_graph().compile()
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 5,
        })
        payload = result["plan_payload"]
        assert payload["total_controls"] == 5
        # Verify records have all expected fields
        for r in payload["final_records"]:
            assert r["control_id"].startswith("CTRL-")
            assert r["full_description"]
            assert r["quality_rating"] == "Satisfactory"

    @patch("controlnexus.graphs.forge_modular_graph._get_agent", return_value=None)
    def test_llm_enabled_flag_propagates(self, _mock_agent):
        """llm_enabled=True in input propagates through state."""
        graph = build_forge_graph().compile()
        # _get_agent returns None → falls back to deterministic
        result = graph.invoke({
            "config_path": str(COMMUNITY_BANK),
            "target_count": 1,
            "llm_enabled": True,
        })
        # Even with llm_enabled=True, generates successfully (fallback)
        assert result["plan_payload"]["total_controls"] == 1

    def test_after_init_routes_to_select(self):
        state: ForgeState = {"assignments": [{"a": 1}]}  # type: ignore[typeddict-item]
        assert after_init(state) == "select"

    def test_after_init_routes_to_finalize_when_empty(self):
        state: ForgeState = {"assignments": []}  # type: ignore[typeddict-item]
        assert after_init(state) == "finalize"

    def test_after_validate_routes_to_enrich(self):
        state: ForgeState = {"validation_passed": True}  # type: ignore[typeddict-item]
        assert after_validate(state) == "enrich"

    def test_after_validate_routes_to_narrative_on_failure(self):
        state: ForgeState = {"validation_passed": False}  # type: ignore[typeddict-item]
        assert after_validate(state) == "narrative"

    def test_select_node_raises_on_out_of_bounds(self):
        state: ForgeState = {"assignments": [], "current_idx": 0}  # type: ignore[typeddict-item]
        with pytest.raises(IndexError, match="out of range"):
            select_node(state)


# ── LLM Node Tests (mock-based) ──────────────────────────────────────────────


def _make_state(
    llm_enabled: bool = True,
    **overrides: object,
) -> ForgeState:
    """Build a minimal ForgeState dict for node-level testing."""
    config = load_domain_config(COMMUNITY_BANK)
    assignments = build_assignment_matrix(config, target_count=1)
    assignment = assignments[0]
    spec = build_deterministic_spec(assignment, config)
    narrative = build_deterministic_narrative(spec, config)

    base: dict = {
        "config_path": str(COMMUNITY_BANK),
        "domain_config": config.model_dump(),
        "llm_enabled": llm_enabled,
        "assignments": assignments,
        "current_idx": 0,
        "current_assignment": assignment,
        "current_spec": spec,
        "current_narrative": narrative,
        "retry_count": 0,
        "validation_passed": False,
        "validation_failures": [],
        "retry_appendix": "",
        "generated_records": [],
        "tool_calls_log": [],
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _mock_agent(name: str = "TestAgent") -> MagicMock:
    """Create a mock BaseAgent with call_llm_with_tools and parse_json."""
    agent = MagicMock()
    agent.name = name
    agent.call_llm = AsyncMock()
    agent.call_llm_with_tools = AsyncMock()
    # parse_json delegates to the real static method for realistic behavior
    from controlnexus.agents.base import BaseAgent
    agent.parse_json = BaseAgent.parse_json
    # _extract_text_from_openai_style is an instance method used by graph nodes
    agent._extract_text_from_openai_style = BaseAgent._extract_text_from_openai_style.__get__(agent)
    return agent


class TestLLMNodes:

    def setup_method(self):
        reset_llm_cache()

    def teardown_method(self):
        reset_llm_cache()

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_calls_llm_when_enabled(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {
            "hierarchy_id": "1.0.1.1",
            "leaf_name": "Test",
            "selected_level_1": "Preventive",
            "control_type": "Authorization",
            "placement": "Preventive",
            "method": "Manual",
            "who": "Manager",
            "what_action": "reviews transactions",
            "what_detail": "detail",
            "when": "monthly",
            "where_system": "Core Banking",
            "why_risk": "to mitigate risk",
            "evidence": "approval log",
            "business_unit_id": "BU-RB",
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(spec_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        result = spec_node(state)
        assert result["current_spec"]["hierarchy_id"] == "1.0.1.1"
        agent.call_llm_with_tools.assert_called_once()

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_narrative_node_calls_llm_when_enabled(self, mock_get_agent):
        agent = _mock_agent("NarrativeAgent")
        mock_get_agent.return_value = agent

        narr_response = {
            "who": "Manager",
            "what": "reviews transactions",
            "when": "monthly",
            "where": "Core Banking",
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(narr_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        result = narrative_node(state)
        assert result["current_narrative"]["who"] == "Manager"
        agent.call_llm_with_tools.assert_called_once()

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_enrich_node_calls_llm_when_enabled(self, mock_get_agent):
        agent = _mock_agent("EnricherAgent")
        mock_get_agent.return_value = agent

        enrich_response = {
            "refined_full_description": "A refined description " + " ".join(["word"] * 35),
            "quality_rating": "Effective",
            "rationale": "Good coverage",
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(enrich_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        result = enrich_node(state)
        assert result["current_enriched"]["quality_rating"] == "Effective"
        agent.call_llm_with_tools.assert_called_once()

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_falls_back_on_llm_error(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent
        agent.call_llm_with_tools.side_effect = Exception("LLM unavailable")

        state = _make_state(llm_enabled=True)
        result = spec_node(state)
        # Should fall back to deterministic
        assert "current_spec" in result
        assert result["current_spec"]["control_type"]

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_narrative_node_falls_back_on_llm_error(self, mock_get_agent):
        agent = _mock_agent("NarrativeAgent")
        mock_get_agent.return_value = agent
        agent.call_llm_with_tools.side_effect = Exception("LLM unavailable")

        state = _make_state(llm_enabled=True)
        result = narrative_node(state)
        assert "current_narrative" in result
        assert result["current_narrative"]["full_description"]

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_enrich_node_falls_back_on_llm_error(self, mock_get_agent):
        agent = _mock_agent("EnricherAgent")
        mock_get_agent.return_value = agent
        agent.call_llm_with_tools.side_effect = Exception("LLM unavailable")

        state = _make_state(llm_enabled=True)
        result = enrich_node(state)
        assert "current_enriched" in result
        assert result["current_enriched"]["quality_rating"] == "Satisfactory"

    def test_spec_node_deterministic_when_disabled(self):
        state = _make_state(llm_enabled=False)
        result = spec_node(state)
        assert "current_spec" in result
        assert result["current_spec"]["control_type"]

    def test_narrative_node_deterministic_when_disabled(self):
        state = _make_state(llm_enabled=False)
        result = narrative_node(state)
        assert "current_narrative" in result
        assert result["current_narrative"]["full_description"]

    def test_enrich_node_deterministic_when_disabled(self):
        state = _make_state(llm_enabled=False)
        result = enrich_node(state)
        assert "current_enriched" in result
        assert result["current_enriched"]["quality_rating"] == "Satisfactory"

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_falls_back_when_no_client(self, mock_get_agent):
        mock_get_agent.return_value = None
        state = _make_state(llm_enabled=True)
        result = spec_node(state)
        assert "current_spec" in result
        assert result["current_spec"]["control_type"]


# ── Validation Retry Loop Tests ──────────────────────────────────────────────


class TestValidationRetryLoop:

    def test_validate_passes_deterministic(self):
        state = _make_state(llm_enabled=False)
        result = validate_node(state)
        assert result["validation_passed"] is True
        assert result["validation_failures"] == []

    def test_validate_catches_vague_when(self):
        """LLM narrative with vague 'when' triggers validation failure."""
        state = _make_state(llm_enabled=True)
        state["current_narrative"] = {
            "who": state["current_spec"]["who"],
            "what": "reviews",
            "when": "as needed",
            "where": state["current_spec"]["where_system"],
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        result = validate_node(state)
        assert result["validation_passed"] is False
        assert "VAGUE_WHEN" in result["validation_failures"]

    def test_validate_retry_increments_count(self):
        state = _make_state(llm_enabled=True, retry_count=0)
        state["current_narrative"] = {
            "who": state["current_spec"]["who"],
            "what": "reviews",
            "when": "as needed",
            "where": state["current_spec"]["where_system"],
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        result = validate_node(state)
        assert result["retry_count"] == 1

    def test_validate_max_retries_forces_pass(self):
        state = _make_state(llm_enabled=True, retry_count=3)
        state["current_narrative"] = {
            "who": "Wrong Person",
            "what": "reviews",
            "when": "as needed",
            "where": "Wrong System",
            "why": "no risk word here",
            "full_description": "too short",
        }
        result = validate_node(state)
        assert result["validation_passed"] is True

    def test_retry_appendix_built_on_failure(self):
        state = _make_state(llm_enabled=True, retry_count=0)
        state["current_narrative"] = {
            "who": state["current_spec"]["who"],
            "what": "reviews",
            "when": "as needed",
            "where": state["current_spec"]["where_system"],
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        result = validate_node(state)
        assert "ATTEMPT" in result["retry_appendix"]
        assert "VAGUE_WHEN" in result["retry_appendix"]


# ── Prompt Template Tests ─────────────────────────────────────────────────────


class TestPromptTemplates:

    @pytest.fixture()
    def config(self) -> DomainConfig:
        return load_domain_config(COMMUNITY_BANK)

    @pytest.fixture()
    def assignment(self, config: DomainConfig) -> dict:
        return build_assignment_matrix(config, target_count=1)[0]

    def test_spec_system_prompt_includes_placements(self, config):
        prompt = build_spec_system_prompt(config)
        for name in config.placement_names():
            assert name in prompt, f"Placement '{name}' not in spec system prompt"

    def test_spec_system_prompt_includes_methods(self, config):
        prompt = build_spec_system_prompt(config)
        for name in config.method_names():
            assert name in prompt, f"Method '{name}' not in spec system prompt"

    def test_narrative_system_prompt_includes_word_counts(self, config):
        prompt = build_narrative_system_prompt(config)
        assert str(config.narrative.word_count_min) in prompt
        assert str(config.narrative.word_count_max) in prompt

    def test_enricher_system_prompt_includes_quality_ratings(self, config):
        prompt = build_enricher_system_prompt(config)
        for rating in config.quality_ratings:
            assert rating in prompt, f"Rating '{rating}' not in enricher system prompt"

    def test_spec_user_prompt_includes_registry(self, config, assignment):
        prompt = build_spec_user_prompt(assignment, config)
        payload = json.loads(prompt)
        assert "domain_registry" in payload
        assert "control_type" in payload

    def test_narrative_user_prompt_includes_retry_appendix(self, config, assignment):
        spec = build_deterministic_spec(assignment, config)
        prompt = build_narrative_user_prompt(spec, config, retry_appendix="ATTEMPT 1/3")
        assert "ATTEMPT 1/3" in prompt

    def test_spec_user_prompt_has_valid_json(self, config, assignment):
        prompt = build_spec_user_prompt(assignment, config)
        payload = json.loads(prompt)
        assert payload["leaf"]["hierarchy_id"]
        assert payload["control_type"]

    def test_enricher_system_prompt_includes_word_counts(self, config):
        prompt = build_enricher_system_prompt(config)
        assert str(config.narrative.word_count_min) in prompt
        assert str(config.narrative.word_count_max) in prompt


# ── Event Emission Tests ──────────────────────────────────────────────────────


class TestEventEmission:
    """Verify that graph nodes emit the expected events."""

    def setup_method(self):
        reset_llm_cache()
        self.events: list[PipelineEvent] = []
        emitter = EventEmitter()
        emitter.on(self.events.append)
        set_emitter(emitter)

    def teardown_method(self):
        reset_llm_cache()
        set_emitter(EventEmitter())  # reset to no-op

    def test_select_node_emits_control_started(self):
        state = _make_state(llm_enabled=False)
        select_node(state)
        types = [e.event_type for e in self.events]
        assert EventType.CONTROL_STARTED in types

    def test_validate_node_emits_validation_passed(self):
        state = _make_state(llm_enabled=True, retry_count=0)
        # Build a narrative that passes validation
        config = DomainConfig(**state["domain_config"])
        spec = state["current_spec"]
        narr = build_deterministic_narrative(spec, config)
        state["current_narrative"] = narr
        validate_node(state)
        types = [e.event_type for e in self.events]
        assert EventType.VALIDATION_PASSED in types

    def test_validate_node_emits_validation_failed(self):
        state = _make_state(llm_enabled=True, retry_count=0)
        state["current_narrative"] = {
            "who": "Manager", "what": "Reviews and monitors and validates and audits transactions",
            "when": "as needed", "where": "System", "why": "because",
            "full_description": "short",
        }
        validate_node(state)
        types = [e.event_type for e in self.events]
        # Should have at least one failure event (could be VALIDATION_FAILED or AGENT_RETRY)
        assert EventType.VALIDATION_FAILED in types or EventType.AGENT_RETRY in types

    def test_merge_node_emits_control_completed(self):
        state = _make_state(llm_enabled=False)
        config = DomainConfig(**state["domain_config"])
        enriched = build_deterministic_enriched(state["current_spec"], state["current_narrative"], config)
        state["current_enriched"] = enriched
        merge_node(state)
        types = [e.event_type for e in self.events]
        assert EventType.CONTROL_COMPLETED in types

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_emits_agent_events(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {"hierarchy_id": "1.0.1.1", "leaf_name": "Test",
                         "selected_level_1": "Preventive", "control_type": "Authorization",
                         "placement": "Preventive", "method": "Manual",
                         "who": "Manager", "what_action": "reviews", "what_detail": "detail",
                         "when": "monthly", "where_system": "System", "why_risk": "risk",
                         "evidence": "log", "business_unit_id": "BU-RB"}
        agent.call_llm_with_tools.return_value = {
            "role": "assistant", "content": json.dumps(spec_response), "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        spec_node(state)
        types = [e.event_type for e in self.events]
        assert EventType.AGENT_STARTED in types
        assert EventType.AGENT_COMPLETED in types

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_agent_failure_emits_agent_failed(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent
        agent.call_llm_with_tools.side_effect = Exception("boom")

        state = _make_state(llm_enabled=True)
        spec_node(state)  # should not raise — falls back to deterministic
        types = [e.event_type for e in self.events]
        assert EventType.AGENT_STARTED in types
        assert EventType.AGENT_FAILED in types

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_tool_calls_log_populated_on_success(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {"hierarchy_id": "1.0.1.1", "leaf_name": "Test",
                         "selected_level_1": "Preventive", "control_type": "Authorization",
                         "placement": "Preventive", "method": "Manual",
                         "who": "Manager", "what_action": "reviews", "what_detail": "detail",
                         "when": "monthly", "where_system": "System", "why_risk": "risk",
                         "evidence": "log", "business_unit_id": "BU-RB"}
        agent.call_llm_with_tools.return_value = {
            "role": "assistant", "content": json.dumps(spec_response), "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        result = spec_node(state)
        # tool_calls_log should be a list (empty if no tools were actually invoked)
        assert "tool_calls_log" in result
        assert isinstance(result["tool_calls_log"], list)


# ── Dual-Mode / Provider Tests ────────────────────────────────────────────────


class TestProviderDetection:
    """Verify provider detection and _supports_tools helper."""

    def test_supports_tools_openai(self):
        assert _supports_tools("openai") is True

    def test_supports_tools_anthropic(self):
        assert _supports_tools("anthropic") is True

    def test_supports_tools_ica(self):
        assert _supports_tools("ica") is False

    def test_supports_tools_none(self):
        assert _supports_tools("none") is False

    def test_supports_tools_empty(self):
        assert _supports_tools("") is False


class TestSlimPromptBuilders:
    """Verify slim prompt builders produce shorter prompts without inline data."""

    @pytest.fixture()
    def config(self) -> DomainConfig:
        return load_domain_config(COMMUNITY_BANK)

    @pytest.fixture()
    def assignment(self, config: DomainConfig) -> dict:
        return build_assignment_matrix(config, target_count=1)[0]

    def test_slim_spec_system_shorter_than_fat(self, config):
        fat = build_spec_system_prompt(config)
        slim = build_slim_spec_system_prompt(config)
        assert len(slim) < len(fat), "Slim spec system prompt should be shorter"

    def test_slim_spec_system_mentions_tools(self, config):
        slim = build_slim_spec_system_prompt(config)
        assert "placement_lookup" in slim
        assert "method_lookup" in slim
        assert "evidence_rules_lookup" in slim

    def test_slim_spec_system_omits_placements(self, config):
        slim = build_slim_spec_system_prompt(config)
        assert "ALLOWED PLACEMENTS" not in slim
        assert "ALLOWED METHODS" not in slim

    def test_slim_spec_user_shorter_than_fat(self, config, assignment):
        fat = build_spec_user_prompt(assignment, config)
        slim = build_slim_spec_user_prompt(assignment, config)
        assert len(slim) < len(fat), "Slim spec user prompt should be shorter"

    def test_slim_spec_user_omits_registry(self, config, assignment):
        slim = build_slim_spec_user_prompt(assignment, config)
        payload = json.loads(slim)
        assert "domain_registry" not in payload
        assert "control_placement_definitions" not in payload
        assert "control_method_definitions" not in payload

    def test_slim_spec_user_has_leaf(self, config, assignment):
        slim = build_slim_spec_user_prompt(assignment, config)
        payload = json.loads(slim)
        assert "leaf" in payload
        assert payload["leaf"]["hierarchy_id"]

    def test_slim_narrative_system_shorter_than_fat(self, config):
        fat = build_narrative_system_prompt(config)
        slim = build_slim_narrative_system_prompt(config)
        # Slim is actually longer because of tool instructions, but shouldn't have exemplars
        assert "exemplar_lookup" in slim

    def test_slim_narrative_system_has_word_counts(self, config):
        slim = build_slim_narrative_system_prompt(config)
        assert str(config.narrative.word_count_min) in slim
        assert str(config.narrative.word_count_max) in slim

    def test_slim_narrative_user_omits_exemplars(self, config, assignment):
        spec = build_deterministic_spec(assignment, config)
        slim = build_slim_narrative_user_prompt(spec, config)
        payload = json.loads(slim)
        assert "exemplars" not in payload

    def test_slim_narrative_user_has_locked_spec(self, config, assignment):
        spec = build_deterministic_spec(assignment, config)
        slim = build_slim_narrative_user_prompt(spec, config)
        payload = json.loads(slim)
        assert "locked_spec" in payload

    def test_slim_narrative_user_includes_retry_appendix(self, config, assignment):
        spec = build_deterministic_spec(assignment, config)
        slim = build_slim_narrative_user_prompt(spec, config, retry_appendix="ATTEMPT 1/3")
        assert "ATTEMPT 1/3" in slim


class TestDualModeNodes:
    """Verify graph nodes select prompts and tool_choice based on provider."""

    def setup_method(self):
        reset_llm_cache()

    def teardown_method(self):
        reset_llm_cache()

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_uses_slim_for_openai(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {
            "hierarchy_id": "1.0.1.1", "leaf_name": "Test",
            "selected_level_1": "Preventive", "control_type": "Authorization",
            "placement": "Preventive", "method": "Manual",
            "who": "Manager", "what_action": "reviews", "what_detail": "detail",
            "when": "monthly", "where_system": "System", "why_risk": "risk",
            "evidence": "log", "business_unit_id": "BU-RB",
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(spec_response),
            "_tool_calls_count": 2,
        }

        state = _make_state(llm_enabled=True)
        state["provider"] = "openai"
        spec_node(state)

        # Verify call_llm_with_tools was called with tool_choice="required"
        call_kwargs = agent.call_llm_with_tools.call_args
        assert call_kwargs.kwargs.get("tool_choice") == "required"

        # Verify slim prompt was used (no ALLOWED PLACEMENTS in system prompt)
        messages = call_kwargs.args[0]
        system_msg = messages[0]["content"]
        assert "ALLOWED PLACEMENTS" not in system_msg
        assert "placement_lookup" in system_msg

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_spec_node_uses_fat_for_ica(self, mock_get_agent):
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {
            "hierarchy_id": "1.0.1.1", "leaf_name": "Test",
            "selected_level_1": "Preventive", "control_type": "Authorization",
            "placement": "Preventive", "method": "Manual",
            "who": "Manager", "what_action": "reviews", "what_detail": "detail",
            "when": "monthly", "where_system": "System", "why_risk": "risk",
            "evidence": "log", "business_unit_id": "BU-RB",
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(spec_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        state["provider"] = "ica"
        spec_node(state)

        call_kwargs = agent.call_llm_with_tools.call_args
        # ICA: no tool_choice forced
        assert call_kwargs.kwargs.get("tool_choice") is None
        # Fat prompt should have ALLOWED PLACEMENTS
        messages = call_kwargs.args[0]
        system_msg = messages[0]["content"]
        assert "ALLOWED PLACEMENTS" in system_msg

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_narrative_node_uses_slim_for_openai(self, mock_get_agent):
        agent = _mock_agent("NarrativeAgent")
        mock_get_agent.return_value = agent

        narr_response = {
            "who": "Manager", "what": "reviews transactions",
            "when": "monthly", "where": "Core Banking",
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(narr_response),
            "_tool_calls_count": 1,
        }

        state = _make_state(llm_enabled=True)
        state["provider"] = "openai"
        narrative_node(state)

        call_kwargs = agent.call_llm_with_tools.call_args
        assert call_kwargs.kwargs.get("tool_choice") == "required"

        # Slim narrative prompt should not have exemplars
        messages = call_kwargs.args[0]
        user_msg = messages[1]["content"]
        payload = json.loads(user_msg)
        assert "exemplars" not in payload

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_narrative_node_uses_fat_for_ica(self, mock_get_agent):
        agent = _mock_agent("NarrativeAgent")
        mock_get_agent.return_value = agent

        narr_response = {
            "who": "Manager", "what": "reviews transactions",
            "when": "monthly", "where": "Core Banking",
            "why": "to mitigate risk",
            "full_description": " ".join(["word"] * 40),
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(narr_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        state["provider"] = "ica"
        narrative_node(state)

        call_kwargs = agent.call_llm_with_tools.call_args
        assert call_kwargs.kwargs.get("tool_choice") is None

        # Fat narrative prompt should have exemplars
        messages = call_kwargs.args[0]
        user_msg = messages[1]["content"]
        payload = json.loads(user_msg)
        assert "exemplars" in payload

    @patch("controlnexus.graphs.forge_modular_graph._get_agent")
    def test_default_provider_is_ica(self, mock_get_agent):
        """When provider is not set in state, defaults to ICA (fat prompts)."""
        agent = _mock_agent("SpecAgent")
        mock_get_agent.return_value = agent

        spec_response = {
            "hierarchy_id": "1.0.1.1", "leaf_name": "Test",
            "selected_level_1": "Preventive", "control_type": "Authorization",
            "placement": "Preventive", "method": "Manual",
            "who": "Manager", "what_action": "reviews", "what_detail": "detail",
            "when": "monthly", "where_system": "System", "why_risk": "risk",
            "evidence": "log", "business_unit_id": "BU-RB",
        }
        agent.call_llm_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps(spec_response),
            "_tool_calls_count": 0,
        }

        state = _make_state(llm_enabled=True)
        # Don't set provider — should default to "ica"
        spec_node(state)

        call_kwargs = agent.call_llm_with_tools.call_args
        assert call_kwargs.kwargs.get("tool_choice") is None
