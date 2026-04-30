"""DomainConfig-aware tool implementations for the modular graph.

Each tool reads from a ``DomainConfig`` instance instead of the legacy
module-level ``SectionProfile`` / ``placement_config`` globals. The
``build_domain_tool_executor`` helper returns a closure that the graph
nodes pass to ``BaseAgent.call_llm_with_tools()`` as *tool_executor*.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from controlnexus.core.domain_config import DomainConfig

logger = logging.getLogger(__name__)


# ── Individual tool implementations ──────────────────────────────────────────


def dc_taxonomy_validator(
    level_1: str,
    level_2: str,
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Validate a (placement, control_type) pair against *config*.

    Returns ``{valid: bool, suggestion: ... | None}``.
    """
    # Build a mapping: placement_name → list[control_type_name]
    l2_by_l1: dict[str, list[str]] = {}
    for ct in config.control_types:
        for pc in ct.placement_categories:
            l2_by_l1.setdefault(pc, []).append(ct.name)

    allowed = l2_by_l1.get(level_1, [])
    if level_2 in allowed:
        return {"valid": True, "suggestion": None}

    # Find the correct placement for this control type
    for placement, types in l2_by_l1.items():
        if level_2 in types:
            return {
                "valid": False,
                "suggestion": {
                    "correct_level_1": placement,
                    "reason": f"'{level_2}' belongs under '{placement}', not '{level_1}'",
                },
            }

    return {
        "valid": False,
        "suggestion": {"reason": f"Unknown control type '{level_2}'"},
    }


def dc_regulatory_lookup(
    framework: str,
    section_id: str = "",
    *,
    process_id: str = "",
    config: DomainConfig,
) -> dict[str, Any]:
    """Look up regulatory context for *framework* in a section or process."""
    # Try process first, then fall back to process_area
    registry_source = None
    affinity_types: list[str] = []
    resolved_id = process_id or section_id

    if process_id:
        proc = config.get_process(process_id)
        if proc:
            registry_source = proc
            # Derive applicable types from risk mitigating_links
            for risk in proc.risks:
                affinity_types.extend(risk.mitigating_type_names)
            affinity_types = list(dict.fromkeys(affinity_types))

    if not registry_source and section_id:
        pa = config.get_process_area(section_id)
        if pa:
            registry_source = pa
            affinity_types = list(pa.affinity.HIGH) + list(pa.affinity.MEDIUM)

    if registry_source is None:
        return {
            "framework": framework,
            "required_themes": [],
            "applicable_types": [],
            "error": f"Unknown section/process {resolved_id}",
        }

    frameworks = registry_source.registry.regulatory_frameworks
    matching = [f for f in frameworks if framework.lower() in f.lower() or f.lower() in framework.lower()]

    return {
        "framework": framework,
        "section_id": section_id,
        "process_id": process_id,
        "required_themes": matching or [framework],
        "applicable_types": affinity_types,
        "domain": registry_source.domain if hasattr(registry_source, "domain") else "",
    }


def dc_hierarchy_search(
    section_id: str = "",
    keyword: str = "",
    *,
    process_id: str = "",
    config: DomainConfig,
) -> dict[str, Any]:
    """Return domain vocabulary for a section or process, optionally filtered by *keyword*."""
    # Try process first, then fall back to process_area
    registry_source = None
    resolved_id = process_id or section_id
    domain = ""

    if process_id:
        proc = config.get_process(process_id)
        if proc:
            registry_source = proc
            domain = proc.domain

    if not registry_source and section_id:
        pa = config.get_process_area(section_id)
        if pa:
            registry_source = pa
            domain = pa.domain

    if registry_source is None:
        return {"leaves": [], "error": f"Unknown section/process {resolved_id}"}

    kw = keyword.lower()

    def _filter(items: list[str]) -> list[str]:
        if not kw:
            return items[:5]
        matched = [i for i in items if kw in i.lower()]
        return matched[:5] if matched else items[:5]

    return {
        "section_id": section_id,
        "process_id": process_id,
        "domain": domain,
        "keyword": keyword,
        "available_roles": _filter(registry_source.registry.roles),
        "available_systems": _filter(registry_source.registry.systems),
        "available_evidence": _filter(registry_source.registry.evidence_artifacts),
        "leaves": [],
    }


