# ControlNexus

An intelligent internal controls management system that identifies gaps in financial control ecosystems and generates remediation controls using a multi-agent LLM pipeline.

## Overview

ControlNexus operates in four layers:

1. **Risk Inventory Builder** -- Creates process-specific risk inventory records with inherent risk, control mapping, control environment, residual risk, review/challenge, executive reporting, and Excel export.
2. **Analysis** -- Ingests existing control populations from Excel, runs deterministic scanners, and produces a weighted gap report.
3. **Dashboard** -- Streamlit-based HITL (Human-in-the-Loop) interface for reviewing risk inventory, controls, gaps, remediation targets, and agents.
4. **Remediation** -- LangGraph-orchestrated multi-agent pipeline that generates new controls via SpecAgent, NarrativeAgent, EnricherAgent with deterministic validation, adversarial review, and deduplication.

## Quick Start

### Prerequisites

- Python 3.11+
- (Optional) An LLM API key for production-quality narrative generation

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd ControlNexus

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Configuration

```bash
# Copy and edit environment variables
cp .env.example .env
```

Supported LLM providers (configure one in `.env`):

| Provider | Variables |
|----------|-----------|
| IBM Cloud AI (ICA) | `ICA_BASE_URL`, `ICA_API_KEY`, `ICA_MODEL` |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Anthropic | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

> **Note:** All agents have deterministic fallback paths. The system runs fully without LLM credentials -- LLM is only needed for production-quality control narrative generation.

### Run the Dashboard

```bash
streamlit run src/controlnexus/ui/app.py
```

Opens at `http://localhost:8501` with five tabs:
- **Risk Inventory Builder** -- Build an executive risk inventory workbench with modular knowledge packs, deterministic scoring, control gaps, review, and Excel export
- **Control Builder** -- Create DomainConfig profiles
- **ControlForge Modular** -- Browse config profiles and run control generation
- **Analysis** -- Upload Excel, run gap analysis, view gap dashboard
- **Playground** -- Select and test any registered agent interactively

### Run Tests

```bash
# Full test suite
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type check
mypy src/controlnexus/ --ignore-missing-imports
```

### Docker

```bash
docker build -t controlnexus .
docker run -p 8501:8501 --env-file .env controlnexus
```

## Project Structure

```
src/controlnexus/
  core/           Models, state, config, constants, transport
  risk_inventory/ Risk inventory models, calculators, graph, demo, export
  agents/         SpecAgent, NarrativeAgent, EnricherAgent,
                  AdversarialReviewer, DifferentiationAgent
  analysis/       Excel ingest, 4 scanners, analysis pipeline
  validation/     6-rule deterministic validator
  graphs/         LangGraph state definitions + analysis/remediation graphs
  hierarchy/      APQC hierarchy parser (Excel/CSV) + scope selection
  pipeline/       Async orchestrator for control generation (3-phase)
  remediation/    Planner, 4 gap-type path handlers
  memory/         ChromaDB vector store + embedder protocol
  tools/          5 function-calling tools + LangGraph ToolNode
  export/         Excel export for FinalControlRecord
  ui/             Streamlit dashboard (5 tabs)

config/
  risk_inventory/          Risk inventory scoring matrices and rules
  taxonomy.yaml             Control type taxonomy
  standards.yaml            5W standards, phrase bank, quality ratings
  placement_methods.yaml    Placement + method taxonomy
  sections/section_*.yaml   Per-section profiles (13 sections)

tests/                      Unit + integration + e2e coverage
```

## Risk Inventory Demo Mode

The Risk Inventory Builder tab includes a top-right **Demo Mode** toggle. Turning it on loads one deterministic process workspace: `Payment Exception Handling` in `Payment Operations`, with mapped controls, KRIs, obligations, issues, evidence, public-source trace, validation findings, and executive Excel export.

The demo UI opens directly into the selected process workbench: choose a risk from the left queue and review the full command-view profile, including impact, frequency, inherent risk, residual risk, controls, gaps, synthetic controls, KRIs, evidence, mitigation, validation owner, and review/challenge fields.

The Excel export is a focused scenario artifact with a cover tab, process risk inventory, control gaps, synthetic control recommendations, KRI dashboard, reviewer decision log, source trace, and config snapshot.

The non-demo Knowledge Base view supports local ingestion of PDF, TXT, and Markdown policy or process documents. Uploaded documents are parsed into process context, risk-category cues, control cues, exposure signals, obligations, systems, and stakeholders before the deterministic graph runs.

APQC crosswalk metadata is optional and used only for process normalization and source trace. It does not generate risk statements, controls, or ratings.

See [docs/RISK_INVENTORY_BUILDER.md](docs/RISK_INVENTORY_BUILDER.md) for details.

## Data Flow

### Gap Analysis (Analysis Tab)

```
Excel Upload --> ingest_excel() --> FinalControlRecord[]
    --> 4 scanners (regulatory, balance, frequency, evidence)
    --> GapReport (weighted score 0-100)
    --> plan_assignments() --> route_assignment()
    --> SpecAgent --> NarrativeAgent --> Validator (retry <= 3)
    --> EnricherAgent --> quality gate --> dedup check
    --> FinalControlRecord[] --> export_to_excel()
```

### Control Generation (ControlForge Tab)

```
APQC Template (Excel) --> load_apqc_hierarchy() --> HierarchyNode[]
    --> select_scope(sections) --> leaf nodes
    --> Orchestrator.execute_planning()
        Phase 1: Deterministic defaults (type, placement, BU, 5W)
        Phase 2: Optional async LLM enrichment (Spec/Narrative/Enricher)
        Phase 3: Merge + assign CTRL IDs --> FinalControlRecord[]
    --> export_to_excel()
```

## Programmatic Usage

### Gap Analysis

```python
from pathlib import Path
from controlnexus.analysis.ingest import ingest_excel
from controlnexus.analysis.pipeline import run_analysis
from controlnexus.core.config import load_all_section_profiles

controls = ingest_excel(Path("data/my_controls.xlsx"))
profiles = load_all_section_profiles(Path("config"))
gap_report = run_analysis(controls, profiles)

print(f"Score: {gap_report.overall_score}/100")
print(f"Summary: {gap_report.summary}")
```

### Control Generation

```python
import asyncio
from pathlib import Path
from controlnexus.core.models import RunConfig, ScopeConfig, SizingConfig
from controlnexus.pipeline import Orchestrator

run_config = RunConfig(
    run_id="my-run",
    scope=ScopeConfig(sections=["4", "9"]),
    sizing=SizingConfig(target_count=100, dry_run_limit=20),
)
orchestrator = Orchestrator(run_config, project_root=Path("."))
result = asyncio.run(orchestrator.execute_planning(Path("config")))

print(f"Generated: {len(result.final_records)} controls")
print(f"Sections: {list(result.section_allocation.keys())}")
```

## Score Weights

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Regulatory Coverage | 40% | Framework keyword coverage per section |
| Ecosystem Balance | 25% | Control type distribution vs. expected ranges |
| Frequency Coherence | 15% | Frequency alignment with control type expectations |
| Evidence Sufficiency | 20% | Artifact name, preparer sign-off, retention location |

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
1. **Lint** -- `ruff check` + `ruff format --check`
2. **Type Check** -- `mypy` with strict mode
3. **Test** -- `pytest` with JUnit XML export
4. **Docker Build** -- Buildx with GitHub Actions cache

## Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

Hooks: ruff lint + format, mypy, trailing whitespace, end-of-file, YAML check, large file check, merge conflict check.

## License

Proprietary. All rights reserved.
