"""
Configuration loader — YAML → Pydantic PipelineConfig.

Separates domain knowledge (config/default.yaml) from runtime settings
(environment variables). Includes risk taxonomy loader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pipeline configuration (domain knowledge from YAML)
# ---------------------------------------------------------------------------

class CoverageThresholds(BaseModel):
    semantic_match_min_confidence: float = 0.6
    frequency_tolerance: int = 1


class PipelineConfig(BaseModel):
    """Single source of truth for all pipeline settings."""

    name: str = "reg-obligation-mapper"
    description: str = ""

    # Ingest
    active_statuses: list[str] = Field(default_factory=lambda: ["In Force", "Pending"])
    control_file_pattern: str = "section_*__controls.xlsx"

    # Classification
    obligation_categories: list[str] = Field(default_factory=lambda: [
        "Attestation", "Documentation", "Controls", "General Awareness", "Not Assigned",
    ])
    relationship_types: list[str] = Field(default_factory=lambda: [
        "Requires Existence", "Constrains Execution", "Requires Evidence", "Sets Frequency", "N/A",
    ])
    criticality_tiers: list[str] = Field(default_factory=lambda: ["High", "Medium", "Low"])

    # Actionable categories
    actionable_categories: list[str] = Field(default_factory=lambda: [
        "Controls", "Documentation", "Attestation",
    ])

    # APQC mapping
    apqc_mapping_depth: int = Field(default=3, ge=1, le=5)
    max_apqc_mappings_per_obligation: int = Field(default=5, ge=1)

    # Coverage
    coverage_thresholds: CoverageThresholds = Field(default_factory=CoverageThresholds)

    # Risk
    min_risks_per_gap: int = Field(default=1, ge=1)
    max_risks_per_gap: int = Field(default=3, ge=1)
    impact_scale: dict[int, dict[str, str]] = Field(default_factory=dict)
    frequency_scale: dict[int, dict[str, str]] = Field(default_factory=dict)

    # Output
    risk_id_prefix: str = "RISK"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


def load_config(path: str | Path) -> PipelineConfig:
    """Load and validate a PipelineConfig from a YAML file."""
    raw = _read_yaml(Path(path))
    return PipelineConfig(**raw)


def load_risk_taxonomy(path: str | Path) -> dict[str, Any]:
    """Load the risk taxonomy JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def default_config_path() -> Path:
    """Return config/default.yaml relative to project root."""
    return Path(__file__).resolve().parents[3] / "config" / "default.yaml"


def default_taxonomy_path() -> Path:
    """Return config/risk_taxonomy.json relative to project root."""
    return Path(__file__).resolve().parents[3] / "config" / "risk_taxonomy.json"
