"""Helper functions for ControlForge Modular graph.

Assignment matrix builder, deterministic spec/narrative/enrichment builders,
config-aware prompt templates, and control ID generation — all driven by
DomainConfig.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

from controlnexus.core.constants import DEFAULT_QUALITY_RATING
from controlnexus.core.domain_config import DomainConfig


# ── Assignment Matrix ─────────────────────────────────────────────────────────


def build_assignment_matrix(
    config: DomainConfig,
    target_count: int,
    distribution_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a list of control assignments from configuration.

    Each assignment is a dict with keys:
        section_id, section_name, control_type, business_unit_id,
        business_unit_name, leaf_name

    Args:
        config: The loaded DomainConfig.
        target_count: Total number of controls to generate.
        distribution_config: Optional user overrides with keys:
            - type_weights: dict[str, float] mapping type name to relative weight
            - section_weights: dict[str, float] mapping section id to relative weight
    """
    if not config.process_areas:
        return _build_assignments_no_sections(config, target_count, distribution_config)

    type_names = [ct.name for ct in config.control_types]
    section_ids = config.section_ids()

    # Determine per-type count
    type_counts = _distribute_by_weight(
        type_names,
        target_count,
        (distribution_config or {}).get("type_weights"),
    )

    # Determine per-section count (weighted by risk multiplier)
    default_section_weights = {pa.id: pa.risk_profile.multiplier for pa in config.process_areas}
    section_weight_overrides = (distribution_config or {}).get("section_weights")
    section_weights = section_weight_overrides if section_weight_overrides else default_section_weights
    section_counts = _distribute_by_weight(section_ids, target_count, section_weights)

    # Build BU cycle per section
    bu_cycle = _build_bu_cycles(config)

    # Allocate assignments: distribute types across sections
    assignments: list[dict[str, Any]] = []
    type_remaining = dict(type_counts)
    section_remaining = dict(section_counts)

    # Round-robin: iterate sections, for each section pick types that have affinity
    section_cycle = itertools.cycle(section_ids)
    type_cycle = itertools.cycle(type_names)
    # Safety cap must be large enough that the cycle can visit every
    # section×type combination even when only a few slots remain.
    max_iterations = max(target_count * 10, len(section_ids) * len(type_names) * 2)

    for _ in range(max_iterations):
        if sum(type_remaining.values()) <= 0 or len(assignments) >= target_count:
            break

        section_id = next(section_cycle)
        if section_remaining.get(section_id, 0) <= 0:
            continue

        # Pick a type that still needs allocation
        for __ in range(len(type_names)):
            ct = next(type_cycle)
            if type_remaining.get(ct, 0) > 0:
                break
        else:
            continue

        if type_remaining.get(ct, 0) <= 0:
            continue

        pa = config.get_process_area(section_id)
        section_name = pa.name if pa else section_id
        domain = pa.domain if pa else ""

        # Get BU
        bu_id, bu_name = _next_bu(bu_cycle, section_id, config)

        assignments.append(
            {
                "section_id": section_id,
                "section_name": section_name,
                "domain": domain,
                "control_type": ct,
                "business_unit_id": bu_id,
                "business_unit_name": bu_name,
                "leaf_name": f"{section_name} – {ct}",
                "hierarchy_id": f"{section_id}.1.1",
            }
        )

        type_remaining[ct] -= 1
        section_remaining[section_id] -= 1

    return assignments[:target_count]


