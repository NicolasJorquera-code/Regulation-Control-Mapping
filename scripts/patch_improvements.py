#!/usr/bin/env python3
"""
Patch a Full Assessment checkpoint with proposed control improvements.

Reads an assessed checkpoint, identifies coverage gaps, and uses the
ControlImprovementAgent to propose new or enhanced controls for each gap.

Usage:
    python scripts/patch_improvements.py \
        --checkpoint "data/checkpoints/Full_Assessment_....json"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Ensure project root is on sys.path so regrisk imports work
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from regrisk.agents.base import AgentContext
from regrisk.agents.control_improver import ControlImprovementAgent
from regrisk.core.transport import build_client_from_env


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch a Full Assessment checkpoint with proposed control improvements."
    )
    parser.add_argument(
        "--checkpoint", required=True,
        help="Path to existing Full Assessment checkpoint JSON.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for the improved checkpoint (default: auto-generated in same dir).",
    )
    args = parser.parse_args()

    # ── 1. Load & validate checkpoint ─────────────────────────────────────
    print("Loading checkpoint …")
    checkpoint_path = Path(args.checkpoint)
    checkpoint: dict = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    meta = checkpoint.get("_meta", {})
    if meta.get("stage") not in ("assessed", "assess_partial"):
        sys.exit(
            f"ERROR: Checkpoint stage is '{meta.get('stage')}', "
            f"expected 'assessed' or 'assess_partial'."
        )

    # ── 2. Identify gaps ──────────────────────────────────────────────────
    assessments = checkpoint.get("coverage_assessments", [])
    gaps = [
        a for a in assessments
        if a.get("overall_coverage") in ("Not Covered", "Partially Covered")
    ]
    print(f"  Found {len(gaps)} coverage gaps to address.")

    if not gaps:
        print("No gaps found. Nothing to improve.")
        return

    # ── 3. Build lookup tables ────────────────────────────────────────────
    ob_lookup: dict[str, dict] = {}
    for ob in checkpoint.get("classified_obligations", []):
        ob_lookup[ob["citation"]] = ob

    mapping_lookup: dict[tuple[str, str], dict] = {}
    for m in checkpoint.get("obligation_mappings", []):
        mapping_lookup[(m["citation"], m["apqc_hierarchy_id"])] = m

    controls_by_id: dict[str, dict] = {}
    for c in checkpoint.get("controls", []):
        controls_by_id[c["control_id"]] = c

    # ── 4. Initialize LLM client & agent ──────────────────────────────────
    print("\nInitializing LLM client …")
    client = build_client_from_env()
    if client is None:
        sys.exit(
            "ERROR: No LLM client configured. "
            "Set OPENAI_API_KEY or ICA_API_KEY + ICA_BASE_URL."
        )
    print(f"  Using model: {client.model}")

    ctx = AgentContext(client=client, model=client.model, max_tokens=4096)
    agent = ControlImprovementAgent(ctx)
    loop = asyncio.new_event_loop()

    # ── 5. Propose improvements for each gap ──────────────────────────────
    print(f"\nProposing improvements for {len(gaps)} gaps …")
    proposed: list[dict] = []

    for i, gap in enumerate(gaps):
        cit = gap["citation"]
        apqc_id = gap.get("apqc_hierarchy_id", "")
        obligation = ob_lookup.get(cit, {"citation": cit})
        mapping = mapping_lookup.get((cit, apqc_id), {})
        apqc_name = mapping.get("apqc_process_name", "")

        # Look up existing control if one was partially matching
        existing_control: dict | None = None
        ctrl_id = gap.get("control_id")
        if ctrl_id:
            existing_control = controls_by_id.get(ctrl_id)

        result = loop.run_until_complete(
            agent.execute(
                obligation=obligation,
                assessment=gap,
                existing_control=existing_control,
                apqc_hierarchy_id=apqc_id,
                apqc_process_name=apqc_name,
                improvement_counter=len(proposed),
            )
        )

        change_type = result.get("change_type", "?")
        ctrl_id_out = result.get("proposed_control", {}).get("control_id", "?")
        print(f"  [{i + 1}/{len(gaps)}] {cit} @ {apqc_id} → {change_type} ({ctrl_id_out})")
        proposed.append(result)

    loop.close()

    # ── 6. Store results in checkpoint ────────────────────────────────────
    checkpoint["proposed_improvements"] = proposed

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d_%Hh%M_%S")

    checkpoint["_meta"]["improvements_count"] = len(proposed)
    checkpoint["_meta"]["improvement_timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    if "keys_saved" in checkpoint["_meta"]:
        keys = checkpoint["_meta"]["keys_saved"]
        if "proposed_improvements" not in keys:
            keys.append("proposed_improvements")

    # ── 7. Save improved checkpoint ───────────────────────────────────────
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = checkpoint_path.parent / f"Improved_{checkpoint_path.stem}_{ts}.json"

    output_path.write_text(
        json.dumps(checkpoint, default=str, indent=2), encoding="utf-8",
    )

    change_type_counts = dict(Counter(p.get("change_type", "?") for p in proposed))
    print(f"\nImproved checkpoint saved: {output_path}")
    print(f"  Improvements: {len(proposed)} ({change_type_counts})")
    print(f"  Gaps addressed: {len(gaps)}")


if __name__ == "__main__":
    main()
