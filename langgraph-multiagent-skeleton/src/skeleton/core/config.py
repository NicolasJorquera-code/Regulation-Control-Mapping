"""
Configuration loader — YAML → Pydantic models.

Pattern: Separate *runtime* settings (``AppConfig``: model, temperature,
concurrency) from *domain knowledge* (``DomainConfig``: quality criteria,
topic areas, word-count rules).  Both are Pydantic models so they get
free validation, serialization, and IDE auto-complete.

The ``load_config`` function reads a YAML file and returns a validated
``DomainConfig``.  ``AppConfig`` is built from environment variables or
explicit keyword arguments — it never lives in YAML because it varies
per deployment, not per domain.

# CUSTOMIZE: Add fields to ``DomainConfig`` for your domain knowledge.
# CUSTOMIZE: Add fields to ``AppConfig`` for your runtime tunables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Runtime settings (per-deployment, not per-domain)
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Runtime settings that vary between deployments.

    # CUSTOMIZE: Add tunables like ``max_parallel_agents``, ``dry_run_limit``, etc.
    """

    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120


# ---------------------------------------------------------------------------
# Domain knowledge (per-domain, lives in YAML)
# ---------------------------------------------------------------------------

class DomainConfig(BaseModel):
    """Single source of truth for domain-specific knowledge.

    Every agent and tool receives a ``DomainConfig`` (or a slice of it)
    rather than reading raw YAML themselves.  This guarantees that the
    entire pipeline shares one validated view of domain rules.

    # CUSTOMIZE: Replace these fields with your domain's concepts.
    """

    name: str = "default"
    description: str = ""

    # Research-specific settings (replace for your domain)
    max_sub_questions: int = Field(default=5, ge=1, le=20)
    summary_min_words: int = Field(default=50, ge=10)
    summary_max_words: int = Field(default=300, ge=50)
    quality_criteria: list[str] = Field(default_factory=lambda: [
        "Claims are supported by cited sources",
        "No internal contradictions between findings",
    ])
    topic_areas: list[str] = Field(default_factory=lambda: [
        "technology", "science", "business",
    ])


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


def load_config(path: str | Path) -> DomainConfig:
    """Load and validate a ``DomainConfig`` from a YAML file.

    Raises ``ValueError`` on parse errors or validation failures.
    """
    raw = _read_yaml(Path(path))
    return DomainConfig(**raw)


def default_config_path() -> Path:
    """Return the default config path (``config/default.yaml`` relative to project root)."""
    return Path(__file__).resolve().parents[3] / "config" / "default.yaml"
