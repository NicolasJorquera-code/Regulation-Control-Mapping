"""RiskAgent -- resolves or generates risk context for a control assignment.

Given a process and risk_id from an assignment, the RiskAgent looks up the
risk catalog entry and enriches the description. When the risk_id is missing
or set to "auto", it can generate a risk from BU+Process context.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from controlnexus.agents.base import BaseAgent, register_agent

logger = logging.getLogger(__name__)


@register_agent
class RiskAgent(BaseAgent):
    """Resolve or generate risk context for a control assignment."""

    async def execute(
        self,
        *,
        risk_id: str,
        process_id: str,
        process_name: str,
        risk_catalog: list[dict[str, Any]],
        process_risks: list[dict[str, Any]],
        registry: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve risk context via catalog lookup or LLM generation."""
        logger.info("RiskAgent run started: risk=%s, process=%s", risk_id, process_id)
        t0 = time.monotonic()

        try:
            # Look up catalog entry
            catalog_entry = None
            for entry in risk_catalog:
                if entry.get("id") == risk_id:
                    catalog_entry = entry
                    break

            # Look up risk instance in process
            risk_instance = None
            for ri in process_risks:
                if ri.get("risk_id") == risk_id:
                    risk_instance = ri
                    break

            if catalog_entry:
                # Direct resolution from catalog — no LLM needed
                result = {
                    "risk_id": risk_id,
                    "risk_name": catalog_entry.get("name", ""),
                    "risk_category": catalog_entry.get("level_1", "") or catalog_entry.get("category", ""),
                    "level_1": catalog_entry.get("level_1", ""),
                    "sub_group": catalog_entry.get("sub_group"),
                    "severity": risk_instance.get("severity", catalog_entry.get("default_severity", 3))
                    if risk_instance
                    else catalog_entry.get("default_severity", 3),
                    "multiplier": risk_instance.get("multiplier", 1.0) if risk_instance else 1.0,
                    "description": catalog_entry.get("description", ""),
                    "mitigated_by_types": risk_instance.get("mitigated_by_types", []) if risk_instance else [],
                    "rationale": risk_instance.get("rationale", "") if risk_instance else "",
                }
                elapsed = time.monotonic() - t0
                logger.info("RiskAgent resolved from catalog in %.2fs", elapsed)
                return result

            # No catalog entry found — use LLM to generate risk context
            system_prompt = (
                "You are RiskAgent. Given a process context, generate a risk description "
                "that this control should mitigate. Return ONLY JSON with keys: "
                "risk_name, risk_category, description, severity (1-5)."
            )
            user_prompt = json.dumps(
                {
                    "risk_id": risk_id,
                    "process_id": process_id,
                    "process_name": process_name,
                    "registry": registry,
                },
                indent=2,
            )
            raw = await self.call_llm(system_prompt, user_prompt)
            parsed = self.parse_json(raw)
            elapsed = time.monotonic() - t0
            logger.info("RiskAgent generated via LLM in %.2fs", elapsed)
            return {
                "risk_id": risk_id,
                "risk_name": parsed.get("risk_name", f"Risk for {process_name}"),
                "risk_category": parsed.get("risk_category", "Operational"),
                "severity": parsed.get("severity", 3),
                "multiplier": risk_instance.get("multiplier", 1.0) if risk_instance else 1.0,
                "description": parsed.get("description", ""),
                "mitigated_by_types": risk_instance.get("mitigated_by_types", []) if risk_instance else [],
                "rationale": risk_instance.get("rationale", "") if risk_instance else "",
            }

        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.warning("RiskAgent failed (%.2fs): %s", elapsed, exc)
            return {
                "risk_id": risk_id,
                "risk_name": f"Risk for {process_name}",
                "risk_category": "Operational",
                "severity": 3,
                "multiplier": 1.0,
                "description": f"Operational risk in {process_name}",
                "mitigated_by_types": [],
                "rationale": "",
            }
