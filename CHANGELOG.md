# Changelog

All notable changes to regrisk are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] -- 2026 cleanup pass (`cleanup/github-ready-pass`)

### Added
- `core/review.py` is now invoked from both LangGraph terminal nodes (`classify_graph.end_classify_node`, `assess_graph.finalize_node`). Live pipeline runs now stamp `needs_review` + `needs_review_reasons` on every classification, mapping, coverage assessment, and scored risk -- matching what preloaded demo checkpoints have always carried.
- `README.md` rewritten from scratch with overview, mermaid architecture, project structure, setup, run, demo walkthrough, extending guide, configuration reference, and known limitations.
- `CONTRIBUTING.md` with branch naming, commit conventions, a four-step new-agent recipe, a new-demo-checkpoint recipe, the smoke-check command, and a list of no-touch zones.
- `.env.example` with ICA and OpenAI placeholders and a note that the pipeline runs in deterministic mode without any keys.
- `docs/cleanup-audit.md` documenting the Phase 1 audit that gated the cleanup.
- `docs/adr/0001..0005` Architecture Decision Records covering the two-graph orchestration, config-driven agents with deterministic fallback, SQLite tracing, deterministic review layer, and checkpoint-loading demo contract.
- `docs/known-gaps.md` listing deferred items and owner-decision flags.
- `data/README.md` and `scripts/README.md`.

### Changed
- Repository layout reorganized: `doc/` -> `docs/`, `flowchart TB.mmd` -> `docs/architecture.mmd`.
- `_fix_risk_dedup.py` promoted to `scripts/fix_risk_dedup.py`.
- "Executive View" removed from `config.ui.visible_tabs` and from the tab registry (the implementation is now gone; the tab was already disabled in practice).
- `.gitignore` now excludes the local `archive/` staging directory.

### Removed (moved to local `archive/`, not committed)
- `_check_schema.py`, `_fix_app_conflict.py`, `_test_card.py` (top-level scratch scripts).
- `langgraph-multiagent-skeleton/` (unused skeleton).
- `src/regrisk/ui/data_explorer_tab.py` (was already unwired).
- Stale planning and presentation docs from the old `doc/`.

### Verified
- `python -m pytest tests/ -q` -- 136 passed in ~3s.
- Both graphs build with no API keys (`build_classify_graph()`, `build_assess_graph()`).
- Demo dropdown discovers 31 checkpoints from `data/checkpoints/`.
- Functional smoke of the deterministic review layer produces the expected reason codes (`missing_source_owner`, `orphan_procedure`, `unclassified_requirement`).

### Owner decisions outstanding
- Pick a LICENSE (none currently declared in `pyproject.toml` or repo root).
- Rotate the ICA API key currently in the local `.env` (never committed).
- Confirm the verdicts on `archive/data_explorer_tab.py`, `archive/_test_card.py`, and the `fix_risk_dedup.py` promotion.

See `docs/cleanup-audit.md` and `docs/known-gaps.md` for full context.
