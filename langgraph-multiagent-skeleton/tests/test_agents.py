"""Tests for individual agents in deterministic (no-LLM) mode."""

from __future__ import annotations

import asyncio

import pytest

from skeleton.agents.planner import PlannerAgent
from skeleton.agents.researcher import ResearcherAgent
from skeleton.agents.reviewer import ReviewerAgent
from skeleton.agents.synthesizer import SynthesizerAgent
from skeleton.agents.base import AgentContext, AGENT_REGISTRY
from skeleton.core.config import DomainConfig


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_agent_registry_populated():
    """All four agents should be registered via @register_agent."""
    assert "PlannerAgent" in AGENT_REGISTRY
    assert "ResearcherAgent" in AGENT_REGISTRY
    assert "SynthesizerAgent" in AGENT_REGISTRY
    assert "ReviewerAgent" in AGENT_REGISTRY


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

def test_planner_deterministic(no_llm_context, sample_config):
    agent = PlannerAgent(no_llm_context)
    result = asyncio.get_event_loop().run_until_complete(
        agent.execute(question="What is LangGraph?", config=sample_config)
    )
    subs = result["sub_questions"]
    assert len(subs) > 0
    assert all("question" in sq for sq in subs)


# ---------------------------------------------------------------------------
# ResearcherAgent
# ---------------------------------------------------------------------------

def test_researcher_deterministic(no_llm_context, sample_config, tool_executor):
    agent = ResearcherAgent(no_llm_context)
    result = asyncio.get_event_loop().run_until_complete(
        agent.execute(
            question="What is LangGraph?",
            config=sample_config,
            tool_executor=tool_executor,
        )
    )
    assert "answer" in result
    assert "sources" in result
    assert len(result["sources"]) > 0


# ---------------------------------------------------------------------------
# SynthesizerAgent
# ---------------------------------------------------------------------------

def test_synthesizer_deterministic(no_llm_context, sample_config):
    findings = [
        {"sub_question": "What is X?", "answer": "X is a thing.", "sources": ["https://example.com"]},
        {"sub_question": "Why is X useful?", "answer": "X helps with Y.", "sources": ["https://example.org"]},
    ]
    agent = SynthesizerAgent(no_llm_context)
    result = asyncio.get_event_loop().run_until_complete(
        agent.execute(question="Tell me about X", findings=findings, config=sample_config)
    )
    assert "text" in result
    assert result["word_count"] > 0
    assert isinstance(result["sources_used"], list)


# ---------------------------------------------------------------------------
# ReviewerAgent
# ---------------------------------------------------------------------------

def test_reviewer_deterministic_passes(no_llm_context, sample_config):
    """A summary within word-count bounds should pass."""
    long_enough = " ".join(["word"] * 70)
    agent = ReviewerAgent(no_llm_context)
    result = asyncio.get_event_loop().run_until_complete(
        agent.execute(
            question="Q",
            summary_text=long_enough,
            config=sample_config,
        )
    )
    assert result["passed"] is True
    assert result["issues"] == []


def test_reviewer_deterministic_fails_short(no_llm_context, sample_config):
    """A very short summary should fail the word-count check."""
    agent = ReviewerAgent(no_llm_context)
    result = asyncio.get_event_loop().run_until_complete(
        agent.execute(
            question="Q",
            summary_text="Too short.",
            config=sample_config,
        )
    )
    assert result["passed"] is False
    assert len(result["issues"]) > 0
