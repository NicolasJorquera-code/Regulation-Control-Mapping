# data/

This folder is mostly **gitignored** -- demo workbooks, checkpoints,
and the local SQLite trace database stay on your machine. Track this
README only.

## Expected files

| Path | Source | Used by |
|---|---|---|
| `regulations yy.xlsx` | Promontory-format Federal Reserve Regulation YY obligations export. | `ingest/regulation_parser.py` reads the `Requirements` sheet. |
| `APQC_Template.xlsx` | APQC Process Classification Framework (PCF) hierarchy. | `ingest/apqc_loader.py`. |
| `Control Dataset/section_*__controls.xlsx` | Internal controls inventory, one workbook per APQC section. | `ingest/control_loader.py`. |
| `policy_source_inventory.xlsx` *(optional)* | Internal policy / procedure inventory with a `Source_Inventory` sheet. | Triggers the policy-led ingest path in `ingest/policy_parser.py`. |
| `checkpoints/*.json` | Saved pipeline state -- both auto-saved (during a run) and final (`Full_Assessment_*`, `Patched_*`, `Improved_Patched_*`). | Demo dropdown in `ui/upload_tab.py`. |
| `traces.db` | Local SQLite trace database written by `tracing/TraceDB`. | Evaluation tab. |

## Replacing the demo data

To run regrisk on your own data, drop replacement files with matching
patterns into this folder. The Upload & Configure tab auto-detects them
via `_detect_data_files()` in `ui/upload_tab.py`. No code change
required.

## Why the workbooks are gitignored

These files contain real or licensed content that should not be
distributed via a public repo. The pipeline ships the code; the data is
supplied by the consumer.
