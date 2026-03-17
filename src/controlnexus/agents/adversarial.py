"""Adversarial Reviewer agent.

Red-teams a generated control: identifies weaknesses, vague language,
missing risk coverage, or specification violations. Output is used
to guide the rewrite cycle in the quality gate.
"""

from __future__ import annotations

from typing import Any

from controlnexus.agents.base import BaseAgent, register_agent


@register_agent
class AdversarialReviewer(BaseAgent):
    """Reviews a generated control from a critical perspective."""

    SYSTEM_PROMPT = """You are a senior internal audit reviewer at a large financial institution.
Your job is to critically evaluate a generated internal control description and identify weaknesses.

For each weakness found, provide:
1. The specific issue (vague language, missing risk, specification violation, etc.)
2. A concrete suggestion for improvement

Return JSON:
{
    "weaknesses": [
        {"issue": "...", "suggestion": "..."}
    ],
    "overall_assessment": "Weak" | "Needs Improvement" | "Satisfactory",
    "rewrite_guidance": "Specific instructions for improving the control"
}"""

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Review a control and identify weaknesses.

        Kwargs:
            control: Dict with the control fields (who, what, when, where, why, full_description).
            spec: Dict with the locked specification.
            standards: Standards config for reference.

        Returns:
            Dict with weaknesses, overall_assessment, and rewrite_guidance.
        """
        control = kwargs.get("control", {})
        spec = kwargs.get("spec", {})

        user_prompt = (
            f"Review this internal control for weaknesses:\n\n"
            f"WHO: {control.get('who', '')}\n"
            f"WHAT: {control.get('what', '')}\n"
            f"WHEN: {control.get('when', '')}\n"
            f"WHERE: {control.get('where', '')}\n"
            f"WHY: {control.get('why', '')}\n"
            f"FULL DESCRIPTION: {control.get('full_description', '')}\n\n"
            f"LOCKED SPEC: {spec}\n\n"
            f"Identify all weaknesses and provide rewrite guidance."
        )

        if self.client is None:
            return {
                "weaknesses": [],
                "overall_assessment": "Satisfactory",
                "rewrite_guidance": "No LLM available for adversarial review.",
            }

        text = await self.call_llm(self.SYSTEM_PROMPT, user_prompt)
        return self.parse_json(text)
