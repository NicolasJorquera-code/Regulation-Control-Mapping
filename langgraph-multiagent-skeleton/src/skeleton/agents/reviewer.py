"""
ReviewerAgent — critiques a summary against quality criteria.

Pattern: The reviewer acts as a "quality gate" that can trigger a
retry loop.  When ``passed`` is False, the graph routes back to the
SynthesizerAgent with the ``issues`` as feedback.  This agent-retry
pattern is one of the key architectural patterns worth preserving.

# CUSTOMIZE: Replace quality_criteria with your domain's rubric.
"""

from __future__ import annotations

from typing import Any

from skeleton.agents.base import BaseAgent, register_agent
from skeleton.core.config import DomainConfig


SYSTEM_PROMPT = """\
You are a quality reviewer. Evaluate the following research summary against
these criteria:

{criteria_list}

Return a JSON object:
{{
  "passed": true/false,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["suggestion 1"]
}}

Set "passed" to true only if ALL criteria are met. Be specific about issues.
"""

# CUSTOMIZE: Adjust the prompt and criteria for your domain.

USER_PROMPT = """\
Original question: {question}

Summary to review:
{summary}

Evaluate against the quality criteria.
"""


@register_agent
class ReviewerAgent(BaseAgent):
    """Critiques a summary against configurable quality criteria.

    LLM mode: Sends summary + criteria to LLM, parses pass/fail + issues.
    Deterministic fallback: Always passes with no issues (for testing).
    """

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        question: str = kwargs["question"]
        summary_text: str = kwargs["summary_text"]
        config: DomainConfig = kwargs["config"]

        # --- Deterministic fallback ---
        if self.context.client is None:
            return self._deterministic(summary_text, config)

        # --- LLM path ---
        criteria_list = "\n".join(f"- {c}" for c in config.quality_criteria)
        system = SYSTEM_PROMPT.format(criteria_list=criteria_list)
        user = USER_PROMPT.format(question=question, summary=summary_text)
        raw = await self.call_llm(system, user)

        parsed = self.parse_json(raw)
        return {
            "passed": bool(parsed.get("passed", True)),
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
        }

    @staticmethod
    def _deterministic(summary_text: str, config: DomainConfig) -> dict[str, Any]:
        """Deterministic fallback — basic rule-based checks."""
        issues: list[str] = []
        suggestions: list[str] = []

        word_count = len(summary_text.split())
        if word_count < config.summary_min_words:
            issues.append(
                f"Summary too short ({word_count} words, minimum {config.summary_min_words})"
            )
            suggestions.append("Expand the summary with more detail from the findings.")

        if word_count > config.summary_max_words:
            issues.append(
                f"Summary too long ({word_count} words, maximum {config.summary_max_words})"
            )
            suggestions.append("Condense the summary while retaining key points.")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
        }
