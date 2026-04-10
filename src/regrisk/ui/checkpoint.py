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
    ts_filename = now.strftime("%Y-%m-%d_%Hh%M")
    ts_display = now.strftime("%Y-%m-%d %H:%M UTC")
    reg_name = session_data.get("regulation_name", "unknown")
    safe_name = _sanitise_name(reg_name)
    stage_lbl = _STAGE_LABELS.get(stage, stage).replace(" ", "_")
    filename = f"{stage_lbl}_{safe_name}_{ts_filename}.json"
    path = target_dir / filename

    keys = _STAGE_KEYS.get(stage, list(session_data.keys()))
    payload: dict[str, Any] = {
        "_meta": {
            "stage": stage,
            "stage_label": _STAGE_LABELS.get(stage, stage),
            "regulation_name": reg_name,
            "timestamp": ts_display,
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
    for p in sorted(target_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            ts_raw = meta.get("timestamp", "?")
            results.append({
                "path": p,
                "filename": p.name,
                "stage": meta.get("stage", "?"),
                "stage_label": meta.get("stage_label", "?"),
                "regulation_name": meta.get("regulation_name", "?"),
                "timestamp": ts_raw,
                "display": (
                    f"{meta.get('stage_label', '?')} · "
                    f"{meta.get('regulation_name', '?')} · "
                    f"{ts_raw}"
                ),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return results
