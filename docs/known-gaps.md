# Known gaps

Items the cleanup pass deliberately deferred. None of these block
demo or test functionality.

## Deferred -- LICENSE not declared

`pyproject.toml` has no `license` field and there is no `LICENSE` file
in the repo root. The owner must pick a license before publishing
(Apache-2.0 and MIT are the common choices for tooling like this).

## Deferred -- no CI / pre-commit

No GitHub Actions workflow, no pre-commit config, no formatter pinning.
The smoke check command in `CONTRIBUTING.md` is the manual substitute.
Adding CI is a clean follow-up once the repo lives on GitHub.

## Deferred -- pinned dependency lockfile

`pyproject.toml` uses lower bounds only (e.g., `langgraph>=0.2`). For
reproducible deployments a lockfile (`uv.lock`, `requirements.lock`, or
`poetry.lock`) should be generated.

## Deferred -- evaluation tab requires a live run

The Evaluation tab is empty when only a preloaded checkpoint is in
session state. This is intentional (trace data is engineering
telemetry, not part of the artifact contract -- see
[ADR 0003](adr/0003-sqlite-tracing.md)). Future work could either
(a) ship a sample `traces.db` separately, or (b) embed a representative
trace snapshot in checkpoints.

## Deferred -- single-writer trace database

`data/traces.db` is SQLite and does not support concurrent writers.
Acceptable for the single-user demo workflow; would need to move to a
proper backing store for any multi-user deployment.

## Deferred -- no agent-level rate limiting

The per-group loops in both graphs do not implement rate limiting
against the LLM provider. Live runs against ICA or OpenAI rely on the
provider's own throttling. A small token-bucket in `GraphInfra` would
be the natural place to add this.

## Owner-decision items raised by this cleanup pass

- `archive/data_explorer_tab.py` -- moved out of the runtime tree. Confirm: archive permanently, delete, or revive as a Tab 7?
- `archive/_test_card.py` -- top-level smoke script. Confirm: archive permanently or migrate into `tests/`?
- `scripts/fix_risk_dedup.py` (promoted from `_fix_risk_dedup.py`) -- confirm the promotion is desired, or move back to archive.
- `.env` on disk contains a real ICA API key (never committed). Rotate.
