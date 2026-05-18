"""
Checkpoint persistence for the regulatory obligation mapping pipeline.

Saves and loads pipeline state as JSON files so runs can be resumed after
failures without re-executing expensive LLM calls.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Stage constants
STAGE_CLASSIFIED = "classified"
STAGE_MAPPED = "mapped"
STAGE_ASSESSED = "assessed"
STAGE_ASSESS_PARTIAL = "assess_partial"

# Default checkpoint directory (project-root/data/checkpoints)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHECKPOINT_DIR = _PROJECT_ROOT / "data" / "checkpoints"

# Session keys to save at each stage
_STAGE_KEYS: dict[str, list[str]] = {
    STAGE_CLASSIFIED: [
        "classified_obligations",
        "obligation_groups",
        "apqc_nodes",
        "controls",
        "regulation_name",
        "pipeline_config",
        "risk_taxonomy",
        "llm_enabled",
    ],
    STAGE_MAPPED: [
        "classified_obligations",
        "obligation_groups",
        "apqc_nodes",
        "controls",
        "regulation_name",
        "pipeline_config",
        "risk_taxonomy",
        "llm_enabled",
        "obligation_mappings",
    ],
    STAGE_ASSESSED: [
        "classified_obligations",
        "obligation_groups",
        "apqc_nodes",
        "controls",
        "regulation_name",
        "pipeline_config",
        "risk_taxonomy",
        "llm_enabled",
        "obligation_mappings",
        "coverage_assessments",
        "scored_risks",
        "gap_report",
        "compliance_matrix",
        "risk_register",
        "proposed_improvements",
    ],
    STAGE_ASSESS_PARTIAL: [
        "classified_obligations",
        "obligation_groups",
        "apqc_nodes",
        "controls",
        "regulation_name",
        "pipeline_config",
        "risk_taxonomy",
        "llm_enabled",
        "obligation_mappings",
        "coverage_assessments",
        "gap_report",
        "scored_risks",
        "compliance_matrix",
        "risk_register",
        "proposed_improvements",
    ],
}

_STAGE_LABELS: dict[str, str] = {
    STAGE_CLASSIFIED: "Classification",
    STAGE_MAPPED: "APQC Mapping",
    STAGE_ASSESSED: "Full Assessment",
    STAGE_ASSESS_PARTIAL: "Partial Assessment (interrupted)",
}


def stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage)


def stage_keys(stage: str) -> list[str]:
    return _STAGE_KEYS.get(stage, [])


def _sanitise_name(name: str, max_len: int = 40) -> str:
    """Sanitise a regulation name for use in filenames.

    Truncates on a word boundary so names are never cut mid-word.
    """
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    safe = safe.replace(" ", "_")
    if len(safe) <= max_len:
        return safe
    # Truncate at the last underscore before max_len
    truncated = safe[:max_len]
    last_sep = truncated.rfind("_")
    if last_sep > 10:
        truncated = truncated[:last_sep]
    return truncated


def save_checkpoint(
    stage: str,
    session_data: dict[str, Any],
    directory: Path | None = None,
) -> Path:
    """Save pipeline state for *stage* to a JSON file.

    Returns the path to the written checkpoint file.
    """
    target_dir = directory or CHECKPOINT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    ts_filename = now.strftime("%Y-%m-%d_%Hh%M_%S")
    ts_display = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    reg_name = session_data.get("regulation_name", "unknown")
    safe_name = _sanitise_name(reg_name)
    llm_enabled = session_data.get("llm_enabled", False)
    mode_tag = "llm" if llm_enabled else "det"

    # Count obligations for the filename descriptor
    obligations = session_data.get("classified_obligations", [])
    ob_count = len(obligations)

    stage_lbl = _STAGE_LABELS.get(stage, stage).replace(" ", "_")
    filename = f"{stage_lbl}_{safe_name}_{ob_count}obs_{mode_tag}_{ts_filename}.json"
    path = target_dir / filename

    keys = _STAGE_KEYS.get(stage, list(session_data.keys()))

    # Build summary statistics for metadata
    from collections import Counter
    cat_counts = dict(Counter(
        ob.get("obligation_category", "Not Assigned") for ob in obligations
    )) if obligations else {}
    crit_counts = dict(Counter(
        ob.get("criticality_tier", "Unrated") for ob in obligations
    )) if obligations else {}
    mapping_count = len(session_data.get("obligation_mappings", []))
    assessment_count = len(session_data.get("coverage_assessments", []))

    payload: dict[str, Any] = {
        "_meta": {
            "stage": stage,
            "stage_label": _STAGE_LABELS.get(stage, stage),
            "regulation_name": reg_name,
            "timestamp": ts_display,
            "llm_mode": "LLM-assisted" if llm_enabled else "Deterministic",
            "obligation_count": ob_count,
            "mapping_count": mapping_count,
            "assessment_count": assessment_count,
            "category_breakdown": cat_counts,
            "criticality_breakdown": crit_counts,
            "keys_saved": keys,
        },
    }
    for k in keys:
        if k in session_data:
            payload[k] = session_data[k]

    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    logger.info("Checkpoint saved: %s (%d keys, %.1f KB)", path.name, len(keys), path.stat().st_size / 1024)
    return path


def load_checkpoint(path: Path | str) -> dict[str, Any]:
    """Load a checkpoint file and return the session data dict.

    The returned dict includes a '_meta' key with stage info.
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("_meta", {})
    logger.info(
        "Checkpoint loaded: stage=%s regulation=%s ts=%s",
        meta.get("stage"), meta.get("regulation_name"), meta.get("timestamp"),
    )
    return data


