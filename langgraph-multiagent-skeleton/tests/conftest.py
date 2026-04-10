"""Test fixtures — mock transport, sample config, shared helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.agents.base import AgentContext
from skeleton.core.config import DomainConfig, load_config
from skeleton.tools.implementations import build_tool_executor


@pytest.fixture()
def sample_config() -> DomainConfig:
    """Load the default config shipped with the skeleton."""
    config_path = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
    return load_config(config_path)


@pytest.fixture()
def no_llm_context() -> AgentContext:
    """AgentContext with no LLM client (deterministic mode)."""
    return AgentContext(client=None)


@pytest.fixture()
def tool_executor(sample_config: DomainConfig):
    """Tool executor closure backed by the sample config."""
    return build_tool_executor(sample_config)
