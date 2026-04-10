"""Tests for tool executor and individual tool implementations."""

from __future__ import annotations

from skeleton.core.config import DomainConfig
from skeleton.tools.implementations import build_tool_executor


def test_web_search_returns_results(sample_config):
    executor = build_tool_executor(sample_config)
    result = executor("web_search", {"query": "LangGraph"})
    assert "results" in result
    assert len(result["results"]) == 2
    assert "title" in result["results"][0]
    assert "snippet" in result["results"][0]
    assert "url" in result["results"][0]


def test_note_store(sample_config):
    executor = build_tool_executor(sample_config)
    result = executor("note_store", {"key": "test", "value": "hello"})
    assert result["stored"] is True
    assert result["key"] == "test"


def test_unknown_tool_returns_error(sample_config):
    executor = build_tool_executor(sample_config)
    result = executor("nonexistent_tool", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]


def test_executor_captures_config():
    """Executor should capture config at creation time."""
    config = DomainConfig(name="test-config")
    executor = build_tool_executor(config)
    # Should work without passing config again
    result = executor("web_search", {"query": "test"})
    assert "results" in result
