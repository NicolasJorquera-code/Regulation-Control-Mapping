"""Gap-to-assignment planner.

Converts a GapReport into an ordered list of ControlAssignment dicts
that the remediation graph processes one at a time.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def plan_assignments(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert gap report into ordered remediation assignments.

    Priority order: regulatory gaps first (highest weight), then balance,
    frequency, evidence.
    """
    assignments: list[dict[str, Any]] = []

    # Regulatory gaps → new controls
    for gap in gap_report.get("regulatory_gaps", []):
        assignments.append(
            {
                "gap_source": "regulatory",
                "framework": gap.get("framework", ""),
                "required_theme": gap.get("required_theme", ""),
                "severity": gap.get("severity", "medium"),
                "current_coverage": gap.get("current_coverage", 0),
            }
        )

    # Balance gaps → new controls for under-represented types
    for gap in gap_report.get("balance_gaps", []):
        if gap.get("direction") == "under":
            assignments.append(
                {
                    "gap_source": "balance",
                    "control_type": gap.get("control_type", ""),
                    "expected_pct": gap.get("expected_pct", 0),
                    "actual_pct": gap.get("actual_pct", 0),
                }
            )

    # Frequency issues → fix existing controls
    for issue in gap_report.get("frequency_issues", []):
        assignments.append(
            {
                "gap_source": "frequency",
                "control_id": issue.get("control_id", ""),
                "hierarchy_id": issue.get("hierarchy_id", ""),
                "expected_frequency": issue.get("expected_frequency", ""),
                "actual_frequency": issue.get("actual_frequency", ""),
            }
        )

    # Evidence issues → fix existing controls
    for issue in gap_report.get("evidence_issues", []):
        assignments.append(
            {
                "gap_source": "evidence",
                "control_id": issue.get("control_id", ""),
                "hierarchy_id": issue.get("hierarchy_id", ""),
                "issue": issue.get("issue", ""),
            }
        )

    logger.info(
        "Planned %d assignments: %d regulatory, %d balance, %d frequency, %d evidence",
        len(assignments),
        sum(1 for a in assignments if a["gap_source"] == "regulatory"),
        sum(1 for a in assignments if a["gap_source"] == "balance"),
        sum(1 for a in assignments if a["gap_source"] == "frequency"),
        sum(1 for a in assignments if a["gap_source"] == "evidence"),
    )
    return assignments
