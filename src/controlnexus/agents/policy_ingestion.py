"""PolicyIngestionAgent — preprocessing agent for policy-first mode.

Converts a policy document (text, PDF extract, or structured YAML) into
transient ``ProcessConfig`` + ``RiskInstance`` entries that augment the
``DomainConfig`` for a single generation run. Persistence is an explicit
user action, not automatic.

Provenance is captured via ``source_policy_clause`` on ``RiskInstance`` and
``source_process_step`` on ``FinalControlRecord``.

**Current status**: Stub implementation with deterministic fallback.
Full LLM-powered extraction is a Phase 4+ deliverable.
"""

from __future__ import annotations

import logging
from typing import Any

from controlnexus.agents.base import AgentContext, BaseAgent, register_agent

logger = logging.getLogger(__name__)


@register_agent
class PolicyIngestionAgent(BaseAgent):
    """Extract processes and risks from a policy document.

    In deterministic (no-LLM) mode, returns empty augmentations.
    When ``llm_enabled=True`` and a policy text is provided, the agent
    will use LLM extraction (not yet implemented — returns empty).
    """

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="PolicyIngestionAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run policy ingestion.

        Kwargs:
            policy_text: str — raw text of the policy document.
            domain_config: dict — current DomainConfig as dict for context.
            llm_enabled: bool — whether LLM extraction is available.

        Returns:
            dict with keys:
                - ``processes``: list[dict] — ProcessConfig-compatible dicts.
                - ``risks``: list[dict] — RiskCatalogEntry-compatible dicts.
                - ``risk_instances``: list[dict] — mapping of process_id → RiskInstance dicts.
                - ``provenance``: str — source document identifier.
        """
        policy_text = kwargs.get("policy_text", "")
        llm_enabled = kwargs.get("llm_enabled", False)

        if not policy_text:
            logger.info("PolicyIngestionAgent: no policy text provided, returning empty augmentations")
            return {
                "processes": [],
                "risks": [],
                "risk_instances": [],
                "provenance": "",
            }

        if not llm_enabled or not self.client:
            logger.info(
                "PolicyIngestionAgent: LLM not available, returning empty "
                "augmentations (deterministic stub)"
            )
            return {
                "processes": [],
                "risks": [],
                "risk_instances": [],
                "provenance": "stub:no-llm",
            }

        # ── LLM extraction path (future implementation) ──────────────────
        # TODO: Implement LLM-powered extraction with structured output:
        #   1. Send policy_text + domain context to LLM
        #   2. Parse structured response into ProcessConfig + RiskInstance dicts
        #   3. Tag each RiskInstance with source_policy_clause
        #   4. Return augmentations for DomainConfig merge
        logger.info(
            "PolicyIngestionAgent: LLM extraction not yet implemented, "
            "returning empty augmentations"
        )
        return {
            "processes": [],
            "risks": [],
            "risk_instances": [],
            "provenance": "stub:llm-not-implemented",
        }
