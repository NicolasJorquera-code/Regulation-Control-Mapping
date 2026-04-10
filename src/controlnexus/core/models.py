"""Pydantic data models for ControlNexus.

Defines all configuration and domain models used throughout the pipeline,
including run configs, section profiles, taxonomy, and business units.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Section profile models
# ---------------------------------------------------------------------------


class RiskProfile(BaseModel):
    """Risk scoring for an APQC section."""

    model_config = ConfigDict(frozen=True)

    inherent_risk: int
    regulatory_intensity: int
    control_density: int
    multiplier: float
    rationale: str


class AffinityMatrix(BaseModel):
    """Control type affinity buckets for a section."""

    HIGH: list[str] = Field(default_factory=list)
    MEDIUM: list[str] = Field(default_factory=list)
    LOW: list[str] = Field(default_factory=list)
    NONE: list[str] = Field(default_factory=list)


class DomainRegistry(BaseModel):
    """Domain-specific vocabulary for control generation."""

    roles: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    data_objects: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    event_triggers: list[str] = Field(default_factory=list)
    regulatory_frameworks: list[str] = Field(default_factory=list)


class ExemplarControl(BaseModel):
    """Sample control used as a style reference by agents."""

    model_config = ConfigDict(frozen=True)

    control_type: str
    placement: str
    method: str
    full_description: str
    word_count: int
    quality_rating: str


class SectionProfile(BaseModel):
    """Complete profile for one APQC section."""

    model_config = ConfigDict(extra="ignore")

    section_id: str
    domain: str
    risk_profile: RiskProfile
    affinity: AffinityMatrix = Field(default_factory=AffinityMatrix)
    registry: DomainRegistry
    exemplars: list[ExemplarControl] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run configuration models
# ---------------------------------------------------------------------------


class ScopeConfig(BaseModel):
    """Which APQC sections and optional subsection to process."""

    sections: list[str]
    subsection: str | None = None

    @field_validator("sections")
    @classmethod
    def sections_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one section must be provided in scope.sections")
        if any(not str(section).strip() for section in value):
            raise ValueError("scope.sections cannot contain empty values")
        return value


class InputConfig(BaseModel):
    """Input file configuration (APQC template path)."""

    apqc_template: Path = Path("data/APQC_Template.xlsx")


class SizingConfig(BaseModel):
    """Target sizing strategy for the run."""

    model_config = ConfigDict(extra="ignore")

    target_count: int | None = None
    dry_run_limit: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, data: Any) -> Any:
        """Map legacy sizing fields to the new schema."""
        if isinstance(data, dict):
            if "target_override" in data and "target_count" not in data:
                data["target_count"] = data.pop("target_override")
            data.pop("mode", None)
            data.pop("controls_per_type", None)
            data.pop("target_override", None)
        return data

    @field_validator("target_count", "dry_run_limit")
    @classmethod
    def positive_numeric_values(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Numeric sizing values must be positive integers")
        return value


class CheckpointConfig(BaseModel):
    """Checkpoint / resume configuration (reserved for future use)."""

    enabled: bool = True
    resume: bool = True
    directory: Path = Path("./checkpoints")


class TransportConfig(BaseModel):
    """HTTP transport settings for LLM API calls."""

    timeout_seconds: int = 120
    max_retries: int = 3
    temperature: float = 0.2
    max_tokens: int = 1400


class ConcurrencyConfig(BaseModel):
    """Parallelism configuration for the pipeline."""

    max_parallel_sections: int = 1
    max_parallel_controls: int = 1


class OutputConfig(BaseModel):
    """Output directory, format, and audit-trail settings."""

    directory: Path = Path("./output")
    formats: list[Literal["excel", "jsonl"]] = Field(default_factory=lambda: ["excel"])
    include_audit_trail: bool = True


class RunConfig(BaseModel):
    """Top-level configuration for a single ControlNexus run."""

    run_id: str
    description: str | None = None
    input: InputConfig = Field(default_factory=InputConfig)
    scope: ScopeConfig
    sizing: SizingConfig
    checkpoint: CheckpointConfig
    transport: TransportConfig
    concurrency: ConcurrencyConfig
    output: OutputConfig
    traced_leaves: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Taxonomy models
# ---------------------------------------------------------------------------


class TaxonomyItem(BaseModel):
    """A control type definition (name + description)."""

    model_config = ConfigDict(frozen=True)

    control_type: str
    definition: str


class BusinessUnitProfile(BaseModel):
    """Metadata for a business unit used in control allocation."""

    business_unit_id: str
    name: str
    description: str
    primary_sections: list[str] = Field(default_factory=list)
    key_control_types: list[str] = Field(default_factory=list)
    regulatory_exposure: list[str] = Field(default_factory=list)


class TaxonomyCatalog(BaseModel):
    """Complete taxonomy catalog: control type definitions and business units."""

    control_types: list[TaxonomyItem] = Field(default_factory=list)
    business_units: list[BusinessUnitProfile] = Field(default_factory=list)
