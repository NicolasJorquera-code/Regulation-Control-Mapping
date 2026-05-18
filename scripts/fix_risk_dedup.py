#!/usr/bin/env python3
"""One-time fix: deduplicate scored risks in a Full_Assessment checkpoint.

For each obligation (source_citation), only one risk per risk_category is
kept — the one with the highest impact × frequency score.  Risk IDs are
re-sequenced (RISK-001, RISK-002, …) and all downstream references
(compliance_matrix, risk_register) are updated accordingly.

Usage:
    python scripts/fix_risk_dedup.py [<checkpoint_path>]

If no path is given the latest Full_Assessment checkpoint is used.
The original file is NOT modified; a new file is saved alongside it.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CHECKPOINT_DIR = Path("data/checkpoints")
DEFAULT_GLOB = "Full_Assessment_Enhanced_Prudential_Standards_*"


def find_latest_checkpoint(pattern: str = DEFAULT_GLOB) -> Path:
    candidates = sorted(CHECKPOINT_DIR.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No checkpoint matching {pattern!r} in {CHECKPOINT_DIR}")
    return candidates[-1]


def deduplicate_risks(
    risks: list[dict],
    id_prefix: str = "RISK",
) -> tuple[list[dict], dict[str, str]]:
    """Return (deduped_risks, old_id_to_new_id_map)."""
    best: dict[tuple[str, str], tuple[int, dict]] = {}
    for idx, r in enumerate(risks):
        key = (r.get("source_citation", ""), r.get("risk_category", ""))
        impact = int(r.get("impact_rating", 0))
        freq = int(r.get("frequency_rating", 0))
        score = impact * freq

        prev = best.get(key)
        if prev is None:
            best[key] = (idx, r)
        else:
            p_impact = int(prev[1].get("impact_rating", 0))
            p_freq = int(prev[1].get("frequency_rating", 0))
            p_score = p_impact * p_freq
            if (score, impact) > (p_score, p_impact):
                best[key] = (prev[0], r)  # keep first-seen position

    winners = sorted(best.values(), key=lambda t: t[0])

    old_to_new: dict[str, str] = {}
    deduped: list[dict] = []
    for new_idx, (_, r) in enumerate(winners, start=1):
        new_id = f"{id_prefix}-{new_idx:03d}"
        old_to_new[r["risk_id"]] = new_id
        updated = dict(r)
        updated["risk_id"] = new_id
        deduped.append(updated)

    return deduped, old_to_new


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else find_latest_checkpoint()
    print(f"Loading  {src.name}")
    data = json.loads(src.read_text())

    # --- Locate scored_risks ------------------------------------------------
    raw_risks = data.get("scored_risks", [])
    prefix = data.get("pipeline_config", {}).get("risk_id_prefix", "RISK")

    print(f"  Raw risks: {len(raw_risks)}")
    deduped, id_map = deduplicate_risks(raw_risks, id_prefix=prefix)
    removed = len(raw_risks) - len(deduped)
    print(f"  Deduplicated risks: {len(deduped)} ({removed} duplicates removed)")

    # Replace top-level scored_risks
    data["scored_risks"] = deduped

    # --- Update risk_register -----------------------------------------------
    rr = data.get("risk_register", {})
    if rr:
        rr["scored_risks"] = deduped
        rr["total_risks"] = len(deduped)

        # Recalculate distribution and severity counts
        dist: dict[str, int] = defaultdict(int)
        critical = high = 0
        for r in deduped:
            dist[r.get("risk_category", "Unknown")] += 1
            rating = r.get("inherent_risk_rating", "")
            if rating == "Critical":
                critical += 1
            elif rating == "High":
                high += 1
        rr["risk_distribution"] = dict(dist)
        rr["critical_count"] = critical
        rr["high_count"] = high
        data["risk_register"] = rr

    # --- Update compliance_matrix -------------------------------------------
    cm = data.get("compliance_matrix", {})
    rows = cm.get("rows", [])
    for row in rows:
        old_ids = row.get("risk_ids", [])
        # Map old IDs to new, dropping any that were removed as duplicates
        row["risk_ids"] = sorted(
            {id_map[oid] for oid in old_ids if oid in id_map}
        )
    if rows:
        cm["rows"] = rows
        data["compliance_matrix"] = cm

    # --- Update metadata ----------------------------------------------------
    meta = data.get("_meta", {})
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%Hh%M_%S")
    meta["dedup_applied"] = True
    meta["dedup_timestamp"] = ts
    meta["pre_dedup_risk_count"] = len(raw_risks)
    meta["post_dedup_risk_count"] = len(deduped)
    data["_meta"] = meta

    # --- Save ---------------------------------------------------------------
    stem = src.stem
    out_name = f"{stem}_deduped_{ts}.json"
    out_path = CHECKPOINT_DIR / out_name
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nSaved    {out_path}")

    # --- Quick sanity check -------------------------------------------------
    seen: set[tuple[str, str]] = set()
    for r in deduped:
        key = (r["source_citation"], r["risk_category"])
        assert key not in seen, f"Duplicate still present: {key}"
        seen.add(key)

    # Verify matrix risk_ids reference valid IDs
    valid_ids = {r["risk_id"] for r in deduped}
    for row in rows:
        for rid in row.get("risk_ids", []):
            assert rid in valid_ids, f"Matrix references unknown ID {rid}"

    print("Sanity checks passed ✓")


if __name__ == "__main__":
    main()
