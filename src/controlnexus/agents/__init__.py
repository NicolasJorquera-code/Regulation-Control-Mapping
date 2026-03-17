"""ControlNexus agent pipeline."""

from controlnexus.agents.adversarial import AdversarialReviewer
from controlnexus.agents.base import AGENT_REGISTRY, AgentContext, BaseAgent, register_agent
from controlnexus.agents.differentiator import DifferentiationAgent
from controlnexus.agents.enricher import EnricherAgent
from controlnexus.agents.narrative import NarrativeAgent
from controlnexus.agents.spec import SpecAgent

__all__ = [
    "AGENT_REGISTRY",
    "AdversarialReviewer",
    "AgentContext",
    "BaseAgent",
    "DifferentiationAgent",
    "EnricherAgent",
    "NarrativeAgent",
    "SpecAgent",
    "register_agent",
]
