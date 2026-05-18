# ADR 0001 -- LangGraph orchestration with two graphs

**Status:** Accepted
**Date:** captured retroactively during the github-ready cleanup pass

## Context

The pipeline has a natural human-in-the-loop checkpoint between
classification and the rest of the work: a compliance analyst should
review the auto-classified obligations (category / relationship type /
criticality) before any expensive APQC mapping or coverage assessment
runs against them.

## Decision

Implement the pipeline as **two LangGraph `StateGraph`s** rather than
one:

- **Graph 1 (`classify_graph`):** ingest -> classify (looping per group) -> end.
- **Graph 2 (`assess_graph`):** map -> assess coverage -> extract & score risks -> propose improvements -> finalize.

The bridge is `st.session_state`. The Streamlit UI runs Graph 1, hands
the result to the Classification Review tab, lets the analyst approve /
edit / re-run, then triggers Graph 2 with the approved obligations.

## Consequences

**Positive**
- Human review is a first-class checkpoint, not an afterthought wrapped in conditional edges.
- Each graph has a simple linear-plus-self-loop topology that is easy to reason about.
- Failure of Graph 2 leaves the classification artifact intact for resumption.
- Checkpoint persistence between graphs is trivial (just serialize session_state at the bridge).

**Negative**
- The two graphs share `GraphInfra` (`graphs/graph_infra.py`) but it must be reset between runs.
- Tracing must be initialised separately for each graph (see ADR 0003).
- The state TypedDicts are not unified -- duplication of common keys.

## Alternatives considered

- **Single graph with a human-review conditional node.** Rejected: would require an `interrupt()` and complicate failure recovery.
- **Per-obligation parallelism via LangGraph's parallel branches.** Rejected: the per-group loop is enough; per-obligation parallelism would require careful rate-limiting against the LLM provider and was out of scope.
