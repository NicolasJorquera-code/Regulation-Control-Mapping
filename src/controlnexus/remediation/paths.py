"""Gap-type-specific remediation path logic.

Each path function takes the current state and produces the inputs
for the agent pipeline (spec_agent → narrative_agent).
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def prepare_regulatory_path(assignment: dict[str, Any], section_profiles: dict[str, Any]) -> dict[str, Any]:
    """Prepare context for a regulatory gap assignment.

    Loads regulatory framework info and builds spec inputs.
    """
    framework = assignment.get("framework", "")
    return {
        "path": "regulatory",
        "framework": framework,
        "required_theme": assignment.get("required_theme", ""),
        "context": f"Generate a control addressing the regulatory requirement: {framework}",
    }


def prepare_balance_path(assignment: dict[str, Any]) -> dict[str, Any]:
    """Prepare context for a balance gap assignment.

    Selects the under-represented control type.
    """
    control_type = assignment.get("control_type", "")
    return {
        "path": "balance",
        "control_type": control_type,
        "context": f"Generate a {control_type} control to improve ecosystem balance",
    }


def prepare_frequency_fix(assignment: dict[str, Any]) -> dict[str, Any]:
    """Deterministic frequency fix — no LLM needed.

    Updates the control's frequency to the expected value.
    """
    return {
        "path": "frequency",
        "control_id": assignment.get("control_id", ""),
        "fix": {
            "frequency": assignment.get("expected_frequency", ""),
            "when": f"{assignment.get('expected_frequency', 'Monthly')}, per updated policy",
        },
    }


def prepare_evidence_fix(assignment: dict[str, Any]) -> dict[str, Any]:
    """Prepare context for evidence sufficiency fix.

    Routes to enricher-only path (no full spec/narrative cycle).
    """
    return {
        "path": "evidence",
        "control_id": assignment.get("control_id", ""),
        "issue": assignment.get("issue", ""),
        "context": "Enhance the evidence field to include specific artifact, signer, and retention system.",
    }


def route_assignment(assignment: dict[str, Any], section_profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route an assignment to the appropriate path handler."""
    gap_source = assignment.get("gap_source", "")

    if gap_source == "regulatory":
        return prepare_regulatory_path(assignment, section_profiles or {})
    elif gap_source == "balance":
        return prepare_balance_path(assignment)
    elif gap_source == "frequency":
        return prepare_frequency_fix(assignment)
    elif gap_source == "evidence":
        return prepare_evidence_fix(assignment)
    else:
        logger.warning("Unknown gap source: %s", gap_source)
        return {"path": "unknown", "context": "Unknown gap source"}
