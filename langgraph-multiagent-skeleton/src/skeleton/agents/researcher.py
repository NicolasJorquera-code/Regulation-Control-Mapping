"""
ResearcherAgent — answers one sub-question using search tools.

This agent demonstrates the tool-calling pattern: it receives a
tool_executor closure and tool schemas, and uses
``call_llm_with_tools()`` to let the LLM decide when to search.

# CUSTOMIZE: Replace the prompt and tool set with your domain's
# research strategy.
"""

from __future__ import annotations

from typing import Any, Callable

from skeleton.agents.base import BaseAgent, register_agent
from skeleton.core.config import DomainConfig
from skeleton.tools.schemas import ALL_TOOL_SCHEMAS


SYSTEM_PROMPT = """\
You are a research assistant. Answer the given sub-question thoroughly and
accurately. You have access to a web_search tool — use it to find relevant
information before composing your answer.

After gathering information, respond with a JSON object:
{{
  "answer": "Your comprehensive answer here",
  "sources": ["url1", "url2"],
  "confidence": 0.85
}}

Be specific, cite your sources, and indicate your confidence (0.0-1.0).
"""

# CUSTOMIZE: Adjust this prompt for your domain.

USER_PROMPT = "Sub-question: {question}"


@register_agent
class ResearcherAgent(BaseAgent):
    """Answers one sub-question using search tools.

    LLM mode: Uses ``call_llm_with_tools()`` for multi-round tool calling,
    then parses the final JSON response.
    Deterministic fallback: Returns a placeholder finding.
    """

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        question: str = kwargs["question"]
        config: DomainConfig = kwargs["config"]
        tool_executor: Callable = kwargs["tool_executor"]

        # --- Deterministic fallback ---
        if self.context.client is None:
            return self._deterministic(question, tool_executor)

        # --- LLM path with tools ---
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT.format(question=question)},
        ]

        final_msg = await self.call_llm_with_tools(
            messages=messages,
            tools=ALL_TOOL_SCHEMAS,
            tool_executor=tool_executor,
            max_tool_rounds=3,
        )

        text = final_msg.get("content", "")
        parsed = self.parse_json(text)

        return {
            "sub_question": question,
            "answer": parsed.get("answer", text),
            "sources": parsed.get("sources", []),
            "confidence": float(parsed.get("confidence", 0.5)),
        }

    @staticmethod
    def _deterministic(
        question: str, tool_executor: Callable
    ) -> dict[str, Any]:
        """Deterministic fallback — calls the search tool directly."""
        search_result = tool_executor("web_search", {"query": question})
        results = search_result.get("results", [])

        snippets = [r.get("snippet", "") for r in results]
        urls = [r.get("url", "") for r in results]
        answer = " ".join(snippets) if snippets else f"Deterministic answer for: {question}"

        return {
            "sub_question": question,
            "answer": answer,
            "sources": urls,
            "confidence": 0.3,
        }