def dc_frequency_lookup(
    control_type: str,
    trigger: str,
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Derive and validate frequency for *control_type* and *trigger* text."""
    # Derive frequency from trigger text using config frequency tiers
    derived = "Other"
    trigger_lower = trigger.lower()
    for tier in sorted(config.frequency_tiers, key=lambda t: t.rank):
        if any(kw in trigger_lower for kw in tier.keywords):
            derived = tier.label
            break

    # Look up expected frequency from control type config
    ct_cfg = None
    for ct in config.control_types:
        if ct.name == control_type:
            ct_cfg = ct
            break

    if ct_cfg and ct_cfg.min_frequency_tier:
        expected = ct_cfg.min_frequency_tier
        reasoning = f"'{control_type}' controls should operate at {expected.lower()} or higher frequency."
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


def dc_memory_retrieval(
    query_text: str,
    section_id: str = "",
    n: int = 5,
    *,
    memory: Any = None,
    bank_id: str = "",
) -> dict[str, Any]:
    """Retrieve similar controls from ChromaDB memory.

    Thin wrapper — delegates to the memory store if configured.
    """
    if memory is None:
        return {"similar_controls": [], "error": "Memory not configured"}

    results = memory.query_similar(
        bank_id,
        query_text,
        n=n,
        section_filter=section_id or None,
    )
    return {"similar_controls": results}


def dc_placement_lookup(
    control_type: str,
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Look up allowed placements and definitions for *control_type*."""
    ct_cfg = next((ct for ct in config.control_types if ct.name == control_type), None)
    placements = []
    for p in config.placements:
        entry: dict[str, Any] = {"name": p.name, "description": p.description}
        if ct_cfg:
            entry["allowed_for_type"] = p.name in ct_cfg.placement_categories
        placements.append(entry)

    return {
        "control_type": control_type,
        "placements": placements,
        "allowed_categories": ct_cfg.placement_categories if ct_cfg else [],
    }


def dc_method_lookup(
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Look up all control methods and their definitions."""
    return {
        "methods": [{"name": m.name, "description": m.description} for m in config.methods],
    }


def dc_evidence_rules_lookup(
    control_type: str,
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Look up evidence quality criteria for *control_type*."""
    ct_cfg = next((ct for ct in config.control_types if ct.name == control_type), None)
    if ct_cfg and ct_cfg.evidence_criteria:
        return {
            "control_type": control_type,
            "evidence_criteria": ct_cfg.evidence_criteria,
        }
    return {
        "control_type": control_type,
        "evidence_criteria": [
            "Evidence must be a specific, audit-grade artifact.",
            "Include: (1) A named artifact, (2) Who signed/approved, (3) Where retained.",
        ],
    }


def dc_exemplar_lookup(
    section_id: str = "",
    *,
    process_id: str = "",
    config: DomainConfig,
) -> dict[str, Any]:
    """Retrieve exemplar narratives for a section or process."""
    # Try process first, then fall back to process_area
    if process_id:
        proc = config.get_process(process_id)
        if proc:
            return {
                "process_id": process_id,
                "section_id": section_id,
                "exemplars": [e.model_dump() for e in proc.exemplars],
            }

    if section_id:
        pa = config.get_process_area(section_id)
        if pa:
            return {
                "section_id": section_id,
                "exemplars": [e.model_dump() for e in pa.exemplars],
            }

    return {"section_id": section_id, "process_id": process_id, "exemplars": [], "error": f"Unknown section/process"}


# ── Risk catalog tool ────────────────────────────────────────────────────────


def dc_risk_catalog_lookup(
    risk_id: str,
    *,
    config: DomainConfig,
) -> dict[str, Any]:
    """Look up a RiskCatalogEntry by ID."""
    entry = config.get_risk_catalog_entry(risk_id)
    if entry is None:
        return {"risk_id": risk_id, "error": f"Unknown risk: {risk_id}"}
    return {
        "risk_id": entry.id,
        "name": entry.name,
        "category": entry.category,
        "default_severity": entry.default_severity,
        "description": entry.description,
    }


# ── Tool executor factory ────────────────────────────────────────────────────


def build_domain_tool_executor(
    config: DomainConfig,
    *,
    memory: Any = None,
    bank_id: str = "",
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return a tool executor closure that dispatches by tool name.

    The returned callable has the signature ``(name, args) -> dict`` and
    is suitable for passing to ``BaseAgent.call_llm_with_tools()`` as the
    *tool_executor* parameter.
    """

    dispatch: dict[str, Callable[..., dict[str, Any]]] = {
        "taxonomy_validator": lambda **kw: dc_taxonomy_validator(**kw, config=config),
        "regulatory_lookup": lambda **kw: dc_regulatory_lookup(**kw, config=config),
        "hierarchy_search": lambda **kw: dc_hierarchy_search(**kw, config=config),
        "frequency_lookup": lambda **kw: dc_frequency_lookup(**kw, config=config),
        "memory_retrieval": lambda **kw: dc_memory_retrieval(**kw, memory=memory, bank_id=bank_id),
        "placement_lookup": lambda **kw: dc_placement_lookup(**kw, config=config),
        "method_lookup": lambda **kw: dc_method_lookup(config=config),
        "evidence_rules_lookup": lambda **kw: dc_evidence_rules_lookup(**kw, config=config),
        "exemplar_lookup": lambda **kw: dc_exemplar_lookup(**kw, config=config),
        "risk_catalog_lookup": lambda **kw: dc_risk_catalog_lookup(**kw, config=config),
    }

    def executor(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        func = dispatch.get(tool_name)
        if func is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return func(**arguments)
        except Exception as exc:
            logger.error("Domain tool %s failed: %s", tool_name, exc)
            return {"error": str(exc)}

    return executor
