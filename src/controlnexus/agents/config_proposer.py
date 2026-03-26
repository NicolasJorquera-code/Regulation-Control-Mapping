"""ConfigProposerAgent — LLM-powered agent for proposing DomainConfig from data.

Supports three modes:
  - ``full``: Analyze a RegisterSummary and produce a complete DomainConfig.
  - ``section_autofill``: Propose registry, affinity, risk profile for one section.
  - ``enrich``: Propose definitions, codes, evidence criteria for control types.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from controlnexus.agents.base import BaseAgent, register_agent
from controlnexus.core.domain_config import DomainConfig
from controlnexus.exceptions import AgentExecutionException

logger = logging.getLogger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

_DOMAIN_CONFIG_SCHEMA = """\
The output must be a JSON object conforming to this exact schema:

{
  "name": "string — config profile name",
  "description": "string — brief description",
  "control_types": [
    {
      "name": "string — e.g. Reconciliation",
      "definition": "string — 1-2 sentence definition",
      "code": "string — 3-letter uppercase code, e.g. REC",
      "min_frequency_tier": "string | null — one of: Daily, Weekly, Monthly, Quarterly, Semi-Annual, Annual",
      "placement_categories": ["string — Preventive, Detective, or Contingency Planning"],
      "evidence_criteria": ["string — what evidence a strong control of this type should provide"]
    }
  ],
  "business_units": [
    {
      "id": "string — e.g. BU-001",
      "name": "string",
      "description": "string",
      "primary_sections": ["string — process area IDs this BU is most involved with"],
      "key_control_types": ["string — control type names most relevant to this BU"],
      "regulatory_exposure": ["string — regulations that apply, e.g. SOX, OCC, Basel III"]
    }
  ],
  "process_areas": [
    {
      "id": "string — e.g. 1.0",
      "name": "string — e.g. Lending Operations",
      "domain": "string — snake_case version of name",
      "risk_profile": {
        "inherent_risk": "int 1-5",
        "regulatory_intensity": "int 1-5",
        "control_density": "int 1-5",
        "multiplier": "float 0.5-5.0",
        "rationale": "string — brief explanation"
      },
      "affinity": {
        "HIGH": ["control type names most relevant here"],
        "MEDIUM": ["control type names somewhat relevant"],
        "LOW": ["control type names rarely relevant"],
        "NONE": ["control type names not applicable"]
      },
      "registry": {
        "roles": ["string — job titles involved"],
        "systems": ["string — technology platforms"],
        "data_objects": ["string — types of data handled"],
        "evidence_artifacts": ["string — documentation produced"],
        "event_triggers": ["string — when controls execute"],
        "regulatory_frameworks": ["string — applicable regulations"]
      }
    }
  ]
}

IMPORTANT:
- Every control type name referenced in business_units.key_control_types or process_areas.affinity MUST exist in control_types[].name.
- Every section ID in business_units.primary_sections MUST exist in process_areas[].id.
- placement_categories values must be from: Preventive, Detective, Contingency Planning.
- min_frequency_tier must be from: Daily, Weekly, Monthly, Quarterly, Semi-Annual, Annual (or null).
"""

SYSTEM_PROMPT_FULL = f"""\
You are a control framework domain expert. Analyze the provided register summary \
(extracted from an Excel file of existing controls) and propose a complete \
organization-specific configuration.

Infer the organization's control taxonomy, business structure, and process areas \
from the data patterns. Be specific and accurate — use the actual control types, \
business units, and sections found in the register. For definitions, evidence \
criteria, and rationale, use your domain expertise to provide meaningful content.

{_DOMAIN_CONFIG_SCHEMA}

Return ONLY the JSON object with no additional text or markdown formatting."""

SYSTEM_PROMPT_SECTION = """\
You are a control framework domain expert. Given a process area name, the \
organization's control types, and optional context, propose the registry, \
affinity matrix, risk profile, and exemplar for that specific process area.

