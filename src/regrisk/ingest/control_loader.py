"""
Control inventory loader — auto-discovers and merges section control files.

Deterministic (no LLM). Pure Python + pandas + glob.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import pandas as pd

from regrisk.core.models import ControlRecord
from regrisk.exceptions import IngestError


def _clean_str(val: object) -> str:
    """Convert a cell value to a clean string, handling NaN."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def discover_control_files(directory: str, pattern: str = "section_*__controls.xlsx") -> list[str]:
    """Glob for control files matching the pattern. Return sorted file paths."""
    search_path = str(Path(directory) / pattern)
    files = sorted(glob.glob(search_path))
    return files


def load_and_merge_controls(file_paths: list[str]) -> list[ControlRecord]:
    """Load each control file, detect its sheet name, merge into unified list.

    Deduplicates by control_id.
    """
    all_controls: list[ControlRecord] = []
    seen_ids: set[str] = set()

    for fpath in file_paths:
        # Detect sheet name: section_{N}_controls (single underscore)
        fname = Path(fpath).stem  # e.g. 'section_1__controls'
        m = re.search(r"section_(\d+)", fname)
        if not m:
            continue
        section_num = m.group(1)
        sheet_name = f"section_{section_num}_controls"

        try:
            df = pd.read_excel(fpath, sheet_name=sheet_name, engine="openpyxl")
        except Exception:
            # Try reading the first sheet as fallback
            try:
                df = pd.read_excel(fpath, sheet_name=0, engine="openpyxl")
            except Exception as exc:
                raise IngestError(f"Failed to read control file {fpath}: {exc}") from exc

        for _, row in df.iterrows():
            control_id = _clean_str(row.get("control_id"))
            if not control_id or control_id in seen_ids:
                continue
            seen_ids.add(control_id)

            record = ControlRecord(
                control_id=control_id,
                hierarchy_id=_clean_str(row.get("hierarchy_id")),
                leaf_name=_clean_str(row.get("leaf_name")),
                full_description=_clean_str(row.get("full_description")),
                selected_level_1=_clean_str(row.get("selected_level_1")),
                selected_level_2=_clean_str(row.get("selected_level_2")),
                who=_clean_str(row.get("who")),
                what=_clean_str(row.get("what")),
                when=_clean_str(row.get("when")),
                frequency=_clean_str(row.get("frequency")),
                where=_clean_str(row.get("where")),
                why=_clean_str(row.get("why")),
                evidence=_clean_str(row.get("evidence")),
                quality_rating=_clean_str(row.get("quality_rating")),
                business_unit_name=_clean_str(row.get("business_unit_name")),
            )
            all_controls.append(record)

    return all_controls


def build_control_index(controls: list[ControlRecord]) -> dict[str, list[ControlRecord]]:
    """Index controls by APQC hierarchy_id for fast structural matching.

    Each control is indexed under its own hierarchy_id AND all ancestor
    prefixes. For lookup, given an APQC process hierarchy_id, this returns
    all controls at that node or any descendant.
    """
    index: dict[str, list[ControlRecord]] = {}
    for ctrl in controls:
        hid = ctrl.hierarchy_id
        index.setdefault(hid, []).append(ctrl)
    return index


def find_controls_for_apqc(
    control_index: dict[str, list[ControlRecord]],
    apqc_hierarchy_id: str,
) -> list[ControlRecord]:
    """Find controls that structurally match an APQC process.

    Returns controls whose hierarchy_id starts with the given apqc_hierarchy_id
    (i.e., the control is at the same node or a descendant).
    """
    prefix = apqc_hierarchy_id
    results: list[ControlRecord] = []
    for hid, ctrls in control_index.items():
        if hid == prefix or hid.startswith(prefix + "."):
            results.extend(ctrls)
    return results
