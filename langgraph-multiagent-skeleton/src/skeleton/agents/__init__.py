"""
Agent layer — registry and public exports.

Import agents here so that ``@register_agent`` decorators execute and
populate ``AGENT_REGISTRY`` on first import of the package.
"""

from skeleton.agents.base import (
    AGENT_REGISTRY,
    AgentContext,
    BaseAgent,
    register_agent,
)
from skeleton.agents.planner import PlannerAgent
from skeleton.agents.researcher import ResearcherAgent
from skeleton.agents.reviewer import ReviewerAgent
from skeleton.agents.synthesizer import SynthesizerAgent

__all__ = [
    "AGENT_REGISTRY",
    "AgentContext",
    "BaseAgent",
    "PlannerAgent",
    "ResearcherAgent",
    "ReviewerAgent",
    "SynthesizerAgent",
    "register_agent",
]
