# Regulatory Obligation Control Mapper

A LangGraph-based pipeline that maps regulatory obligations from Federal Reserve Regulation YY to APQC business processes, assesses control coverage, extracts compliance risks, and produces exportable reports.

## Overview

This system takes three inputs:
1. **Regulatory obligations** (693 from 12 CFR 252 — Regulation YY)
2. **APQC Process Classification Framework** (1,803 process nodes)
3. **Internal controls** (520+ controls mapped to APQC processes)

And produces:
- Classified obligations (Attestation, Documentation, Controls, General Awareness, Not Assigned)
- Obligation-to-APQC crosswalk (many-to-many mappings)
- Control coverage assessment (Covered, Partially Covered, Not Covered)
- Risk register with scored risks (4-point impact × frequency)
- Gap analysis with full traceability chains

## Architecture

Two LangGraph state machines with human review checkpoints between them:

- **Graph 1 (Classify):** Ingest → Classify all obligations by section group
- **Graph 2 (Assess):** Map to APQC → Assess coverage → Extract & score risks → Finalize

Human review between graphs is implemented via Streamlit's `st.session_state`.

## Setup

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests (no API keys needed — deterministic mode)
python -m pytest tests/ -v

# Launch the Streamlit UI
python -m streamlit run src/regrisk/ui/app.py
```

## LLM Configuration

Set environment variables for LLM-powered mode:

```bash
# Option 1: IBM Cloud AI (ICA)
export ICA_API_KEY="your-key"
export ICA_BASE_URL="https://your-ica-endpoint"
export ICA_MODEL_ID="your-model"

# Option 2: OpenAI
export OPENAI_API_KEY="your-key"
```

Without any LLM keys, the pipeline runs in **deterministic mode** using keyword-based fallbacks.

## Data Files

Place input files in the `data/` directory:

| File | Description |
|---|---|
| `data/regulations yy.xlsx` | Promontory-format Regulation YY obligations |
| `data/APQC_Template.xlsx` | APQC Process Classification Framework |
| `data/Control Dataset/section_*__controls.xlsx` | Control inventory by APQC section |

## Project Structure

```
src/regrisk/
├── agents/              # LLM agents with deterministic fallbacks
│   ├── base.py          # BaseAgent ABC, AgentContext, registry
│   ├── obligation_classifier.py
│   ├── apqc_mapper.py
│   ├── coverage_assessor.py
│   └── risk_extractor_scorer.py
├── core/                # Config, models, events, constants, transport
│   ├── config.py        # PipelineConfig from YAML
│   ├── constants.py     # Canonical string constants (categories, statuses, etc.)
│   ├── events.py        # EventEmitter with domain events
│   ├── models.py        # Frozen Pydantic domain models
│   ├── scoring.py       # Pure business-logic scoring (impact × frequency)
│   └── transport.py     # AsyncTransportClient (OpenAI-compatible)
├── export/              # Excel export utilities
│   ├── excel_export.py
│   └── formatting.py    # Shared display column name formatting
├── graphs/              # LangGraph state machines
│   ├── classify_graph.py   # Graph 1: Ingest + Classify
│   ├── assess_graph.py     # Graph 2: Map + Assess + Score
│   ├── classify_state.py   # ClassifyState TypedDict
│   ├── assess_state.py     # AssessState TypedDict
│   └── graph_infra.py      # Shared graph infrastructure (caches, emitter)
├── ingest/              # Deterministic data loaders
│   ├── regulation_parser.py
│   ├── apqc_loader.py
│   ├── control_loader.py
│   └── utils.py         # Shared ingest utilities (clean_str)
├── tracing/             # SQLite-backed execution tracing
│   ├── db.py            # TraceDB — run/event/node/LLM-call storage
│   ├── decorators.py    # @trace_node decorator
│   ├── listener.py      # SQLiteTraceListener (EventEmitter → DB)
│   └── transport_wrapper.py  # TracingTransportClient (wraps LLM calls)
├── ui/                  # Streamlit 5-tab application
│   ├── app.py           # Entry point — page config, tabs, status bar
│   ├── components.py    # Shared UI helpers (HTML table, checkpoints, etc.)
│   ├── upload_tab.py    # Tab 1: Upload & Configure
│   ├── review_tabs.py   # Tabs 2 & 3: Classification & Mapping Review
│   ├── results_tab.py   # Tab 4: Coverage, risk heatmap, gap analysis
│   ├── traceability_tab.py  # Tab 5: Execution traces & data lineage
│   ├── checkpoint.py    # Checkpoint save/load/list
│   └── session_keys.py  # Session state key catalog
└── validation/          # Deterministic validators
    └── validator.py
```

## Testing

All tests run without API keys or network access:

```bash
python -m pytest tests/ -v
```

## Key Patterns

1. **Module-level caches** — LLM clients and agents built once, reused across nodes
2. **Annotated[list, operator.add] reducers** — accumulate results across loop iterations
3. **Deterministic fallbacks** — every agent works without LLM (keyword-based)
4. **Event emission** — every node emits typed events for UI progress
5. **Frozen Pydantic models** — immutable pipeline artifacts
6. **Config-driven behavior** — all thresholds from YAML config
7. **Conditional edge functions** — return node name strings for explicit routing
