"""NarrativeAgent -- converts a locked spec into 5W prose.

Preserves locked spec values for who and where_system exactly while
generating a 30-80 word full_description narrative.
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
class NarrativeAgent(BaseAgent):
    """Convert a locked control specification into 5W narrative prose."""

    async def execute(
        self,
        *,
        locked_spec: dict[str, Any],
        standards: dict[str, Any],
        phrase_bank_cfg: dict[str, Any],
        exemplars: list[dict[str, Any]],
        regulatory_context: list[str],
        retry_appendix: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convert a locked specification into 5W narrative prose via LLM."""
        hierarchy_id = locked_spec.get("hierarchy_id", "unknown")
        logger.info("NarrativeAgent run started: %s", hierarchy_id)
        t0 = time.monotonic()
        try:
            system_prompt = (
                "You are NarrativeAgent. Convert the locked control specification into 5W prose. "
                "You must preserve locked spec values for who and where_system exactly in output fields. "
                "Return ONLY JSON with keys: who, what, when, where, why, full_description."
            )

            user_payload = {
                "locked_spec": locked_spec,
                "five_w_standards": standards,
                "phrase_bank": phrase_bank_cfg,
                "exemplars": exemplars,
                "regulatory_context": regulatory_context,
                "constraints": [
                    "Use exactly one primary action in WHAT.",
                    "WHEN must be specific and avoid vague terms.",
                    "Word count for full_description must be between 30 and 80 words.",
                    "Do not change locked spec values for who and where_system.",
                ],
            }
            user_prompt = json.dumps(user_payload, indent=2)
            if retry_appendix:
                user_prompt += "\n\n" + retry_appendix

            raw = await self.call_llm(system_prompt, user_prompt)
            result = self.parse_json(raw)
            logger.info("NarrativeAgent run completed: %s (%.3fs)", hierarchy_id, time.monotonic() - t0)
            return result
        except AgentExecutionException:
            raise
        except Exception as exc:
            logger.exception("NarrativeAgent run failed: %s", hierarchy_id)
            raise AgentExecutionException(f"NarrativeAgent failed for {hierarchy_id}") from exc
