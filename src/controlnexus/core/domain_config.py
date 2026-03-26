"""DomainConfig — single source of truth for an organization's control domain.

Consolidates taxonomy, section profiles, placement/methods, standards, and
frequency rules into one validated Pydantic model loaded from a single YAML.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


# ── Inner models ──────────────────────────────────────────────────────────────


class FrequencyTier(BaseModel):
    """One frequency level (e.g., Daily, Weekly, Monthly)."""

    label: str
    rank: int
    keywords: list[str]


class ControlTypeConfig(BaseModel):
    """One control type in the taxonomy."""

    name: str
    definition: str
    code: str = ""
    min_frequency_tier: str | None = None
    placement_categories: list[str] = Field(default_factory=list)
    evidence_criteria: list[str] = Field(default_factory=list)


class BusinessUnitConfig(BaseModel):
    """One business unit."""

    id: str
    name: str
    description: str = ""
    primary_sections: list[str] = Field(default_factory=list)
    key_control_types: list[str] = Field(default_factory=list)
    regulatory_exposure: list[str] = Field(default_factory=list)


class AffinityConfig(BaseModel):
    """Control type affinity buckets for a section."""

    HIGH: list[str] = Field(default_factory=list)
    MEDIUM: list[str] = Field(default_factory=list)
    LOW: list[str] = Field(default_factory=list)
    NONE: list[str] = Field(default_factory=list)


class RegistryConfig(BaseModel):
    """Domain-specific vocabulary for one process area.

    Extra keys are allowed so orgs can add custom fields.
    """

    model_config = {"extra": "allow"}

    roles: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    data_objects: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    event_triggers: list[str] = Field(default_factory=list)
    regulatory_frameworks: list[str] = Field(default_factory=list)


class ExemplarConfig(BaseModel):
    """A sample control used as a style reference."""

    control_type: str
    placement: str
    method: str
    full_description: str
    word_count: int = 0
    quality_rating: str = "Effective"


class RiskProfileConfig(BaseModel):
    """Risk scoring for a process area."""

    inherent_risk: int = 3
    regulatory_intensity: int = 3
    control_density: int = 3
    multiplier: float = 1.0
    rationale: str = ""


class ProcessAreaConfig(BaseModel):
    """One process area / section."""

    id: str
    name: str
    domain: str = ""
    risk_profile: RiskProfileConfig = Field(default_factory=RiskProfileConfig)
    affinity: AffinityConfig = Field(default_factory=AffinityConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    exemplars: list[ExemplarConfig] = Field(default_factory=list)


class NarrativeField(BaseModel):
    """One field in the narrative output schema."""

    name: str
    definition: str = ""
    required: bool = True


class NarrativeConstraints(BaseModel):
    """Rules for the narrative agent's output."""

    fields: list[NarrativeField] = Field(
        default_factory=lambda: [
            NarrativeField(
                name="who",
                definition="The specific role responsible for performing the control",
            ),
            NarrativeField(
                name="what",
                definition="The specific action performed",
            ),
            NarrativeField(
                name="when",
                definition="The timing or trigger for the control",
            ),
            NarrativeField(
                name="where",
                definition="The system or location where the control is performed",
            ),
            NarrativeField(
                name="why",
                definition="The risk or objective the control addresses",
            ),
            NarrativeField(
                name="full_description",
                definition="Prose narrative incorporating all fields",
            ),
        ]
    )
    word_count_min: int = 30
    word_count_max: int = 80


class PlacementConfig(BaseModel):
    """One placement category."""

    name: str
    description: str = ""


class MethodConfig(BaseModel):
    """One control method."""

    name: str
    description: str = ""


# ── Top-level model ───────────────────────────────────────────────────────────


