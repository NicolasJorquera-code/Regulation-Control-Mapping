"""
Regulation Excel parser — Promontory-format regulatory obligation inventory.

Deterministic (no LLM). Pure Python + pandas.
"""

from __future__ import annotations

import re

import pandas as pd

from regrisk.core.models import Obligation, ObligationGroup
from regrisk.exceptions import IngestError


# Columns we extract from the regulation Excel
_COLUMN_MAP: dict[str, str] = {
    "Citation": "citation",
    "Mandate Title": "mandate_title",
    "Abstract": "abstract",
    "Text": "text",
    "Link": "link",
    "Status": "status",
    "Title Level 2": "title_level_2",
    "Title Level 3": "title_level_3",
    "Title Level 4": "title_level_4",
    "Title Level 5": "title_level_5",
    "Citation Level 2": "citation_level_2",
    "Citation Level 3": "citation_level_3",
    "Effective Date": "effective_date",
    "Applicability": "applicability",
    "Mandate Citation": "mandate_citation",
}


def _clean_str(val: object) -> str:
    """Convert a cell value to a clean string, handling NaN and 'nan'."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def parse_regulation_excel(path: str) -> tuple[str, list[Obligation]]:
    """Parse Promontory-format regulation Excel.

    Reads the 'Requirements' sheet, extracts 15 key columns.
    Returns (regulation_name, list_of_obligations).
    """
    try:
        df = pd.read_excel(path, sheet_name="Requirements", engine="openpyxl")
    except Exception as exc:
        raise IngestError(f"Failed to read regulation Excel at {path}: {exc}") from exc

    # Verify expected columns exist
    missing = [c for c in _COLUMN_MAP if c not in df.columns]
    if missing:
        raise IngestError(f"Missing columns in regulation Excel: {missing}")

    obligations: list[Obligation] = []
    regulation_name = ""

    for _, row in df.iterrows():
        data: dict[str, str] = {}
        for excel_col, model_field in _COLUMN_MAP.items():
            data[model_field] = _clean_str(row.get(excel_col))

        # Use Text as fallback if Abstract is empty
        if not data["abstract"] and data.get("text"):
            data["abstract"] = data["text"]

        # Capture regulation name from first non-empty mandate_title
        if not regulation_name and data.get("mandate_title"):
            regulation_name = data["mandate_title"]

        # Remove mandate_citation (not in the Obligation model)
        data.pop("mandate_citation", None)

        obligations.append(Obligation(**data))

    return regulation_name, obligations


def group_obligations(obligations: list[Obligation]) -> list[ObligationGroup]:
    """Group obligations by (Citation Level 2, Citation Level 3).

    Returns ~89 groups. Each group gets a group_id like 'Subpart_D__252.34'.
    """
    groups_dict: dict[tuple[str, str], list[Obligation]] = {}
    for ob in obligations:
        key = (ob.citation_level_2, ob.citation_level_3)
        groups_dict.setdefault(key, []).append(ob)

    groups: list[ObligationGroup] = []
    for (subpart, section_cit), obs in sorted(groups_dict.items()):
        # Build group_id: strip spaces, extract section number
        subpart_clean = subpart.replace(" ", "_") if subpart else "Unknown"
        section_num = ""
        m = re.search(r"(\d[\d.]*\d?)$", section_cit)
        if m:
            section_num = m.group(1)
        group_id = f"{subpart_clean}__{section_num}" if section_num else subpart_clean

        # Use the first obligation's titles for the group metadata
        first = obs[0]
        groups.append(ObligationGroup(
            group_id=group_id,
            subpart=subpart,
            section_citation=section_cit,
            section_title=first.title_level_3,
            topic_title=first.title_level_2,
            obligation_count=len(obs),
            obligations=obs,
        ))

    return groups
