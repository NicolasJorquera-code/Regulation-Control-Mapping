# ADR 0006 -- LLM is required; AI Governance replaces deterministic fallbacks

**Status:** Accepted
**Date:** 2026 refactor pass (`refactor/llm-only-and-ai-governance`)
**Supersedes:** [ADR 0002](0002-config-driven-agents.md) (the "deterministic
fallback" half of that decision)
**Relates to:** [ADR 0004](0004-ai-governance-review-layer.md)

## Context

ADR 0002 fielded each agent with two code paths: a real LLM call and a
keyword-based "deterministic fallback" that ran when no API key was
configured. The fallback was originally justified by three demands:
CI runs without keys, offline laptop demos, and unit tests that don't
need recorded fixtures.

In practice the fallback created more problems than it solved:

1. **Two divergent code paths per agent.** The fallback was meaningfully
   lower quality (especially for `control_improver`, which produced
   skeleton controls indistinguishable from each other) and rotted
   relative to the LLM expectations.
2. **Misleading framing.** "Deterministic mode" suggested a parallel
   product the team intended to support. In reality it was a CI shim
   that no one shipped.
3. **Wrong governance model.** Compliance auditability does not come
   from running a second non-LLM pipeline in parallel; it comes from
   running **software checks ON the LLM output** (schema validation,
   categorical-value enforcement, named-reason review flags). That
   layer already existed in `validation/validator.py` and
   `core/review.py`; it just needed to be the only story.

## Decision

regrisk is an **LLM-driven pipeline**. There is no fallback agent code
path. Concretely:

1. `BaseAgent.call_llm` and `BaseAgent.call_llm_with_tools` raise
   `LLMRequiredError` if `context.client is None`.
2. Every agent (`obligation_classifier`, `apqc_mapper`,
   `coverage_assessor`, `risk_extractor_scorer`, `control_improver`)
   has had its keyword-based fallback removed. Each `execute` builds a
   prompt, calls the LLM, parses + validates the response, and returns
   it. If the LLM returns nothing usable, the result is empty (no
   synthesised data).
3. The Streamlit UI checks for `ICA_API_KEY` / `OPENAI_API_KEY` at
   launch-button click and shows a blocking error pointing to
   `.env.example` if neither is present. The "Resume from Checkpoint"
   dropdown still works without keys (it loads pre-recorded outputs).
4. Tests use a `StubLLMClient` (`tests/_stub_llm.py`) that exercises
   the **real LLM code path** (prompt build -> chat_completion -> JSON
   parse -> validation -> AI governance review) with deterministic
   canned responses. CI runs in seconds with no API keys, and the
   test suite covers the same code path production does.

The **AI Governance layer** is the renaming of what previously called
itself "the deterministic review layer." It is the union of:

- `validation/validator.py` -- schema and categorical-value checks on
  every LLM response.
- `core/review.py` -- 14 named-reason rules that stamp `needs_review`
  on every artifact at the terminal node of each graph (see ADR 0004).
- Per-call tracing (see ADR 0003) -- every LLM call is captured with
  prompt, response, latency, tokens, and validation outcome.

Future governance work (categorical-value tightening, output diffing
against prior runs, drift detection) extends this layer, not the agents.

## Consequences

**Positive**
- One code path per agent. Reading any agent file shows the full story.
- Honest framing: regrisk is an AI product with rule-based software
  checks running on the AI output. That maps directly to how regulated
  AI deployments are governed.
- Tests still run in <3s with no API keys.
- The UI cannot silently produce skeleton output when keys are
  misconfigured.

**Negative**
- The pipeline cannot run end-to-end without an LLM provider. The
  demo experience for someone with no keys is now: load a checkpoint
  from `data/checkpoints/`, browse the tabs. (This matches ADR 0005:
  checkpoint loading was already the canonical demo path.)
- CI must continue to maintain `StubLLMClient` in lock-step with prompt
  / schema changes -- not free, but cheap.

## Alternatives considered

- **Keep deterministic fallbacks, just rename them "no-LLM mode."**
  Rejected: the framing was the smallest problem; the code-rot and
  silent-degradation problems remained.
- **Record real LLM responses as fixtures.** Rejected: fixture
  maintenance is heavier than the stub, and fixtures bind the test
  suite to specific provider responses.
