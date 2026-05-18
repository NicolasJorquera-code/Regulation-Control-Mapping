# Scripts

Reusable utilities. Run from the repo root with the project venv
activated.

| Script | Purpose | When to run |
|---|---|---|
| `fix_risk_dedup.py` | Deduplicate `scored_risks` in a `Full_Assessment_*.json` checkpoint, keeping one risk per `(source_citation, risk_category)` with the highest impact x frequency. Re-sequences risk IDs and updates `compliance_matrix` / `risk_register` references. Writes a `*_deduped_*.json` next to the input. | If a live pipeline run produced duplicate risks (rare since `core/scoring.deduplicate_risks` is applied in `finalize_node`, but useful for older checkpoints). |
| `patch_checkpoint.py` | Apply schema migrations / field additions to existing checkpoints in `data/checkpoints/`. | When the checkpoint schema changes and old demos need to keep working. |
| `patch_improvements.py` | Backfill `proposed_improvements` into a checkpoint produced before `ControlImprovementAgent` was wired in. | One-off; kept for parity with older demo files. |
| `generate_synthetic_policies.py` | Generate a synthetic `Source_Inventory` workbook for testing the policy-led ingest path without real internal policies. | When testing policy-mode features without real data. |

Each script has a docstring at the top explaining its CLI. Run with `--help` or read the file for arguments.
