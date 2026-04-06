"""SpecAgent -- produces a locked control specification.

Given an APQC leaf, control type, and domain context, the SpecAgent calls the
LLM to generate a complete control specification with all required fields.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from controlnexus.agents.base import BaseAgent, register_agent
from controlnexus.exceptions import AgentExecutionException

logger = logging.getLogger(__name__)


@register_agent
class SpecAgent(BaseAgent):
    """Generate a locked control specification for one control."""

    async def execute(
        self,
        *,
        leaf: dict[str, Any],
        control_type: str,
        type_definition: str,
        registry: dict[str, Any],
        placement_defs: dict[str, Any],
        method_defs: dict[str, Any],
        taxonomy_constraints: dict[str, Any],
        diversity_context: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a locked control specification via LLM."""
        logger.info("SpecAgent run started: %s / %s", leaf.get("hierarchy_id"), control_type)
        t0 = time.monotonic()
        try:
            system_prompt = (
                "You are SpecAgent. Produce a locked control specification JSON for one control. "
                "Choose exactly one who, what_action, when, where_system, why_risk, and business_unit_id. "
                "Return ONLY JSON with keys: hierarchy_id, leaf_name, selected_level_1, control_type, placement, method, who, what_action, "
                "what_detail, when, where_system, why_risk, evidence, business_unit_id. "
                "EVIDENCE QUALITY RULES: The evidence field must be a specific, audit-grade artifact description that a junior auditor "
                "could retrieve without follow-up questions. It must include three things: "
                "(1) A specific named artifact (not generic — e.g. 'wire transfer release approval log' not 'approval documentation'), "
                "(2) Who signed or approved it (use the role from who or another appropriate role), "
                "(3) Where it is retained (name the system from where_system or another system from the registry). "
                "Good example: 'GL account reconciliation report with Staff Accountant preparer sign-off and Accounting Manager reviewer sign-off, retained in the financial close platform.' "
                "Bad example: 'Reconciliation documentation.'"
            )
            user_prompt = json.dumps(
                {
                    "leaf": leaf,
                    "control_type": control_type,
                    "control_type_definition": type_definition,
                    "domain_registry": registry,
                    "control_placement_definitions": placement_defs,
                    "control_method_definitions": method_defs,
                    "taxonomy_constraints": taxonomy_constraints,
                    "diversity_context": diversity_context,
                    "constraints": [
                        "selected_level_1 must be one value from taxonomy_constraints.level_1_options",
                        "control_type must be one value from taxonomy_constraints.allowed_level_2_for_selected_level_1",
                        "business_unit_id must be one business_unit_id from diversity_context.available_business_units",
                        "Choose the business unit most naturally aligned with this control's leaf process, control type, and domain",
                        "if diversity_context.suggested_business_unit is present, use it as a preference signal but override if another BU is clearly more appropriate",
                        "placement must be one value from control_placement_definitions.placements",
                        "method must be one value from control_method_definitions.methods",
                        "who must be one role from registry.roles",
                        "where_system must be one system from registry.systems",
                        "evidence must be a specific, audit-grade artifact description inspired by registry.evidence_artifacts — include the artifact name, who signs/approves it, and which system retains it",
                    ],
                },
                indent=2,
            )

            raw = await self.call_llm(system_prompt, user_prompt)
            result = self.parse_json(raw)
            logger.info("SpecAgent run completed: %s (%.3fs)", leaf.get("hierarchy_id"), time.monotonic() - t0)
            return result
        except AgentExecutionException:
            raise
        except Exception as exc:
            logger.exception("SpecAgent run failed: %s", leaf.get("hierarchy_id"))
            raise AgentExecutionException(f"SpecAgent failed for {leaf.get('hierarchy_id')}") from exc
