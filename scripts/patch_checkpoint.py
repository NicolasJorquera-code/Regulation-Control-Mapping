#!/usr/bin/env python3
"""
Patch a Full Assessment checkpoint with new controls and re-assess affected items.

Usage:
    python scripts/patch_checkpoint.py \
        --checkpoint "data/checkpoints/Full_Assessment_....json" \
        --controls "data/Control Dataset/section_11_controls.json"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path so regrisk imports work
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from regrisk.agents.base import AgentContext
from regrisk.agents.coverage_assessor import CoverageAssessorAgent
from regrisk.agents.risk_extractor_scorer import RiskExtractorAndScorerAgent
from regrisk.core.models import ControlRecord
from regrisk.core.scoring import deduplicate_risks
from regrisk.core.transport import build_client_from_env
from regrisk.ingest.control_loader import build_control_index, find_controls_for_apqc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "control_id", "hierarchy_id", "leaf_name", "full_description",
    "selected_level_1", "selected_level_2", "who", "what", "when",
    "frequency", "where", "why", "evidence", "quality_rating",
    "business_unit_name",
]


def _validate_controls(controls_raw: list[dict]) -> list[ControlRecord]:
    """Validate and return ControlRecord instances."""
    records: list[ControlRecord] = []
    for c in controls_raw:
        missing = [f for f in REQUIRED_FIELDS if f not in c]
        if missing:
            raise ValueError(
                f"Control {c.get('control_id', '?')} missing fields: {missing}"
            )
        records.append(ControlRecord(**c))
    return records


def _build_finalization_outputs(
    approved: list[dict],
    mappings: list[dict],
    assessments: list[dict],
    risks: list[dict],
    regulation_name: str,
) -> tuple[dict, dict, dict]:
    """Rebuild gap_report, compliance_matrix, risk_register (mirrors finalize_node)."""

    # Coverage summary
    coverage_summary: dict[str, int] = defaultdict(int)
    for a in assessments:
        coverage_summary[a.get("overall_coverage", "Not Covered")] += 1

    # Gaps
    gaps = [
        a for a in assessments
        if a.get("overall_coverage") in ("Not Covered", "Partially Covered")
    ]

    # Classified counts
    classified_counts: dict[str, int] = defaultdict(int)
    for ob in approved:
        classified_counts[ob.get("obligation_category", "Not Assigned")] += 1

    gap_report = {
        "regulation_name": regulation_name,
        "total_obligations": len(approved),
        "classified_counts": dict(classified_counts),
        "mapped_obligation_count": len({m.get("citation") for m in mappings}),
        "coverage_summary": dict(coverage_summary),
        "gaps": gaps,
    }

    # Compliance matrix
    mapping_lookup: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mapping_lookup[m.get("citation", "")].append(m)
    assessment_lookup: dict[tuple[str, str], dict] = {}
    for a in assessments:
        assessment_lookup[(a.get("citation", ""), a.get("apqc_hierarchy_id", ""))] = a
    risk_lookup: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risk_lookup[r.get("source_citation", "")].append(r)

    matrix_rows: list[dict] = []
    for ob in approved:
        cit = ob.get("citation", "")
        for m in mapping_lookup.get(cit, [{}]):
            apqc_id = m.get("apqc_hierarchy_id", "")
            a = assessment_lookup.get((cit, apqc_id), {})
            matrix_rows.append({
                "citation": cit,
                "obligation_category": ob.get("obligation_category", ""),
                "criticality_tier": ob.get("criticality_tier", ""),
                "apqc_hierarchy_id": apqc_id,
                "apqc_process_name": m.get("apqc_process_name", ""),
                "control_id": a.get("control_id", ""),
                "overall_coverage": a.get("overall_coverage", ""),
                "risk_ids": [r.get("risk_id", "") for r in risk_lookup.get(cit, [])],
            })
    compliance_matrix = {"rows": matrix_rows}

    # Risk register
    risk_dist: dict[str, int] = defaultdict(int)
    critical_count = high_count = 0
    for r in risks:
        risk_dist[r.get("risk_category", "Unknown")] += 1
        rating = r.get("inherent_risk_rating", "")
        if rating == "Critical":
            critical_count += 1
        elif rating == "High":
            high_count += 1

    risk_register = {
        "scored_risks": risks,
        "total_risks": len(risks),
        "risk_distribution": dict(risk_dist),
        "critical_count": critical_count,
        "high_count": high_count,
    }

    return gap_report, compliance_matrix, risk_register


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch a Full Assessment checkpoint with new controls and re-assess."
    )
    parser.add_argument(
        "--checkpoint", required=True,
        help="Path to existing Full Assessment checkpoint JSON.",
    )
    parser.add_argument(
        "--controls", required=True,
        help="Path to JSON file containing an array of new ControlRecord dicts.",
    )
    args = parser.parse_args()

    # ── 1. Load & validate inputs ─────────────────────────────────────────
    print("Loading checkpoint …")
    checkpoint_path = Path(args.checkpoint)
    checkpoint: dict = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    meta = checkpoint.get("_meta", {})
    if meta.get("stage") != "assessed":
        sys.exit(f"ERROR: Checkpoint stage is '{meta.get('stage')}', expected 'assessed'.")

    print("Loading new controls …")
    new_controls_raw: list[dict] = json.loads(
        Path(args.controls).read_text(encoding="utf-8")
    )
    new_control_records = _validate_controls(new_controls_raw)
    print(f"  Validated {len(new_control_records)} new controls.")

    # ── 2. Merge controls ─────────────────────────────────────────────────
    existing_controls: list[dict] = checkpoint.get("controls", [])
    existing_ids = {c["control_id"] for c in existing_controls}
    added = 0
    for c in new_controls_raw:
        if c["control_id"] not in existing_ids:
            existing_controls.append(c)
            existing_ids.add(c["control_id"])
            added += 1
    checkpoint["controls"] = existing_controls
    print(f"  Merged {added} new controls (total: {len(existing_controls)}).")

    # ── 3. Build control index ────────────────────────────────────────────
    all_control_records = [ControlRecord(**c) for c in existing_controls]
    control_index = build_control_index(all_control_records)

    # ── 4. Identify affected assessments ──────────────────────────────────
    new_prefixes: set[str] = set()
    for c in new_controls_raw:
        new_prefixes.add(c["hierarchy_id"].split(".")[0])

    old_assessments = checkpoint.get("coverage_assessments", [])
    affected: list[dict] = []
    preserved: list[dict] = []
    for a in old_assessments:
        apqc_top = a.get("apqc_hierarchy_id", "").split(".")[0]
        if apqc_top in new_prefixes:
            affected.append(a)
        else:
            preserved.append(a)

    print(f"  Affected assessments: {len(affected)}, Preserved: {len(preserved)}")

    # Filter risks: remove risks whose source_apqc_id falls under affected prefixes
    old_risks = checkpoint.get("scored_risks", [])
    preserved_risks = [
        r for r in old_risks
        if r.get("source_apqc_id", "").split(".")[0] not in new_prefixes
    ]
    print(f"  Preserved risks: {len(preserved_risks)} (removed {len(old_risks) - len(preserved_risks)})")

    if not affected:
        print("No assessments affected by the new controls. Nothing to do.")
        return

    # ── 5. Initialize LLM client & agents ─────────────────────────────────
    print("\nInitializing LLM client …")
    client = build_client_from_env()
    if client is None:
        sys.exit(
            "ERROR: No LLM client configured. "
            "Set OPENAI_API_KEY or ICA_API_KEY + ICA_BASE_URL."
        )
    print(f"  Using model: {client.model}")

    assess_ctx = AgentContext(client=client, model=client.model, max_tokens=2048)
    risk_ctx = AgentContext(client=client, model=client.model, max_tokens=4096)
    assessor = CoverageAssessorAgent(assess_ctx)
    risk_scorer = RiskExtractorAndScorerAgent(risk_ctx)

    loop = asyncio.new_event_loop()

    # Build lookup tables
    ob_lookup: dict[str, dict] = {}
    for ob in checkpoint.get("classified_obligations", []):
        ob_lookup[ob["citation"]] = ob

    mapping_lookup: dict[tuple[str, str], dict] = {}
    for m in checkpoint.get("obligation_mappings", []):
        mapping_lookup[(m["citation"], m["apqc_hierarchy_id"])] = m

    # ── 6. Re-run coverage assessment for affected items ──────────────────
    print(f"\nRe-assessing {len(affected)} coverage items …")
    new_assessments: list[dict] = []

    for i, old_a in enumerate(affected):
        cit = old_a["citation"]
        apqc_id = old_a["apqc_hierarchy_id"]
        mapping = mapping_lookup.get((cit, apqc_id), {})
        obligation = ob_lookup.get(cit, {"citation": cit})
        apqc_name = mapping.get("apqc_process_name", "")

        # Find candidate controls (now including new controls)
        candidates = find_controls_for_apqc(control_index, apqc_id)

        if not candidates:
            # No controls → deterministic Not Covered
            result = loop.run_until_complete(assessor.execute(
                obligation=obligation,
                control=None,
                apqc_hierarchy_id=apqc_id,
                apqc_process_name=apqc_name,
            ))
        else:
            # Evaluate each candidate, keep best
            best: dict | None = None
            for ctrl in candidates:
                result = loop.run_until_complete(assessor.execute(
                    obligation=obligation,
                    control=ctrl.model_dump(),
                    apqc_hierarchy_id=apqc_id,
                    apqc_process_name=apqc_name,
                ))
                if best is None:
                    best = result
                elif result.get("overall_coverage") == "Covered":
                    best = result
                    break
                elif (
                    result.get("overall_coverage") == "Partially Covered"
                    and best.get("overall_coverage") == "Not Covered"
                ):
                    best = result
            result = best

        new_assessments.append(result)
        status = result.get("overall_coverage", "?")
        print(f"  [{i + 1}/{len(affected)}] {cit} @ {apqc_id} → {status}")

    # ── 7. Re-run risk scoring for remaining gaps ─────────────────────────
    new_gaps = [
        a for a in new_assessments
        if a.get("overall_coverage") in ("Not Covered", "Partially Covered")
    ]
    print(f"\nScoring risks for {len(new_gaps)} remaining gaps …")

    risk_counter = len(preserved_risks)
    new_risks: list[dict] = []

    for i, gap in enumerate(new_gaps):
        cit = gap["citation"]
        obligation = ob_lookup.get(cit, {"citation": cit})
        mapping = mapping_lookup.get((cit, gap["apqc_hierarchy_id"]), {})

        result = loop.run_until_complete(risk_scorer.execute(
            obligation=obligation,
            coverage_status=gap.get("overall_coverage", "Not Covered"),
            gap_rationale=gap.get("semantic_rationale", ""),
            apqc_hierarchy_id=gap.get("apqc_hierarchy_id", ""),
            apqc_process_name=mapping.get("apqc_process_name", ""),
            risk_taxonomy=checkpoint.get("risk_taxonomy", {}),
            config=checkpoint.get("pipeline_config", {}),
            risk_counter=risk_counter,
        ))

        scored = result.get("risks", [])
        new_risks.extend(scored)
        risk_counter += len(scored)
        print(f"  [{i + 1}/{len(new_gaps)}] {cit} → {len(scored)} risks")

    loop.close()

    # ── 8. Merge & deduplicate ────────────────────────────────────────────
    all_assessments = preserved + new_assessments
    all_risks_raw = preserved_risks + new_risks
    risk_id_prefix = checkpoint.get("pipeline_config", {}).get("risk_id_prefix", "RISK")
    all_risks = deduplicate_risks(all_risks_raw, id_prefix=risk_id_prefix)
    print(f"\n  Total risks after dedup: {len(all_risks)} (from {len(all_risks_raw)} raw)")

    # ── 9. Rebuild reports ────────────────────────────────────────────────
    approved = checkpoint.get("classified_obligations", [])
    mappings = checkpoint.get("obligation_mappings", [])
    regulation_name = checkpoint.get("regulation_name", "")

    gap_report, compliance_matrix, risk_register = _build_finalization_outputs(
        approved, mappings, all_assessments, all_risks, regulation_name,
    )

    # ── 10. Save patched checkpoint ───────────────────────────────────────
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d_%Hh%M_%S")

    checkpoint["coverage_assessments"] = all_assessments
    checkpoint["scored_risks"] = all_risks
    checkpoint["gap_report"] = gap_report
    checkpoint["compliance_matrix"] = compliance_matrix
    checkpoint["risk_register"] = risk_register

    checkpoint["_meta"]["patched"] = True
    checkpoint["_meta"]["patch_timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    checkpoint["_meta"]["assessment_count"] = len(all_assessments)
    checkpoint["_meta"]["original_file"] = checkpoint_path.name

    output_path = checkpoint_path.parent / f"Patched_Full_Assessment_{ts}.json"
    output_path.write_text(
        json.dumps(checkpoint, default=str, indent=2), encoding="utf-8"
    )

    coverage_summary = dict(
        Counter(a.get("overall_coverage", "Not Covered") for a in all_assessments)
    )
    print(f"\nPatched checkpoint saved: {output_path}")
    print(f"  Assessments: {len(all_assessments)} ({len(new_assessments)} re-assessed)")
    print(f"  Risks: {len(all_risks)} ({len(new_risks)} new, {len(all_risks)} after dedup)")
    print(f"  Coverage: {coverage_summary}")


if __name__ == "__main__":
    main()
