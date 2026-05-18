# ADR 0004 -- AI Governance review layer as pure library

**Status:** Accepted
**Date:** captured during the github-ready cleanup pass; reframed during
the LLM-only refactor (see ADR 0006)

## Context

Every artifact the pipeline produces (classification, mapping, coverage
assessment, scored risk, proposed improvement) comes from an LLM and
may or may not need human review. The original design fielded an LLM
that judged its own output for review-worthiness. That fails three
demands:

1. **Auditability.** Regulated environments require rule-based, named
   reason codes for any flag that lands in front of a human -- "the
   model said so" is not an audit trail.
2. **Reproducibility.** The same artifact must produce the same review
   verdict every time.
3. **Cost.** Running an LLM judge on every artifact doubles token spend.

## Decision

Implement review as a **pure Python library** in `src/regrisk/core/review.py`
-- the **AI Governance layer** that runs software checks on every LLM output:

- One `review_<artifact>` function per artifact type:
  `review_source`, `review_classification`, `review_mapping`,
  `review_coverage`, `review_risk`, plus `review_procedure_contradictions`
  for cross-cutting rules.
- Each returns a list of reason codes (constants from `core/constants.py`).
- A 14-reason catalogue covers lifecycle, ownership, coverage, mapping
  fanout, traceability, evidence, residual risk, classification gaps,
  and procedure-vs-policy contradictions.
- `annotate_artifact(dict, reasons)` stamps `needs_review` and
  `needs_review_reasons` on the artifact in place. Idempotent.

The library is invoked from the **terminal node of each graph**
(`classify_graph.end_classify_node` and `assess_graph.finalize_node`),
not scattered across every agent node. Centralising at the terminal
node keeps the governance layer single-pass and side-effect-free
relative to the agent logic.

A companion `validation/validator.py` enforces schema + categorical-value
correctness on each LLM response (e.g., a category value must be one of
the configured categories). Together, validator + review form the AI
Governance layer described in ADR 0006.

## Consequences

**Positive**
- Every flag traces to a named reason code.
- No LLM cost for review itself.
- Tests for review live entirely in `tests/test_review.py` with no API mocking.

**Negative**
- New review reasons require a code change, not a config edit.
- Rules that genuinely benefit from semantic judgment cannot be expressed here.

## Alternatives considered

- **LLM-as-judge per artifact.** Rejected for the reasons above.
- **Rules in YAML.** Rejected: rule predicates need access to dates, source metadata, fanout counts, and cross-artifact lookups.
