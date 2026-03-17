"""Differentiation agent.

Modifies a generated control to avoid semantic duplication with
existing controls in the memory store. Preserves the locked spec
constraints while varying the narrative approach.
"""

from __future__ import annotations

from typing import Any

from controlnexus.agents.base import BaseAgent, register_agent


@register_agent
class DifferentiationAgent(BaseAgent):
    """Generates an alternative control description to avoid duplication."""

    SYSTEM_PROMPT = """You are a control documentation specialist at a large financial institution.
A generated control has been flagged as too similar to an existing control in the database.

Your task: rewrite the control description to be semantically distinct while preserving:
1. The same WHO (accountable role)
2. The same WHERE (system/platform)
3. The same control type and placement
4. The same risk coverage (WHY)

Change the WHAT (specific action) and WHEN (timing/trigger) to create a genuinely different control procedure.

Return JSON:
{
    "who": "...",
    "what": "...",
    "when": "...",
    "where": "...",
    "why": "...",
    "full_description": "..."
}"""

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Generate an alternative control description.

        Kwargs:
            control: Dict with the duplicate control fields.
            existing_control: The existing control it duplicates.
            spec: Locked specification constraints.

        Returns:
            Dict with differentiated control fields.
        """
        control = kwargs.get("control", {})
        existing = kwargs.get("existing_control", "")
        spec = kwargs.get("spec", {})

        user_prompt = (
            f"This generated control is too similar to an existing one.\n\n"
            f"GENERATED:\n{control.get('full_description', '')}\n\n"
            f"EXISTING (avoid similarity to this):\n{existing}\n\n"
            f"LOCKED SPEC CONSTRAINTS:\n{spec}\n\n"
            f"Rewrite the generated control to be semantically distinct."
        )

        if self.client is None:
            # Deterministic fallback: prepend "Additionally, " to differentiate
            desc = control.get("full_description", "")
            return {
                **control,
                "full_description": f"Additionally, {desc}",
            }

        text = await self.call_llm(self.SYSTEM_PROMPT, user_prompt)
        return self.parse_json(text)
