# ADR 0003 -- SQLite-backed tracing

**Status:** Accepted
**Date:** captured retroactively during the github-ready cleanup pass

## Context

The pipeline issues many LLM calls per run. Engineers maintaining it
need to answer: which calls were slow, which failed validation, which
were expensive, and whether quality is regressing across runs and
models. Operations teams running the demo need this without standing up
external telemetry.

## Decision

Build a local SQLite trace database (`src/regrisk/tracing/db.py` ->
`TraceDB`). Tables:

- `events` -- every domain event emitted via `EventEmitter`.
- `llm_calls` -- every LLM call, with prompt, response, parsed output, tokens, cost estimate, validation pass/fail, retry attempt.
- `run_metrics` -- per-run roll-ups: total tokens, estimated cost, overall pass rate, quality score, coverage percentages.
- `run_comparisons` -- A/B comparison between two runs.

Tracing is wired in via two mechanisms:

1. `TracingTransportClient` (`tracing/transport_wrapper.py`) wraps the
   LLM transport so every call is recorded automatically.
2. `trace_node(...)` (`tracing/decorators.py`) wraps every graph node
   when `trace_db` is passed to `build_classify_graph` /
   `build_assess_graph`.

The Streamlit UI attaches a `TraceDB` to every live run by default.

## Consequences

**Positive**
- No external services. The whole evaluation experience works on a laptop.
- The Evaluation tab (`ui/evaluation_tab.py`) can query the same DB the pipeline writes to.
- Recomputing metrics for past runs is one SQL pass -- see `TraceDB.recompute_all_metrics()`.
- The DB file is in `data/traces.db` which is gitignored.

**Negative**
- SQLite is single-writer; concurrent runs would conflict. Acceptable for the single-user demo workflow.
- No retention policy -- the file grows monotonically.
- **Preloaded checkpoints do not carry trace data.** The Evaluation tab is empty when only the demo is loaded. This is intentional (checkpoints capture pipeline outputs, not the engineering telemetry of how they were produced) but should be documented.

## Alternatives considered

- **LangSmith / Phoenix / OpenTelemetry.** Rejected for the demo phase: adds external dependency and credentials, blocks offline demos.
- **JSON log files.** Rejected: needs custom aggregation tooling; SQL is shorter for the dashboards in the Evaluation tab.