def _build_assignments_no_sections(
    config: DomainConfig,
    target_count: int,
    distribution_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fallback when no process areas are defined."""
    type_names = [ct.name for ct in config.control_types]
    type_counts = _distribute_by_weight(
        type_names,
        target_count,
        (distribution_config or {}).get("type_weights"),
    )

    bu_list = config.business_units or [None]
    bu_cycle = itertools.cycle(bu_list)
    assignments: list[dict[str, Any]] = []

    for ct_name, count in type_counts.items():
        for i in range(count):
            bu = next(bu_cycle)
            assignments.append(
                {
                    "section_id": "0.0",
                    "section_name": "General",
                    "domain": "",
                    "control_type": ct_name,
                    "business_unit_id": bu.id if bu else "BU-DEFAULT",
                    "business_unit_name": bu.name if bu else "Default",
                    "leaf_name": f"General – {ct_name}",
                    "hierarchy_id": "0.0.1.1",
                }
            )

    return assignments[:target_count]


def _distribute_by_weight(
    items: list[str],
    total: int,
    weights: dict[str, float] | None = None,
) -> dict[str, int]:
    """Distribute ``total`` across ``items`` proportionally to weights.

    If weights is None, distributes evenly.
    """
    if not items:
        return {}

    if weights is None:
        base, remainder = divmod(total, len(items))
        result = {item: base for item in items}
        for i in range(remainder):
            result[items[i]] += 1
        return result

    total_weight = sum(weights.get(item, 1.0) for item in items)
    if total_weight <= 0:
        total_weight = len(items)

    raw = {item: (weights.get(item, 1.0) / total_weight) * total for item in items}

    # Floor + distribute remainder by largest fractional part
    floored = {item: int(v) for item, v in raw.items()}
    remainder = total - sum(floored.values())
    fractionals = sorted(
        items,
        key=lambda item: raw[item] - floored[item],
        reverse=True,
    )
    for i in range(remainder):
        floored[fractionals[i % len(fractionals)]] += 1

    return floored


def _build_bu_cycles(config: DomainConfig) -> dict[str, itertools.cycle]:
    """Build a BU cycle iterator per section.

    Prefers BUs whose primary_sections include this section.
    Falls back to cycling all BUs.
    """
    if not config.business_units:
        return {}

    cycles: dict[str, itertools.cycle] = {}
    all_bus = config.business_units

    for pa in config.process_areas:
        matching = [bu for bu in all_bus if pa.id in bu.primary_sections]
        pool = matching if matching else all_bus
        cycles[pa.id] = itertools.cycle(pool)

    return cycles


def _next_bu(
    bu_cycles: dict[str, itertools.cycle],
    section_id: str,
    config: DomainConfig,
) -> tuple[str, str]:
    """Get next BU id and name for a section."""
    if not config.business_units:
        return "BU-DEFAULT", "Default"

    cycle = bu_cycles.get(section_id)
    if cycle:
        bu = next(cycle)
        return bu.id, bu.name

    bu = config.business_units[0]
    return bu.id, bu.name


# ── Deterministic Builders ────────────────────────────────────────────────────


def build_deterministic_spec(
    assignment: dict[str, Any],
    config: DomainConfig,
) -> dict[str, Any]:
    """Build a spec dict from the assignment and config registry."""
    section_id = assignment["section_id"]
    pa = config.get_process_area(section_id)

    roles = pa.registry.roles if pa else ["Analyst"]
    systems = pa.registry.systems if pa else ["Enterprise System"]
    triggers = pa.registry.event_triggers if pa else ["at each review cycle"]
    evidence = pa.registry.evidence_artifacts if pa else ["documented approval"]

    ct_name = assignment["control_type"]

    # Determine placement from control type config
    ct_cfg = next((ct for ct in config.control_types if ct.name == ct_name), None)
    placement = ct_cfg.placement_categories[0] if ct_cfg and ct_cfg.placement_categories else "Detective"

    # Pick method based on placement
    method = "Automated" if placement == "Preventive" else "Manual"

    # Cycle through registry items based on a hash for determinism
    idx = hash(f"{section_id}-{ct_name}") % max(len(roles), 1)

    return {
        "hierarchy_id": assignment.get("hierarchy_id", f"{section_id}.1.1"),
        "leaf_name": assignment.get("leaf_name", ""),
        "control_type": ct_name,
        "selected_level_1": placement,
        "selected_level_2": ct_name,
        "business_unit_id": assignment["business_unit_id"],
        "business_unit_name": assignment["business_unit_name"],
        "placement": placement,
        "method": method,
        "who": roles[idx % len(roles)],
        "what_action": f"performs {ct_name.lower()} control activities",
        "what_detail": ct_cfg.definition[:120] if ct_cfg else "",
        "when": triggers[idx % len(triggers)] if triggers else "at each review cycle",
        "where_system": systems[idx % len(systems)] if systems else "Enterprise System",
        "why_risk": f"to mitigate risk of control failures in {assignment.get('section_name', 'the process area')}",
        "evidence": evidence[idx % len(evidence)] if evidence else "documented approval",
    }


def build_deterministic_narrative(
    spec: dict[str, Any],
    config: DomainConfig,
) -> dict[str, Any]:
    """Build a 5W narrative from a spec dict."""
    who = spec.get("who", "Analyst")
    what = spec.get("what_action", "performs control activities")
    when = spec.get("when", "at each review cycle")
    where = spec.get("where_system", "Enterprise System")
    why = spec.get("why_risk", "to mitigate risk")
    evidence = spec.get("evidence", "documented approval")

    full_description = (
        f"{when.rstrip(',').capitalize()}, the {who} {what} "
        f"within the {where} {why}, "
        f"with results documented via {evidence}."
    )

    # Derive frequency
    frequency = _derive_frequency(when, config)

    return {
        "who": who,
        "what": what,
        "when": when,
        "where": where,
        "why": why,
        "full_description": full_description,
        "frequency": frequency,
        "evidence": evidence,
    }


def build_deterministic_enriched(
    spec: dict[str, Any],
    narrative: dict[str, Any],
    config: DomainConfig,
) -> dict[str, Any]:
    """Build an enriched record by merging spec + narrative."""
    # Derive selected_level_2 from control_type if the LLM didn't return it
    selected_level_2 = spec.get("selected_level_2") or spec.get("control_type", "")

    # Look up business_unit_name from config if spec only has the ID
    bu_name = spec.get("business_unit_name", "")
    if not bu_name or bu_name == "Default":
        bu_id = spec.get("business_unit_id", "")
        bu_match = next((bu for bu in config.business_units if bu.id == bu_id), None)
        bu_name = bu_match.name if bu_match else (bu_name or "Default")

    # Derive frequency from when text if narrative doesn't include it
    frequency = narrative.get("frequency") or _derive_frequency(
        narrative.get("when", ""),
        config,
    )

    return {
        "control_id": "",  # set later by finalize
        "hierarchy_id": spec.get("hierarchy_id", ""),
        "leaf_name": spec.get("leaf_name", ""),
        "control_type": spec.get("control_type", ""),
        "selected_level_1": spec.get("selected_level_1", "Unspecified"),
        "selected_level_2": selected_level_2,
        "business_unit_id": spec.get("business_unit_id", "BU-DEFAULT"),
        "business_unit_name": bu_name,
        "placement": spec.get("placement", "Detective"),
        "method": spec.get("method", "Manual"),
        "who": narrative.get("who", ""),
        "what": narrative.get("what", ""),
        "when": narrative.get("when", ""),
        "frequency": frequency,
        "where": narrative.get("where", ""),
        "why": narrative.get("why", ""),
        "full_description": narrative.get("full_description", ""),
        "quality_rating": DEFAULT_QUALITY_RATING,
        "validator_passed": True,
        "validator_retries": 0,
        "validator_failures": [],
        "evidence": narrative.get("evidence", ""),
    }


def assign_control_ids(
    records: list[dict[str, Any]],
    config: DomainConfig,
) -> list[dict[str, Any]]:
    """Assign control IDs to a list of records using config type codes."""
    code_map = config.type_code_map()
    type_counters: dict[str, int] = {}

    for record in records:
        ct = record.get("control_type", "")
        type_code = code_map.get(ct, _auto_code(ct))
        type_counters[type_code] = type_counters.get(type_code, 0) + 1
        seq = type_counters[type_code]

        hierarchy_id = record.get("hierarchy_id", "0.0")
        parts = hierarchy_id.split(".")
        l1 = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
        l2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        record["control_id"] = f"CTRL-{l1:02d}{l2:02d}-{type_code}-{seq:03d}"

    return records


def _auto_code(name: str) -> str:
    """Generate a 3-letter code from consonants."""
    consonants = re.sub(r"[aeiouAEIOU\s\-,]", "", name)
    return consonants[:3].upper() or "UNK"


def _derive_frequency(when_text: str, config: DomainConfig) -> str:
    """Derive frequency from a when string using config frequency tiers."""
    if not when_text:
        return "Other"

    normalized = re.sub(r"\s+", " ", when_text.strip().lower())
    for tier in sorted(config.frequency_tiers, key=lambda t: t.rank):
        if any(kw in normalized for kw in tier.keywords):
            return tier.label

    return "Other"


# ── Config-Aware Prompt Templates ─────────────────────────────────────────────


def build_spec_system_prompt(config: DomainConfig) -> str:
    """Build a system prompt for the SpecAgent using DomainConfig values."""
    placements = ", ".join(config.placement_names())
    methods = ", ".join(config.method_names())

    # Collect evidence criteria across all control types
    evidence_rules: list[str] = []
    for ct in config.control_types:
        for ec in ct.evidence_criteria:
            if ec not in evidence_rules:
                evidence_rules.append(ec)

    evidence_section = ""
    if evidence_rules:
        evidence_section = "EVIDENCE QUALITY RULES:\n" + "\n".join(f"- {rule}" for rule in evidence_rules)
    else:
        evidence_section = (
            "EVIDENCE QUALITY RULES: The evidence field must be a specific, audit-grade "
            "artifact description that a junior auditor could retrieve without follow-up "
            "questions. It must include: (1) A specific named artifact, (2) Who signed or "
            "approved it, (3) Where it is retained."
        )

    return (
        "You are SpecAgent. Produce a locked control specification JSON for one control. "
        "Choose exactly one who, what_action, when, where_system, why_risk, and business_unit_id. "
        "Return ONLY JSON with keys: hierarchy_id, leaf_name, selected_level_1, selected_level_2, "
        "control_type, placement, method, who, what_action, what_detail, when, where_system, "
        "why_risk, evidence, business_unit_id.\n\n"
        "selected_level_2 should be the control type name (e.g. Reconciliation, Authorization).\n\n"
        f"ALLOWED PLACEMENTS: {placements}\n"
        f"ALLOWED METHODS: {methods}\n\n"
        f"{evidence_section}"
    )


def build_spec_user_prompt(assignment: dict[str, Any], config: DomainConfig) -> str:
    """Build a user prompt for the SpecAgent from assignment + config."""
    ct_name = assignment.get("control_type", "")
    ct_cfg = next((ct for ct in config.control_types if ct.name == ct_name), None)

    section_id = assignment.get("section_id", "")
    pa = config.get_process_area(section_id)

    registry = pa.registry.model_dump() if pa else {}
    placement_defs = [p.model_dump() for p in config.placements]
    method_defs = [m.model_dump() for m in config.methods]

    # Build taxonomy constraints for this control type
    taxonomy_constraints: dict[str, Any] = {
        "level_1_options": config.placement_names(),
        "allowed_level_2_for_selected_level_1": ct_name,
    }
    if ct_cfg:
        taxonomy_constraints["placement_categories"] = ct_cfg.placement_categories

    # Build diversity context from business units
    diversity_context: dict[str, Any] = {
        "available_business_units": [{"business_unit_id": bu.id, "name": bu.name} for bu in config.business_units],
    }
    suggested_bu = assignment.get("business_unit_id")
    if suggested_bu:
        diversity_context["suggested_business_unit"] = suggested_bu

    return json.dumps(
        {
            "leaf": {
                "hierarchy_id": assignment.get("hierarchy_id", ""),
                "leaf_name": assignment.get("leaf_name", ""),
                "section_name": assignment.get("section_name", ""),
                "domain": assignment.get("domain", ""),
            },
            "control_type": ct_name,
            "control_type_definition": ct_cfg.definition if ct_cfg else "",
            "domain_registry": registry,
            "control_placement_definitions": {"placements": placement_defs},
            "control_method_definitions": {"methods": method_defs},
            "taxonomy_constraints": taxonomy_constraints,
            "diversity_context": diversity_context,
        },
        indent=2,
    )


def build_narrative_system_prompt(config: DomainConfig) -> str:
    """Build a system prompt for the NarrativeAgent using DomainConfig values."""
    word_min = config.narrative.word_count_min
    word_max = config.narrative.word_count_max

    field_lines: list[str] = []
    for f in config.narrative.fields:
        if f.definition:
            field_lines.append(f"- {f.name}: {f.definition}")
        else:
            field_lines.append(f"- {f.name}")

    output_keys = ", ".join(f.name for f in config.narrative.fields)

    return (
        "You are NarrativeAgent. Convert the locked control specification into 5W prose. "
        "You must preserve locked spec values for who and where_system exactly in output fields. "
        f"Return ONLY JSON with keys: {output_keys}.\n\n"
        "OUTPUT FIELD DEFINITIONS:\n"
        + "\n".join(field_lines)
        + f"\n\nWord count for full_description must be between {word_min} and {word_max} words."
    )


def build_narrative_user_prompt(
    spec: dict[str, Any],
    config: DomainConfig,
    retry_appendix: str | None = None,
) -> str:
    """Build a user prompt for the NarrativeAgent from spec + config."""
    section_id = (
        spec.get("hierarchy_id", "").split(".")[0]
        + "."
        + (spec.get("hierarchy_id", "0.0").split(".")[1] if "." in spec.get("hierarchy_id", "") else "0")
    )
    pa = config.get_process_area(section_id)

    exemplars = []
    if pa:
        exemplars = [e.model_dump() for e in pa.exemplars]

    payload = {
        "locked_spec": spec,
        "exemplars": exemplars,
        "constraints": [
            "Use exactly one primary action in WHAT.",
            "WHEN must be specific and avoid vague terms.",
            f"Word count for full_description must be between "
            f"{config.narrative.word_count_min} and {config.narrative.word_count_max} words.",
            "Do not change locked spec values for who and where_system.",
        ],
    }

    prompt = json.dumps(payload, indent=2)
    if retry_appendix:
        prompt += "\n\n" + retry_appendix
    return prompt


def build_enricher_system_prompt(config: DomainConfig) -> str:
    """Build a system prompt for the EnricherAgent using DomainConfig values."""
    ratings = ", ".join(config.quality_ratings)
    word_min = config.narrative.word_count_min
    word_max = config.narrative.word_count_max

    return (
        "You are EnricherAgent. Refine control prose slightly for clarity while "
        "preserving meaning, then assign one quality rating from: "
        f"{ratings}. "
        "Return ONLY JSON with keys: refined_full_description, quality_rating, rationale.\n\n"
        f"Keep refined description between {word_min} and {word_max} words. "
        "Do not change control facts (who/what/when/where/why). "
        "Rating must be exactly one allowed label."
    )


def build_enricher_user_prompt(
    validated_control: dict[str, Any],
    config: DomainConfig,
) -> str:
    """Build a user prompt for the EnricherAgent from narrative + config."""
    return json.dumps(
        {
            "validated_control": validated_control,
            "quality_ratings": config.quality_ratings,
        },
        indent=2,
    )


# ── Slim Prompt Builders (OpenAI / tool-calling providers) ────────────────────
#
# These strip inline domain data (placements, methods, evidence rules,
# exemplars, registry) from prompts.  The LLM is instructed to call lookup
# tools instead.  This reduces token usage by ~55-60% while keeping the
# same agent structure.
# --------------------------------------------------------------------------


def build_slim_spec_system_prompt(config: DomainConfig) -> str:
    """Slim SpecAgent system prompt — output schema only, no inline data."""
    return (
        "You are SpecAgent. Produce a locked control specification JSON for one control.\n\n"
        "Return ONLY JSON with keys: hierarchy_id, leaf_name, selected_level_1, selected_level_2, "
        "control_type, placement, method, who, what_action, what_detail, when, where_system, "
        "why_risk, evidence, business_unit_id.\n\n"
        "selected_level_2 should be the control type name (e.g. Reconciliation, Authorization).\n\n"
        "IMPORTANT: You MUST use tools to look up allowed placements, methods, and evidence "
        "rules before producing your JSON. Call placement_lookup to get valid placements for "
        "the control type, method_lookup to get valid methods, and evidence_rules_lookup to "
        "get evidence quality criteria. Also call taxonomy_validator to verify your "
        "(level_1, level_2) pair."
    )


def build_slim_spec_user_prompt(assignment: dict[str, Any], config: DomainConfig) -> str:
    """Slim SpecAgent user prompt — leaf info + control type only."""
    ct_name = assignment.get("control_type", "")

    diversity_context: dict[str, Any] = {
        "available_business_units": [{"business_unit_id": bu.id, "name": bu.name} for bu in config.business_units],
    }
    suggested_bu = assignment.get("business_unit_id")
    if suggested_bu:
        diversity_context["suggested_business_unit"] = suggested_bu

    return json.dumps(
        {
            "leaf": {
                "hierarchy_id": assignment.get("hierarchy_id", ""),
                "leaf_name": assignment.get("leaf_name", ""),
                "section_name": assignment.get("section_name", ""),
                "domain": assignment.get("domain", ""),
            },
            "control_type": ct_name,
            "diversity_context": diversity_context,
            "instructions": (
                "Use placement_lookup, method_lookup, and evidence_rules_lookup tools "
                "to retrieve allowed values before generating JSON."
            ),
        },
        indent=2,
    )


def build_slim_narrative_system_prompt(config: DomainConfig) -> str:
    """Slim NarrativeAgent system prompt — output schema + word limits, no exemplars."""
    word_min = config.narrative.word_count_min
    word_max = config.narrative.word_count_max

    field_lines: list[str] = []
    for f in config.narrative.fields:
        if f.definition:
            field_lines.append(f"- {f.name}: {f.definition}")
        else:
            field_lines.append(f"- {f.name}")

    output_keys = ", ".join(f.name for f in config.narrative.fields)

    return (
        "You are NarrativeAgent. Convert the locked control specification into 5W prose. "
        "You must preserve locked spec values for who and where_system exactly in output fields. "
        f"Return ONLY JSON with keys: {output_keys}.\n\n"
        "OUTPUT FIELD DEFINITIONS:\n"
        + "\n".join(field_lines)
        + f"\n\nWord count for full_description must be between {word_min} and {word_max} words.\n\n"
        "IMPORTANT: You MUST use the exemplar_lookup tool to retrieve example narratives "
        "for the relevant section before writing prose. Also use frequency_lookup to "
        "determine the correct frequency for the control type."
    )


def build_slim_narrative_user_prompt(
    spec: dict[str, Any],
    config: DomainConfig,
    retry_appendix: str | None = None,
) -> str:
    """Slim NarrativeAgent user prompt — locked spec + constraints only, no exemplars."""
    payload = {
        "locked_spec": spec,
        "constraints": [
            "Use exactly one primary action in WHAT.",
            "WHEN must be specific and avoid vague terms.",
            f"Word count for full_description must be between "
            f"{config.narrative.word_count_min} and {config.narrative.word_count_max} words.",
            "Do not change locked spec values for who and where_system.",
        ],
        "instructions": ("Use exemplar_lookup to get example narratives and frequency_lookup to validate timing."),
    }

    prompt = json.dumps(payload, indent=2)
    if retry_appendix:
        prompt += "\n\n" + retry_appendix
    return prompt


# ── XML tool-call instruction builder (ICA XML mode) ─────────────────────────


def build_xml_tool_instructions(tool_schemas: list[dict[str, Any]]) -> str:
    """Build a prompt addendum that teaches the LLM to emit XML tool calls.

    Converts OpenAI-format tool schemas into a text description of available
    tools and the ``<tool_call>`` XML format the LLM should use.
    """
    lines = [
        "\n\n--- TOOL CALLING INSTRUCTIONS ---",
        "",
        "You have access to the following tools. To call a tool, emit an XML block",
        "in your response using this exact format:",
        "",
        "<tool_call>",
        "<name>TOOL_NAME</name>",
        '<arguments>{"param": "value"}</arguments>',
        "</tool_call>",
        "",
        "You may call multiple tools in a single response. After each tool call,",
        "you will receive results in <tool_result> blocks. Use those results to",
        "inform your final answer.",
        "",
        "When you have enough information, respond with ONLY the raw JSON object.",
        "Do NOT include <tool_call> blocks in your final response.",
        "Do NOT wrap the JSON in markdown code fences (``` ```json ```).",
        "Do NOT include any prose, explanation, or commentary — output ONLY the JSON object.",
        "",
        "IMPORTANT: You MUST call the relevant tools to look up domain data",
        "before producing your JSON response. Do not guess values.",
        "",
        "Available tools:",
        "",
    ]

    for schema in tool_schemas:
        fn = schema.get("function", {})
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})
        props = params.get("properties", {})
        required = params.get("required", [])

        lines.append(f"  {name}: {desc}")
        if props:
            lines.append("    Parameters:")
            for pname, pdef in props.items():
                ptype = pdef.get("type", "string")
                pdesc = pdef.get("description", "")
                req_marker = " (required)" if pname in required else ""
                lines.append(f"      - {pname} ({ptype}){req_marker}: {pdesc}")
        lines.append("")

    return "\n".join(lines)
