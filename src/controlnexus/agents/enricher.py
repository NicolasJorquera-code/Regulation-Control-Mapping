"""EnricherAgent -- refines control prose and assigns quality rating.

Takes a validated control with its narrative and produces a refined
description along with a quality rating (Strong through Weak).
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
class EnricherAgent(BaseAgent):
    """Refine control narrative prose and assign a quality rating."""

    async def execute(
        self,
        *,
        validated_control: dict[str, Any],
        rating_criteria_cfg: dict[str, Any],
        nearest_neighbors: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Refine control prose and assign a quality rating via LLM."""
        hierarchy_id = validated_control.get("hierarchy_id", "unknown")
        logger.info("EnricherAgent run started: %s", hierarchy_id)
        t0 = time.monotonic()
        try:
            system_prompt = (
                "You are EnricherAgent. Refine control prose slightly for clarity while preserving meaning, "
                "then assign one quality rating from: Strong, Effective, Satisfactory, Needs Improvement, Weak. "
                "Return ONLY JSON with keys: refined_full_description, quality_rating, rationale."
            )
            user_prompt = json.dumps(
                {
                    "validated_control": validated_control,
                    "rating_criteria": rating_criteria_cfg,
                    "nearest_neighbors": nearest_neighbors,
                    "constraints": [
                        "Keep refined description between 30 and 80 words",
                        "Do not change control facts (who/what/when/where/why)",
                        "Rating must be exactly one allowed label",
                    ],
                },
                indent=2,
            )

            raw = await self.call_llm(system_prompt, user_prompt)
            result = self.parse_json(raw)
            logger.info(
                "EnricherAgent run completed: %s (%s, %.3fs)",
                hierarchy_id, result.get("quality_rating"), time.monotonic() - t0,
            )
            return result
        except AgentExecutionException:
            raise
        except Exception as exc:
            logger.exception("EnricherAgent run failed: %s", hierarchy_id)
            raise AgentExecutionException(
                f"EnricherAgent failed for {hierarchy_id}"
            ) from exc
