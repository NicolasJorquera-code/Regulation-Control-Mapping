"""
PlannerAgent — decomposes a research question into sub-questions.

# CUSTOMIZE: Replace the prompt template and output parsing with your
# domain's decomposition logic.
"""

from __future__ import annotations

import json
from typing import Any

from skeleton.agents.base import BaseAgent, register_agent
from skeleton.core.config import DomainConfig


SYSTEM_PROMPT = """\
You are a research planner. Given a user's research question, decompose it
into {max_sub_questions} or fewer focused sub-questions that, when answered
individually, will provide comprehensive coverage of the original question.

Return a JSON array of objects, each with "question" and "topic" keys.
Example:
[
  {{"question": "What is X?", "topic": "technology"}},
  {{"question": "How does Y compare to Z?", "topic": "business"}}
]

Available topic areas: {topics}
"""

# CUSTOMIZE: Change this prompt to match your domain's decomposition strategy.

USER_PROMPT = "Research question: {question}"


@register_agent
class PlannerAgent(BaseAgent):
    """Decomposes a research question into sub-questions.

    LLM mode: Sends the question + config to the LLM, parses JSON array.
    Deterministic fallback: Generates a single sub-question echoing the
    original question (useful for testing without API keys).
    """

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        question: str = kwargs["question"]
        config: DomainConfig = kwargs["config"]

        # --- Deterministic fallback (no LLM) ---
        if self.context.client is None:
            return self._deterministic(question, config)

        # --- LLM path ---
        system = SYSTEM_PROMPT.format(
            max_sub_questions=config.max_sub_questions,
            topics=", ".join(config.topic_areas),
        )
        user = USER_PROMPT.format(question=question)
        raw = await self.call_llm(system, user)

        parsed = self._parse_sub_questions(raw, config)
        return {"sub_questions": parsed}

    # ---- helpers ----

    def _parse_sub_questions(
        self, raw: str, config: DomainConfig
    ) -> list[dict[str, str]]:
        """Parse LLM output into a list of sub-question dicts."""
        try:
            # Try parsing as JSON array
            data = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            if isinstance(data, list):
                return [
                    {"question": item.get("question", ""), "topic": item.get("topic", "")}
                    for item in data[:config.max_sub_questions]
                ]
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: try extracting from BaseAgent.parse_json
        obj = self.parse_json(raw)
        if "sub_questions" in obj:
            return obj["sub_questions"][:config.max_sub_questions]

        # Last resort: treat the whole response as one question
        return [{"question": raw.strip()[:200], "topic": ""}]

    @staticmethod
    def _deterministic(question: str, config: DomainConfig) -> dict[str, Any]:
        """Deterministic fallback — produces one sub-question per topic area."""
        subs = [
            {"question": f"What are the key {topic} aspects of: {question}?", "topic": topic}
            for topic in config.topic_areas[:config.max_sub_questions]
        ]
        return {"sub_questions": subs}
