"""
SynthesizerAgent — merges multiple findings into a cohesive summary.

# CUSTOMIZE: Replace the prompt with your domain's synthesis strategy.
"""

from __future__ import annotations

from typing import Any

from skeleton.agents.base import BaseAgent, register_agent
from skeleton.core.config import DomainConfig


SYSTEM_PROMPT = """\
You are a research synthesizer. You will receive a collection of research
findings from individual sub-questions. Combine them into a single cohesive
summary that:

1. Addresses the original research question comprehensively
2. Is between {min_words} and {max_words} words
3. Cites sources where appropriate
4. Resolves contradictions between findings (if any)

Return a JSON object:
{{
  "text": "Your synthesized summary here",
  "sources_used": ["url1", "url2"]
}}
"""

# CUSTOMIZE: Adjust for your domain.

USER_PROMPT = """\
Original question: {question}

Findings:
{findings_text}

Synthesize these into a comprehensive summary.
"""


@register_agent
class SynthesizerAgent(BaseAgent):
    """Merges findings into a cohesive summary.

    LLM mode: Sends all findings to the LLM with synthesis instructions.
    Deterministic fallback: Concatenates finding answers with headers.
    """

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        question: str = kwargs["question"]
        findings: list[dict[str, Any]] = kwargs["findings"]
        config: DomainConfig = kwargs["config"]

        # --- Deterministic fallback ---
        if self.context.client is None:
            return self._deterministic(question, findings, config)

        # --- LLM path ---
        findings_text = self._format_findings(findings)
        system = SYSTEM_PROMPT.format(
            min_words=config.summary_min_words,
            max_words=config.summary_max_words,
        )
        user = USER_PROMPT.format(question=question, findings_text=findings_text)
        raw = await self.call_llm(system, user)

        parsed = self.parse_json(raw)
        text = parsed.get("text", raw)
        sources = parsed.get("sources_used", [])

        return {
            "text": text,
            "word_count": len(text.split()),
            "sources_used": sources,
        }

    # ---- helpers ----

    @staticmethod
    def _format_findings(findings: list[dict[str, Any]]) -> str:
        parts = []
        for i, f in enumerate(findings, 1):
            sq = f.get("sub_question", f"Finding {i}")
            ans = f.get("answer", "No answer")
            sources = ", ".join(f.get("sources", []))
            parts.append(f"--- Finding {i}: {sq} ---\n{ans}\nSources: {sources}")
        return "\n\n".join(parts)

    @staticmethod
    def _deterministic(
        question: str,
        findings: list[dict[str, Any]],
        config: DomainConfig,
    ) -> dict[str, Any]:
        """Deterministic fallback — concatenates findings."""
        all_sources: list[str] = []
        parts = [f"Research summary for: {question}\n"]
        for i, f in enumerate(findings, 1):
            parts.append(f"{i}. {f.get('answer', 'No answer available.')}")
            all_sources.extend(f.get("sources", []))

        text = "\n".join(parts)
        return {
            "text": text,
            "word_count": len(text.split()),
            "sources_used": list(dict.fromkeys(all_sources)),  # dedupe preserving order
        }