Return ONLY a JSON object with these keys:
{
  "risk_profile": {"inherent_risk": 1-5, "regulatory_intensity": 1-5, "control_density": 1-5, "multiplier": float, "rationale": "..."},
  "affinity": {"HIGH": [...], "MEDIUM": [...], "LOW": [...], "NONE": [...]},
  "registry": {"roles": [...], "systems": [...], "data_objects": [...], "evidence_artifacts": [...], "event_triggers": [...], "regulatory_frameworks": [...]},
  "exemplars": [{"control_type": "...", "placement": "...", "method": "...", "full_description": "30-80 word narrative", "word_count": int, "quality_rating": "Effective"}]
}

IMPORTANT: Only use control type names that appear in the provided control_types list.
Return ONLY the JSON, no additional text."""

SYSTEM_PROMPT_ENRICH = """\
You are a control framework domain expert. Given a list of control type names, \
propose detailed definitions, 3-letter codes, evidence criteria, minimum \
frequency tiers, and placement categories for each.

Return ONLY a JSON object:
{
  "control_types": [
    {
      "name": "exact name from input",
      "definition": "1-2 sentence expert definition",
      "code": "3-letter uppercase code",
      "min_frequency_tier": "Daily|Weekly|Monthly|Quarterly|Semi-Annual|Annual or null",
      "placement_categories": ["Preventive" and/or "Detective" and/or "Contingency Planning"],
      "evidence_criteria": ["2-4 criteria strings for evaluating evidence quality"]
    }
  ]
}

