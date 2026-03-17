"""Shared constants and utility functions for ControlNexus.

Extracted from the orchestrator monolith: TYPE_CODE_MAP, frequency rules,
control ID generation, and frequency derivation.
"""

from __future__ import annotations

import re
from typing import Any

MAX_CONTROL_TARGET = 10000

TYPE_CODE_MAP: dict[str, str] = {
    "Reconciliation": "REC",
    "Authorization": "AUT",
    "Verification and Validation": "VNV",
    "Exception Reporting": "EXR",
    "Segregation of Duties": "SOD",
    "Documentation, Data, and Activity Completeness and Appropriateness Checks": "DOC",
    "Internal and External Audits": "AUD",
    "Automated Rules": "ARL",
    "Training and Awareness Programs": "TRN",
    "Risk Escalation Processes": "REP",
    "System and Application Restrictions": "SAR",
    "Data Security and Protection": "DSP",
    "Third Party Due Diligence": "THR",
}

FREQUENCY_ORDERED_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Daily", ("daily", "every day", "each day", "per day", "day-end", "day end", "end of day", "eod")),
    ("Weekly", ("weekly", "every week", "each week", "per week", "biweekly", "bi-weekly", "fortnight")),
    (
        "Monthly",
        (
            "monthly", "every month", "each month", "per month",
            "month-end", "month end", "eom", "semi-monthly", "semimonthly",
        ),
    ),
    ("Quarterly", ("quarterly", "every quarter", "each quarter", "per quarter", "qtr", "quarter-end", "quarter end")),
    ("Semi-Annual", ("semi-annual", "semi annual", "semiannual", "bi-annual", "biannual", "twice a year")),
    ("Annual", ("annual", "annually", "yearly", "once a year", "each year", "per year")),
]


def derive_frequency_from_when(when_text: Any) -> str:
    """Derive a frequency label from a free-text 'when' field.

    Uses ordered keyword matching (Daily checked before Monthly, etc.).
    Returns 'Other' if no keyword matches.
    """
    if not when_text:
        return "Other"

    normalized = re.sub(r"\s+", " ", str(when_text).strip().lower())
    if not normalized:
        return "Other"

    for frequency, keywords in FREQUENCY_ORDERED_RULES:
        if any(keyword in normalized for keyword in keywords):
            return frequency

    return "Other"


def type_to_code(control_type: str) -> str:
    """Convert a control type name to its 3-letter code.

    Uses TYPE_CODE_MAP for known types; falls back to stripping vowels
    and taking the first 3 consonants.
    """
    if control_type in TYPE_CODE_MAP:
        return TYPE_CODE_MAP[control_type]

    consonants = re.sub(r"[aeiouAEIOU\s\-]", "", control_type)
    return consonants[:3].upper() or "UNK"


def build_control_id(hierarchy_id: str, type_code: str, sequence: int) -> str:
    """Build a control ID in the format CTRL-{L1:02d}{L2:02d}-{TYPE}-{SEQ:03d}.

    Args:
        hierarchy_id: Dot-separated hierarchy path like "4.1.1.1".
        type_code: 3-letter type code (e.g., "REC").
        sequence: Sequence number within the type.
    """
    parts = hierarchy_id.split(".")
    l1 = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    l2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return f"CTRL-{l1:02d}{l2:02d}-{type_code}-{sequence:03d}"