def list_checkpoints(directory: Path | None = None) -> list[dict[str, Any]]:
    """List available checkpoint files, newest first.

    Returns a list of dicts with keys: path, filename, stage, stage_label,
    regulation_name, timestamp.
    """
    target_dir = directory or CHECKPOINT_DIR
    if not target_dir.is_dir():
        return []

    results = []
    for p in sorted(target_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            ts_raw = meta.get("timestamp", "?")
            ob_count = meta.get("obligation_count")
            llm_mode = meta.get("llm_mode", "")
            is_patched = meta.get("patched", False)
            improvements_count = meta.get("improvements_count", 0)

            # Build a human-readable display string
            label = meta.get("stage_label", "?")
            if improvements_count:
                label = f"💡 Improved {label}"
            elif is_patched:
                label = f"\U0001f527 Patched {label}"
            parts = [label]
            parts.append(meta.get("regulation_name", "?"))
            detail_bits: list[str] = []
            if ob_count is not None:
                detail_bits.append(f"{ob_count} obligations")
            if improvements_count:
                detail_bits.append(f"{improvements_count} improvements")
            if llm_mode:
                detail_bits.append(llm_mode)
            if detail_bits:
                parts.append(" · ".join(detail_bits))
            # Use improvement timestamp, then patch timestamp, then original
            imp_ts = meta.get("improvement_timestamp")
            patch_ts = meta.get("patch_timestamp")
            if imp_ts:
                parts.append(imp_ts)
            elif is_patched and patch_ts:
                parts.append(patch_ts)
            else:
                parts.append(ts_raw)

            results.append({
                "path": p,
                "filename": p.name,
                "stage": meta.get("stage", "?"),
                "stage_label": meta.get("stage_label", "?"),
                "regulation_name": meta.get("regulation_name", "?"),
                "timestamp": ts_raw,
                "obligation_count": ob_count,
                "llm_mode": llm_mode,
                "patched": is_patched,
                "display": " · ".join(parts),
            })
        except (json.JSONDecodeError, OSError):
            continue

    # Ensure display names are unique by appending filename stub on collision
    seen: dict[str, int] = {}
    for item in results:
        d = item["display"]
        if d in seen:
            seen[d] += 1
            stem = item["filename"].rsplit(".", 1)[0][-20:]
            item["display"] = f"{d} ({stem})"
        else:
            seen[d] = 1

    return results


# ---------------------------------------------------------------------------
# Checkpoint validation
# ---------------------------------------------------------------------------

# Keys that are optional (may not exist in older checkpoints)
_OPTIONAL_KEYS: frozenset[str] = frozenset({"proposed_improvements"})


def validate_checkpoint(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check that all required keys for the checkpoint's stage are present.

    Returns (is_valid, list_of_missing_keys).  Optional keys (e.g. proposed_improvements)
    are excluded from the validation — their absence does not make a checkpoint invalid.
    """
    meta = data.get("_meta", {})
    stage = meta.get("stage", "")
    expected_keys = _STAGE_KEYS.get(stage, [])
    required_keys = [k for k in expected_keys if k not in _OPTIONAL_KEYS]
    missing = [k for k in required_keys if k not in data]
    return (len(missing) == 0, missing)


def list_valid_checkpoints(
    directory: Path | None = None,
    required_stage: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List checkpoints that have all required fields for their stage.

    Parameters
    ----------
    directory : optional checkpoint directory
    required_stage : if set, also filter to only this stage

    Returns
    -------
    (valid_checkpoints, hidden_count) — the valid list and the number filtered out.
    """
    all_cps = list_checkpoints(directory)
    valid: list[dict[str, Any]] = []
    hidden = 0

    for cp in all_cps:
        if required_stage and cp.get("stage") != required_stage:
            # Stage filter — not counted as "hidden"
            continue
        # Perform validation by loading the file
        try:
            data = json.loads(Path(cp["path"]).read_text(encoding="utf-8"))
            is_valid, _missing = validate_checkpoint(data)
            if is_valid:
                valid.append(cp)
            else:
                hidden += 1
                logger.debug(
                    "Checkpoint %s hidden: missing keys %s", cp["filename"], _missing,
                )
        except (json.JSONDecodeError, OSError):
            hidden += 1

    return valid, hidden