Return ONLY the JSON, no additional text."""


# ── Deterministic fallback builders ───────────────────────────────────────────


def _auto_code(name: str) -> str:
    """Generate a 3-letter code from consonants of a name."""
    consonants = re.sub(r"[aeiouAEIOU\s\-,]", "", name)
    return consonants[:3].upper() or "UNK"


def _build_deterministic_config(summary_dict: dict[str, Any]) -> dict[str, Any]:
    """Build a basic DomainConfig dict from a RegisterSummary without LLM."""
    control_types = []
    type_names = summary_dict.get("unique_control_types", [])
    for ct_name in type_names:
        control_types.append(
            {
                "name": ct_name,
                "definition": f"Controls related to {ct_name.lower()}.",
                "code": _auto_code(ct_name),
                "min_frequency_tier": None,
                "placement_categories": [],
                "evidence_criteria": [],
            }
        )

    # Infer placement categories from detected placements
    detected_placements = summary_dict.get("unique_placements", [])
    valid_placements = {"Preventive", "Detective", "Contingency Planning"}
    for ct in control_types:
        for p in detected_placements:
            if p in valid_placements:
                ct["placement_categories"].append(p)
        if not ct["placement_categories"]:
            ct["placement_categories"] = ["Detective"]

    business_units = []
    for i, bu_data in enumerate(summary_dict.get("unique_business_units", []), 1):
        bu_id = bu_data.get("id", f"BU-{i:03d}")
        if not bu_id.startswith("BU-"):
            bu_id = f"BU-{i:03d}"
        business_units.append(
            {
                "id": bu_id,
                "name": bu_data.get("name", f"Unit {i}"),
                "description": "",
                "primary_sections": [],
                "key_control_types": type_names[:3] if type_names else [],
                "regulatory_exposure": summary_dict.get("regulatory_mentions", [])[:3],
            }
        )

    process_areas = []
    sections = summary_dict.get("unique_sections", [])
    for sec in sections:
        sec_id = sec.get("id", "1.0")
        sec_name = sec.get("name", f"Section {sec_id}")
        domain = re.sub(r"[^a-z0-9]+", "_", sec_name.lower()).strip("_")

        # Distribute types across affinity levels
        high_types = type_names[: max(1, len(type_names) // 3)]
        medium_types = type_names[len(high_types) : len(high_types) + max(1, len(type_names) // 3)]
        low_types = type_names[len(high_types) + len(medium_types) :]

        process_areas.append(
            {
                "id": sec_id,
                "name": sec_name,
                "domain": domain,
                "risk_profile": {
                    "inherent_risk": 3,
                    "regulatory_intensity": 3,
                    "control_density": 3,
                    "multiplier": 1.0,
                    "rationale": f"Default risk profile for {sec_name}.",
                },
                "affinity": {
                    "HIGH": high_types,
                    "MEDIUM": medium_types,
                    "LOW": low_types,
                    "NONE": [],
                },
                "registry": {
                    "roles": summary_dict.get("role_mentions", [])[:5],
                    "systems": summary_dict.get("system_mentions", [])[:5],
                    "data_objects": [],
                    "evidence_artifacts": [],
                    "event_triggers": [],
                    "regulatory_frameworks": summary_dict.get("regulatory_mentions", [])[:5],
                },
            }
        )

    # Wire BU primary_sections
    section_ids = [pa["id"] for pa in process_areas]
    for bu in business_units:
        bu["primary_sections"] = section_ids[:2] if section_ids else []

    # Need at least one control type
    if not control_types:
        control_types = [
            {
                "name": "General Control",
                "definition": "A general-purpose control activity.",
                "code": "GNR",
                "min_frequency_tier": None,
                "placement_categories": ["Detective"],
                "evidence_criteria": [],
            }
        ]

    name = summary_dict.get("name", "imported-config")
    return {
        "name": name,
        "description": f"Configuration auto-generated from uploaded register ({summary_dict.get('row_count', 0)} controls).",
        "control_types": control_types,
        "business_units": business_units,
        "process_areas": process_areas,
    }


def _build_deterministic_section(
    section_name: str,
    control_type_names: list[str],
) -> dict[str, Any]:
    """Build a deterministic section autofill result."""
    high = control_type_names[: max(1, len(control_type_names) // 3)]
    medium = control_type_names[len(high) : len(high) + max(1, len(control_type_names) // 3)]
    low = control_type_names[len(high) + len(medium) :]

    return {
        "risk_profile": {
            "inherent_risk": 3,
            "regulatory_intensity": 3,
            "control_density": 3,
            "multiplier": 1.0,
            "rationale": f"Default risk profile for {section_name}.",
        },
        "affinity": {
            "HIGH": high,
            "MEDIUM": medium,
            "LOW": low,
            "NONE": [],
        },
        "registry": {
            "roles": [f"{section_name} Manager", f"{section_name} Analyst"],
            "systems": [],
            "data_objects": [],
            "evidence_artifacts": [],
            "event_triggers": [],
            "regulatory_frameworks": [],
        },
        "exemplars": [],
    }


def _build_deterministic_enrichment(type_names: list[str]) -> dict[str, Any]:
    """Build deterministic control type enrichment."""
    return {
        "control_types": [
            {
                "name": name,
                "definition": f"Controls related to {name.lower()}.",
                "code": _auto_code(name),
                "min_frequency_tier": None,
                "placement_categories": ["Detective"],
                "evidence_criteria": [],
            }
            for name in type_names
        ]
    }


# ── Agent ─────────────────────────────────────────────────────────────────────


@register_agent
class ConfigProposerAgent(BaseAgent):
    """Proposes DomainConfig content from register data or partial config.

    Modes:
        - ``full``: Analyze ``RegisterSummary`` → complete DomainConfig dict.
        - ``section_autofill``: Propose registry/affinity/risk for one section.
        - ``enrich``: Propose definitions/codes/evidence for control types.
    """

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        mode = kwargs.get("mode", "full")
        if mode == "full":
            return await self._execute_full(**kwargs)
        elif mode == "section_autofill":
            return await self._execute_section_autofill(**kwargs)
        elif mode == "enrich":
            return await self._execute_enrich(**kwargs)
        else:
            raise AgentExecutionException(f"Unknown mode: {mode}")

    # ── Full mode ─────────────────────────────────────────────────────────

    async def _execute_full(self, **kwargs: Any) -> dict[str, Any]:
        register_summary = kwargs.get("register_summary", {})
        t0 = time.monotonic()
        logger.info("ConfigProposerAgent (full) started")

        # Convert Pydantic model to dict for uniform access
        if hasattr(register_summary, "model_dump"):
            summary_dict = register_summary.model_dump()
        else:
            summary_dict = register_summary

        if self.client is None:
            logger.info("No LLM client — using deterministic fallback")
            result = _build_deterministic_config(summary_dict)
            # Validate
            DomainConfig(**result)
            logger.info("ConfigProposerAgent (full) completed deterministic (%.3fs)", time.monotonic() - t0)
            return result

        user_prompt = json.dumps(summary_dict, indent=2, default=str)
        try:
            raw = await self.call_llm(SYSTEM_PROMPT_FULL, user_prompt, max_tokens=4096)
            result = self.parse_json(raw)

            # Validate — retry once on failure
            try:
                DomainConfig(**result)
            except Exception as e:
                logger.warning("First LLM proposal failed validation: %s — retrying", e)
                retry_prompt = (
                    f"Your previous response failed DomainConfig validation:\n{e}\n\n"
                    f"Original register summary:\n{user_prompt}\n\n"
                    f"Fix the issues and return a corrected JSON."
                )
                raw = await self.call_llm(SYSTEM_PROMPT_FULL, retry_prompt, max_tokens=4096)
                result = self.parse_json(raw)
                try:
                    DomainConfig(**result)
                except Exception:
                    logger.warning("Retry also failed — falling back to deterministic")
                    result = _build_deterministic_config(register_summary)
                    DomainConfig(**result)

            logger.info("ConfigProposerAgent (full) completed (%.3fs)", time.monotonic() - t0)
            return result

        except Exception as exc:
            logger.warning("LLM call failed: %s — falling back to deterministic", exc)
            result = _build_deterministic_config(register_summary)
            DomainConfig(**result)
            return result

    # ── Section autofill mode ─────────────────────────────────────────────

    async def _execute_section_autofill(self, **kwargs: Any) -> dict[str, Any]:
        section_name = kwargs.get("section_name", "")
        control_type_names = kwargs.get("control_type_names", [])
        config_context = kwargs.get("config_context", {})
        t0 = time.monotonic()
        logger.info("ConfigProposerAgent (section_autofill) started for '%s'", section_name)

        if self.client is None:
            result = _build_deterministic_section(section_name, control_type_names)
            logger.info("ConfigProposerAgent (section_autofill) completed deterministic (%.3fs)", time.monotonic() - t0)
            return result

        user_prompt = json.dumps(
            {
                "section_name": section_name,
                "control_types": control_type_names,
                "config_name": config_context.get("name", ""),
                "config_description": config_context.get("description", ""),
            },
            indent=2,
        )

        try:
            raw = await self.call_llm(SYSTEM_PROMPT_SECTION, user_prompt, max_tokens=2048)
            result = self.parse_json(raw)
            logger.info("ConfigProposerAgent (section_autofill) completed (%.3fs)", time.monotonic() - t0)
            return result
        except Exception as exc:
            logger.warning("Section autofill LLM failed: %s — using deterministic", exc)
            return _build_deterministic_section(section_name, control_type_names)

    # ── Enrich mode ───────────────────────────────────────────────────────

    async def _execute_enrich(self, **kwargs: Any) -> dict[str, Any]:
        type_names = kwargs.get("type_names", [])
        t0 = time.monotonic()
        logger.info("ConfigProposerAgent (enrich) started for %d types", len(type_names))

        if self.client is None:
            result = _build_deterministic_enrichment(type_names)
            logger.info("ConfigProposerAgent (enrich) completed deterministic (%.3fs)", time.monotonic() - t0)
            return result

        user_prompt = json.dumps({"control_type_names": type_names}, indent=2)
        try:
            raw = await self.call_llm(SYSTEM_PROMPT_ENRICH, user_prompt, max_tokens=2048)
            result = self.parse_json(raw)
            logger.info("ConfigProposerAgent (enrich) completed (%.3fs)", time.monotonic() - t0)
            return result
        except Exception as exc:
            logger.warning("Enrich LLM failed: %s — using deterministic", exc)
            return _build_deterministic_enrichment(type_names)
