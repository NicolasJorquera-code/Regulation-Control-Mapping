# ADR 0002 -- Config-driven agents with deterministic fallback

**Status:** Accepted
**Date:** captured retroactively during the github-ready cleanup pass

## Context

The pipeline must:

- Run in CI without any API keys (so the test suite is meaningful).
- Be demoable on a laptop without an LLM provider.
- Stay testable by ordinary unit tests that don't need recorded fixtures.

At the same time, agents must produce real LLM-quality output when keys
are available.

## Decision

Every agent class (`obligation_classifier`, `apqc_mapper`,
`coverage_assessor`, `risk_extractor_scorer`, `control_improver`)
subclasses `BaseAgent` and accepts an `AgentContext` with an optional
`client`. Each `execute` method:

1. If `context.client is None`, runs a **deterministic fallback** based
   on keyword heuristics, configured thresholds, and the YAML taxonomy.
2. Otherwise, builds a prompt (with per-source-type fragments from
   `agents/source_type_prompts.py`), calls the LLM, validates the
   response, and falls back to deterministic mode on validation failure.

Domain knowledge (categories, relationship types, criticality tiers,
APQC depth, scoring scales) is **never hard-coded in agents** -- it
lives in `config/default.yaml` and is loaded as `PipelineConfig`. The
risk taxonomy is in `config/risk_taxonomy.json` and threaded through
agent contexts.

## Consequences

**Positive**
- `python -m pytest tests/` runs in ~3s with no network or API keys.
- The pipeline can be demoed offline.
- Changing a taxonomy or threshold is a config edit, not a code edit.
- Validation failure does not crash the pipeline -- it degrades to deterministic mode for that artifact.

**Negative**
- Every agent contains two code paths; deterministic fallbacks can rot relative to LLM expectations.
- Deterministic output is meaningfully lower quality (especially for `control_improver`).

## Alternatives considered

- **LLM-only with mocked responses in tests.** Rejected: brittle, makes the pipeline unusable for live demos without keys.
- **Move deterministic fallbacks into a single "DeterministicAgent" facade.** Rejected: would couple all agents to a shared fallback that doesn't know per-agent context.
