# Test Gap Analysis

> Generated during the Phase 5 code review. Identifies source modules without
> dedicated test coverage and suggests priorities for future test work.

## Coverage Summary

| Test file | Modules covered | Tests |
|---|---|---:|
| `test_validator.py` | `validation/validator.py`, `core/scoring.py` (via re-export) | 22 |
| `test_tracing.py` | `tracing/db.py`, `tracing/listener.py`, `tracing/decorators.py` | 20 |
| `test_models.py` | `core/models.py` | 18 |
| `test_ingest.py` | `ingest/regulation_parser.py`, `ingest/apqc_loader.py`, `ingest/control_loader.py` | 8 |
| `test_assess_graph.py` | `graphs/assess_graph.py`, `graphs/assess_state.py` | 6 |
| `test_classify_graph.py` | `graphs/classify_graph.py`, `graphs/classify_state.py` | 4 |
| **Total** | | **78** |

## Untested Modules

### Priority 1 — Business Logic (High Value, Easy to Test)

| Module | Lines | Why |
|---|---:|---|
| `agents/obligation_classifier.py` | 172 | Core classification logic; deterministic fallback is pure function |
| `agents/apqc_mapper.py` | 158 | Mapping logic; deterministic fallback is testable without LLM |
| `agents/coverage_assessor.py` | ~150 | Coverage assessment; 3-layer matching is deterministic |
| `agents/risk_extractor_scorer.py` | 158 | Risk scoring; deterministic fallback builds dicts from inputs |
| `agents/base.py` | 199 | AgentContext, call_llm wrapper, registry — foundational |
| `core/scoring.py` | 17 | Already tested via `test_validator.py` re-export; could add direct tests |
| `core/constants.py` | ~120 | Constants — low risk, but a smoke-test import would catch typos |

### Priority 2 — Infrastructure (Medium Value)

| Module | Lines | Why |
|---|---:|---|
| `core/transport.py` | 290 | AsyncTransportClient; requires mocking httpx |
| `core/config.py` | ~80 | PipelineConfig loader; YAML parsing is testable |
| `core/events.py` | ~60 | EventEmitter — partially tested via `test_tracing.py` integration |
| `export/excel_export.py` | 161 | Excel generation; testable with BytesIO + openpyxl read-back |
| `export/formatting.py` | 14 | Trivial `display_col_name()`; low risk |
| `ingest/utils.py` | 14 | `clean_str()` — trivial but easy to test |
| `graphs/graph_infra.py` | ~100 | GraphInfra class — tested indirectly via graph tests |

### Priority 3 — UI (Low Value for Unit Tests)

| Module | Lines | Why |
|---|---:|---|
| `ui/app.py` | 157 | Thin entry point; test via Streamlit AppTest or manual QA |
| `ui/upload_tab.py` | 460 | Heavy Streamlit widget usage; best tested with AppTest |
| `ui/review_tabs.py` | 331 | Same — Streamlit-dependent |
| `ui/results_tab.py` | 174 | Same — matplotlib + Streamlit |
| `ui/traceability_tab.py` | 280 | Same |
| `ui/components.py` | 234 | `render_html_table` could be unit-tested (HTML output) |
| `ui/checkpoint.py` | 180 | `save_checkpoint`/`load_checkpoint` — testable with temp dirs |
| `ui/session_keys.py` | 50 | Constants class — no logic |

## Recommended Next Steps

1. **Agent deterministic fallbacks** — Write tests for each agent's `_deterministic_fallback()` method.
   These are pure functions that take context dicts and return structured output; no LLM needed.

2. **Export round-trip** — `export_for_review()` → `import_reviewed()` round-trip with a few sample records.

3. **Config loader** — Test `default_config_path()`, `load_pipeline_config()`, edge cases.

4. **Checkpoint I/O** — Test `save_checkpoint()` / `load_checkpoint()` / `list_checkpoints()` with temp dirs.

5. **Transport provider detection** — Mock env vars and verify ICA vs OpenAI vs deterministic selection.