class DomainConfig(BaseModel):
    """The single source of truth for an organization's control domain.

    Everything the pipeline needs to know about control types, business units,
    process areas, placements, methods, frequencies, and narrative structure
    is defined here.
    """

    name: str = "default"
    description: str = ""

    control_types: list[ControlTypeConfig] = Field(min_length=1)
    business_units: list[BusinessUnitConfig] = Field(default_factory=list)
    process_areas: list[ProcessAreaConfig] = Field(default_factory=list)

    placements: list[PlacementConfig] = Field(
        default_factory=lambda: [
            PlacementConfig(name="Preventive"),
            PlacementConfig(name="Detective"),
            PlacementConfig(name="Contingency Planning"),
        ]
    )
    methods: list[MethodConfig] = Field(
        default_factory=lambda: [
            MethodConfig(name="Automated"),
            MethodConfig(name="Manual"),
            MethodConfig(name="Automated with Manual Component"),
        ]
    )

    frequency_tiers: list[FrequencyTier] = Field(
        default_factory=lambda: [
            FrequencyTier(
                label="Daily",
                rank=1,
                keywords=["daily", "every day", "each day", "per day", "day-end", "day end", "end of day", "eod"],
            ),
            FrequencyTier(
                label="Weekly",
                rank=2,
                keywords=["weekly", "every week", "each week", "per week", "biweekly", "bi-weekly", "fortnight"],
            ),
            FrequencyTier(
                label="Monthly",
                rank=3,
                keywords=[
                    "monthly",
                    "every month",
                    "each month",
                    "per month",
                    "month-end",
                    "month end",
                    "eom",
                    "semi-monthly",
                    "semimonthly",
                ],
            ),
            FrequencyTier(
                label="Quarterly",
                rank=4,
                keywords=[
                    "quarterly",
                    "every quarter",
                    "each quarter",
                    "per quarter",
                    "qtr",
                    "quarter-end",
                    "quarter end",
                ],
            ),
            FrequencyTier(
                label="Semi-Annual",
                rank=5,
                keywords=["semi-annual", "semi annual", "semiannual", "bi-annual", "biannual", "twice a year"],
            ),
            FrequencyTier(
                label="Annual",
                rank=6,
                keywords=["annual", "annually", "yearly", "once a year", "each year", "per year"],
            ),
        ]
    )

    narrative: NarrativeConstraints = Field(default_factory=NarrativeConstraints)

    quality_ratings: list[str] = Field(
        default_factory=lambda: ["Strong", "Effective", "Satisfactory", "Needs Improvement"]
    )

    # ── Cross-reference validation ────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "DomainConfig":
        known_types = {ct.name for ct in self.control_types}
        known_sections = {pa.id for pa in self.process_areas}
        known_placements = {p.name for p in self.placements}
        known_freq_tiers = {ft.label for ft in self.frequency_tiers}
        errors: list[str] = []

        for bu in self.business_units:
            for ct in bu.key_control_types:
                if ct not in known_types:
                    errors.append(f"BU '{bu.id}' references unknown control type: '{ct}'")
            for sec in bu.primary_sections:
                if known_sections and sec not in known_sections:
                    errors.append(f"BU '{bu.id}' references unknown section: '{sec}'")

        for ct in self.control_types:
            for pc in ct.placement_categories:
                if pc not in known_placements:
                    errors.append(f"Control type '{ct.name}' references unknown placement: '{pc}'")
            if ct.min_frequency_tier and ct.min_frequency_tier not in known_freq_tiers:
                errors.append(f"Control type '{ct.name}' references unknown frequency tier: '{ct.min_frequency_tier}'")

        for pa in self.process_areas:
            for level in ("HIGH", "MEDIUM", "LOW", "NONE"):
                for type_name in getattr(pa.affinity, level, []):
                    if type_name not in known_types:
                        errors.append(f"Section '{pa.id}' affinity {level} references unknown type: '{type_name}'")

        if errors:
            raise ValueError("DomainConfig cross-reference errors:\n  - " + "\n  - ".join(errors))
        return self

    # ── Computed properties ───────────────────────────────────────────────

    def type_code_map(self) -> dict[str, str]:
        """Build control type -> 3-letter code mapping.

        Uses the ``code`` field from config, or auto-generates from consonants.
        """
        result: dict[str, str] = {}
        for ct in self.control_types:
            if ct.code:
                result[ct.name] = ct.code
            else:
                consonants = re.sub(r"[aeiouAEIOU\s\-,]", "", ct.name)
                result[ct.name] = consonants[:3].upper() or "UNK"
        return result

    def frequency_tier_rank(self, label: str) -> int | None:
        """Get the rank for a frequency tier label, or None if unknown."""
        for ft in self.frequency_tiers:
            if ft.label == label:
                return ft.rank
        return None

    def min_frequency_types(self, at_or_better_than: str) -> set[str]:
        """Get control types that require at least the given frequency.

        "at_or_better_than" means rank <= the given tier's rank.
        """
        threshold_rank = self.frequency_tier_rank(at_or_better_than)
        if threshold_rank is None:
            return set()
        return {
            ct.name
            for ct in self.control_types
            if ct.min_frequency_tier and (self.frequency_tier_rank(ct.min_frequency_tier) or 999) <= threshold_rank
        }

    def section_ids(self) -> list[str]:
        """Return all process area IDs."""
        return [pa.id for pa in self.process_areas]

    def get_process_area(self, section_id: str) -> ProcessAreaConfig | None:
        """Look up a process area by ID."""
        for pa in self.process_areas:
            if pa.id == section_id:
                return pa
        return None

    def placement_names(self) -> list[str]:
        """Return all placement category names."""
        return [p.name for p in self.placements]

    def method_names(self) -> list[str]:
        """Return all method names."""
        return [m.name for m in self.methods]

    def narrative_field_names(self) -> list[str]:
        """Return the ordered list of narrative output field names."""
        return [f.name for f in self.narrative.fields]


# ── Loader ────────────────────────────────────────────────────────────────────


def load_domain_config(path: Path) -> DomainConfig:
    """Load and validate a DomainConfig from a YAML file.

    Raises ``pydantic.ValidationError`` if the YAML is malformed or
    cross-references are invalid.
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return DomainConfig(**raw)
