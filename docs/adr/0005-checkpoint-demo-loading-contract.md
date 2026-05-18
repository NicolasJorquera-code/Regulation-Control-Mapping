# ADR 0005 -- Checkpoint loading is the demo contract

**Status:** Accepted
**Date:** captured retroactively during the github-ready cleanup pass

## Context

The pipeline is expensive to run end-to-end (many LLM calls, several
minutes wall-clock). For demos, code reviews, and tab-by-tab UI
development, the team needs a reliable way to show every downstream
tab populated with realistic output without re-running the agents.

## Decision

`data/checkpoints/*.json` is the canonical demo surface. Each
checkpoint is a JSON object whose top-level keys correspond directly to
keys in `st.session_state`. The `apply_checkpoint(data)` function in
`ui/components.py` blindly copies every top-level key into
`st.session_state` and triggers `st.rerun()`. The downstream tabs read
from session state and have no awareness of whether the data came from
a live pipeline run or a checkpoint.

The **Resume from Checkpoint** dropdown (rendered by
`render_checkpoint_load(...)`, called from Tab 1) lists every JSON file
under `data/checkpoints/`. There is no auto-load on startup -- the user
must select and click "Load".

## Consequences

**Positive**
- Visible output of a loaded checkpoint must match what a live pipeline run produces for the same input. This is the contract that gates any change to graph terminal nodes (which is exactly why the deterministic review layer landed in `finalize_node`, not as a separate UI-only post-step -- see ADR 0004).
- Tab developers can iterate without ever running the pipeline.
- Resuming a partially-failed run is the same code path as loading a demo.

**Negative**
- Any structural change to a top-level state key (rename, schema change) breaks every existing checkpoint. There is no migration framework.
- `apply_checkpoint()` does not validate the shape; missing keys produce a soft warning, not an error.
- Trace data is not in the checkpoint, so the Evaluation tab is empty when only a checkpoint is loaded (see ADR 0003).

## Invariants the cleanup pass must preserve

1. The dropdown remains; default behaviour (no auto-load on startup) is unchanged.
2. The JSON shape of existing `Full_Assessment_*.json` and `*Patched*.json` files is not modified by any code change.
3. `apply_checkpoint()` semantics (blindly copy keys, rerun) do not change.
4. New behaviour added to `finalize_node` / `end_classify_node` must be **idempotent on already-stamped checkpoints** -- the review layer's `annotate_artifact` satisfies this by merging rather than replacing.

## Alternatives considered

- **Auto-load most recent checkpoint on startup.** A helper `_load_demo_data()` exists in `ui/upload_tab.py` but is not called. Per owner, the dropdown is the demo path -- preserved.
- **Versioned schema with migrations.** Rejected for now: not enough churn in the state shape to justify the tooling.
