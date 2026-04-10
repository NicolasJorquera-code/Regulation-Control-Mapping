# ControlForge Modular — Testing Guide

This document describes how the LLM Agent Integration changes frontend and backend testing for the ControlForge Modular pipeline.

---

## 1. Test Architecture

The modular graph has **two execution paths** controlled by the `llm_enabled` flag:

| Path | `llm_enabled` | What runs | Speed | Needs credentials |
|------|--------------|-----------|-------|-------------------|
| **Deterministic** | `False` | `build_deterministic_spec()`, `build_deterministic_narrative()`, `build_deterministic_enriched()` | Fast (~0.5s for 50 controls) | No |
| **LLM** | `True` | `SpecAgent → NarrativeAgent → Validator → EnricherAgent` with config-aware prompts | Slow (~2-5s per control) | Yes |

Both paths share the same graph topology (8 nodes). The only difference is which code path each agent node takes internally.

### Testing principle

> **All tests run without LLM credentials.** LLM calls are mocked in unit tests. Integration tests with real credentials are optional and run manually.

---

## 2. Test Classes

### Existing (unchanged)

| Class | File | Tests | What it covers |
|-------|------|-------|----------------|
| `TestAssignmentMatrix` | `test_forge_modular_graph.py` | 4 | Assignment matrix builder: correct count, field presence, custom weights, banking standard |
| `TestDeterministicBuilders` | `test_forge_modular_graph.py` | 3 | Deterministic spec/narrative/enriched builders |
| `TestForgeGraph` | `test_forge_modular_graph.py` | 8 | Full graph execution: count, IDs, type codes, looping, deterministic output, custom distribution |

### New

| Class | File | Tests | What it covers |
|-------|------|-------|----------------|
| `TestGraphTopology` | `test_forge_modular_graph.py` | 5 | Node count verification (8), deterministic path output, `llm_enabled` propagation, `after_validate` routing |
| `TestLLMNodes` | `test_forge_modular_graph.py` | 10 | Mock-based LLM node testing: each agent node calls LLM when enabled, falls back on error, works in deterministic mode, handles None client |
| `TestValidationRetryLoop` | `test_forge_modular_graph.py` | 5 | Validation behavior: passes deterministic, catches vague_when, increments retry_count, forces pass at max retries, builds retry_appendix |
| `TestPromptTemplates` | `test_forge_modular_graph.py` | 8 | Config-aware prompt verification: placements/methods in spec prompt, word counts in narrative prompt, quality ratings in enricher prompt, valid JSON structure |
| `TestCustomWordCountLimits` | `test_validator.py` | 6 | Validator with custom min_words/max_words: passes/fails with custom limits, default params unchanged, retry appendix uses custom limits |

---

## 3. Mock Strategy

### Mocking the LLM client

The LLM nodes in `forge_modular_graph.py` call `build_client_from_env()` to get an `AsyncTransportClient`. In tests, we patch this:

```python
from unittest.mock import AsyncMock, MagicMock, patch

def _mock_client():
    client = MagicMock()
    client.model = "test-model"
    client.chat_completion = AsyncMock()
    return client

@patch("controlnexus.graphs.forge_modular_graph.build_client_from_env")
def test_spec_node_calls_llm(mock_build):
    mock_client = _mock_client()
    mock_build.return_value = mock_client

    # Configure the LLM response
    mock_client.chat_completion.return_value = {
        "choices": [{"message": {"content": '{"hierarchy_id": "1.0.1.1", ...}'}}],
        "usage": {},
    }

    state = _make_state(llm_enabled=True)
    result = spec_node(state)
    assert result["current_spec"]["hierarchy_id"] == "1.0.1.1"
    mock_client.chat_completion.assert_called_once()
```

### Key mock patterns

1. **Patch target**: Always patch `controlnexus.graphs.forge_modular_graph.build_client_from_env` (the import location, not the definition location)
2. **Return `None`** to test the "no credentials" fallback path
3. **Raise `Exception`** to test the error fallback path
4. **Return valid JSON** wrapped in OpenAI-style response format to test the happy path

### The `_make_state()` helper

Tests use `_make_state(llm_enabled=True, **overrides)` to build a minimal `ForgeState` dict with all required fields pre-populated from a real community bank config.

---

## 4. Validation Retry Testing

The validation retry loop works as follows:

```
narrative_node → validate_node →
    ├── passed=True → enrich_node
    └── passed=False, retry_count < 3 → narrative_node (with retry_appendix)
    └── passed=False, retry_count >= 3 → force pass → enrich_node
```

### Testing without LLM

When `llm_enabled=False`, `validate_node` always returns `validation_passed=True` because deterministic output is trusted. No retry loop occurs.

### Testing the retry loop

To test retry behavior, construct a state with `llm_enabled=True` and inject a narrative that fails validation:

```python
def test_validate_catches_vague_when(self):
    state = _make_state(llm_enabled=True)
    state["current_narrative"] = {
        "who": state["current_spec"]["who"],
        "what": "reviews",
        "when": "as needed",  # <-- triggers VAGUE_WHEN
        "where": state["current_spec"]["where_system"],
        "why": "to mitigate risk",
        "full_description": " ".join(["word"] * 40),
    }
    result = validate_node(state)
    assert result["validation_passed"] is False
    assert "VAGUE_WHEN" in result["validation_failures"]
```

### Config-driven word count validation

The validator reads `config.narrative.word_count_min` and `config.narrative.word_count_max` from DomainConfig instead of using hardcoded 30/80. Test this by passing custom limits:

```python
result = validate(narrative, spec, min_words=20, max_words=100)
```

---

## 5. Config-Aware Prompt Verification

Each prompt builder function takes a `DomainConfig` and produces a string. Tests verify that the config values appear in the output:

```python
def test_spec_system_prompt_includes_placements(self, config):
    prompt = build_spec_system_prompt(config)
    for name in config.placement_names():
        assert name in prompt
```

The prompt templates replace hardcoded values with config-driven ones:

| Agent | Hardcoded (before) | Config-driven (now) |
|-------|-------------------|---------------------|
| SpecAgent system prompt | Evidence quality rules inline | `config.control_types[].evidence_criteria` |
| SpecAgent system prompt | Placement/method lists missing | `config.placement_names()`, `config.method_names()` |
| NarrativeAgent system prompt | "30 and 80 words" | `config.narrative.word_count_min/max` |
| NarrativeAgent system prompt | Field names only | `config.narrative.fields` with definitions |
| EnricherAgent system prompt | "Strong, Effective, Satisfactory, Needs Improvement, Weak" | `config.quality_ratings` |
| EnricherAgent system prompt | "30 and 80 words" | `config.narrative.word_count_min/max` |
| Validator | `MIN_WORDS=30`, `MAX_WORDS=80` | Optional `min_words`, `max_words` params |

---

## 6. Frontend Testing Implications

### What changed in the Streamlit tab

The `modular_tab.py` now includes:

1. **`st.toggle("Enable LLM Generation")`** — a boolean toggle in the Generation Settings section
2. **Credential check warning** — when toggled on, imports `build_client_from_env()` and shows a `st.warning` if no credentials found
3. **`llm_enabled` in graph input** — the toggle value is passed into `graph.invoke()` as `"llm_enabled": llm_enabled`

### How to manually test the UI

1. **Deterministic mode (default)**: Open the Streamlit app, go to the "ControlForge Modular" tab. The toggle is off by default. Click "Generate Controls" — should produce results identical to before the LLM integration.

2. **LLM toggle without credentials**: Toggle "Enable LLM Generation" on. A warning should appear: "No LLM credentials found." Click "Generate Controls" — should still produce results (deterministic fallback).

3. **LLM toggle with credentials**: Set environment variables (`OPENAI_API_KEY`, `ICA_API_KEY`, or `ANTHROPIC_API_KEY`). Toggle on. Generate controls — should produce LLM-enriched output with varied quality ratings and richer descriptions.

### Automated Streamlit testing

The Streamlit tab can be tested with `pytest` by importing the module and verifying:
- `build_forge_graph()` compiles without error
- The graph produces valid output with both `llm_enabled=True` and `llm_enabled=False`
- The `_load_config()` cached function returns valid `DomainConfig` data

Direct widget testing requires `streamlit.testing.v1.AppTest` (optional).

---

## 7. Running Tests

```bash
# Run only the modular graph tests (fast, no LLM needed)
python3 -m pytest tests/test_forge_modular_graph.py -v

# Run validator tests including custom word count limits
python3 -m pytest tests/test_validator.py -v

# Run both together
python3 -m pytest tests/test_forge_modular_graph.py tests/test_validator.py -v

# Run the full suite (293 passing; 17 pre-existing async failures unrelated to this work)
python3 -m pytest tests/ -v

# Run only the new test classes
python3 -m pytest tests/test_forge_modular_graph.py -k "TestGraphTopology or TestLLMNodes or TestValidationRetryLoop or TestPromptTemplates" -v
python3 -m pytest tests/test_validator.py -k "TestCustomWordCountLimits" -v
```

---

## 8. Integration Testing (Optional)

For end-to-end testing with real LLM credentials:

```bash
# Set credentials
export OPENAI_API_KEY="sk-..."
# or
export ICA_API_KEY="..." && export ICA_BASE_URL="..." && export ICA_MODEL_ID="..."

# Run the graph with LLM enabled
python3 -c "
from controlnexus.graphs.forge_modular_graph import build_forge_graph
graph = build_forge_graph().compile()
result = graph.invoke({
    'config_path': 'config/profiles/community_bank_demo.yaml',
    'target_count': 3,
    'llm_enabled': True,
})
for r in result['plan_payload']['final_records']:
    print(f\"{r['control_id']}: {r['quality_rating']} — {r['full_description'][:80]}...\")
"
```

This will make real LLM API calls and produce richer, more varied control descriptions than the deterministic path.
