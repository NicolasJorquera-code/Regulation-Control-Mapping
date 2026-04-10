"""Pure Python tool implementations for agent function calling.

All tools are read-only (no mutation). They look up data from
YAML configs, section profiles, and ChromaDB memory.
"""

from __future__ import annotations

import logging
from typing import Any

from controlnexus.core.constants import derive_frequency_from_when
from controlnexus.core.models import SectionProfile

logger = logging.getLogger(__name__)

# Module-level context — set by the graph before agent execution
_placement_config: dict[str, Any] = {}
_section_profiles: dict[str, SectionProfile] = {}
_memory: Any = None  # ControlMemory instance, optional
_bank_id: str = ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure_tools(
    placement_config: dict[str, Any],
    section_profiles: dict[str, SectionProfile],
    memory: Any = None,
    bank_id: str = "",
) -> None:
    """Set tool context. Call this before running the remediation graph."""
    global _placement_config, _section_profiles, _memory, _bank_id
    _placement_config = placement_config
    _section_profiles = section_profiles
    _memory = memory
    _bank_id = bank_id


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def taxonomy_validator(level_1: str, level_2: str) -> dict[str, Any]:
    """Validate a (level_1, level_2) control type pair.

    Returns {valid: bool, suggestion: {correct_level_1: str} or None}.
    """
    l2_by_l1 = _placement_config.get("control_taxonomy", {}).get("level_2_by_level_1", {})

    # Check if the pair is valid
    allowed_l2 = l2_by_l1.get(level_1, [])
    if level_2 in allowed_l2:
        return {"valid": True, "suggestion": None}

    # Find the correct level_1 for this level_2
    for l1, l2_list in l2_by_l1.items():
        if level_2 in l2_list:
            return {
                "valid": False,
                "suggestion": {"correct_level_1": l1, "reason": f"'{level_2}' belongs under '{l1}', not '{level_1}'"},
            }

    return {"valid": False, "suggestion": {"reason": f"Unknown control type '{level_2}'"}}


def regulatory_lookup(framework: str, section_id: str) -> dict[str, Any]:
    """Look up regulatory requirements for a framework in a section.

    Returns {framework, required_themes, applicable_types}.
    """
    profile = _section_profiles.get(section_id)
    if not profile:
        return {
            "framework": framework,
            "required_themes": [],
            "applicable_types": [],
            "error": f"Unknown section {section_id}",
        }

    # Check if this framework applies to this section
    frameworks = profile.registry.regulatory_frameworks
    matching = [f for f in frameworks if framework.lower() in f.lower() or f.lower() in framework.lower()]

    # Get HIGH and MEDIUM affinity types as applicable
    applicable_types = list(profile.affinity.HIGH) + list(profile.affinity.MEDIUM)

    return {
        "framework": framework,
        "section_id": section_id,
        "required_themes": matching or [framework],
        "applicable_types": applicable_types,
        "domain": profile.domain,
    }


def hierarchy_search(section_id: str, keyword: str) -> dict[str, Any]:
    """Search for APQC leaf nodes matching a keyword.

    Note: Full hierarchy search requires the APQC template Excel.
    This stub returns section-level info from profiles.
    """
    profile = _section_profiles.get(section_id)
    if not profile:
        return {"leaves": [], "error": f"Unknown section {section_id}"}

    # Return domain info as context
    return {
        "section_id": section_id,
        "domain": profile.domain,
        "keyword": keyword,
        "available_roles": profile.registry.roles[:5],
        "available_systems": profile.registry.systems[:5],
        "leaves": [],  # Full leaf search requires APQC template
    }


def frequency_lookup(control_type: str, trigger: str) -> dict[str, Any]:
    """Get expected frequency for a control type given timing context.

    Uses derive_frequency_from_when() and type-frequency expectations.
    """
    from controlnexus.analysis.scanners import (
        MONTHLY_OR_BETTER_TYPES,
        QUARTERLY_OR_BETTER_TYPES,
    )

    derived = derive_frequency_from_when(trigger)

    if control_type in MONTHLY_OR_BETTER_TYPES:
        expected = "Monthly"
        reasoning = f"'{control_type}' controls should operate at monthly or higher frequency for timely detection."
    elif control_type in QUARTERLY_OR_BETTER_TYPES:
        expected = "Quarterly"
        reasoning = f"'{control_type}' controls should operate at quarterly or higher frequency for adequate coverage."
    else:
        expected = "Other"
        reasoning = f"No specific frequency expectation for '{control_type}' — trigger-driven is acceptable."

    return {
        "control_type": control_type,
        "trigger": trigger,
        "derived_frequency": derived,
        "expected_frequency": expected,
        "reasoning": reasoning,
    }


def memory_retrieval(query_text: str, section_id: str = "", n: int = 5) -> dict[str, Any]:
    """Retrieve similar controls from ChromaDB memory.

    Returns {similar_controls: [{document, score, metadata}]}.
    """
    if _memory is None:
        return {"similar_controls": [], "error": "Memory not configured"}

    results = _memory.query_similar(
        _bank_id,
        query_text,
        n=n,
        section_filter=section_id or None,
    )
    return {"similar_controls": results}
