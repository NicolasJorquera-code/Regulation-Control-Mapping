"""DomainConfig — single source of truth for an organization's control domain.

Consolidates taxonomy, section profiles, placement/methods, standards, and
frequency rules into one validated Pydantic model loaded from a single YAML.

.. note::
   **TODO — Config convergence**: ``DomainConfig`` (this module) and
   ``RunConfig`` (``core/models.py``) serve similar purposes for different
   pipelines. ``DomainConfig`` powers the ControlForge Modular graph;
   ``RunConfig`` powers the legacy orchestrator. When the orchestrator is
   deprecated, evaluate whether ``RunConfig`` fields (scope, sizing,
   transport, output) should be absorbed into ``DomainConfig`` to create a
   single unified configuration model.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


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
    """One business unit.

    ``processes`` is not a YAML field — it is computed at load time from
    ``ProcessConfig.owner_bu_ids`` (see ``DomainConfig._compute_bu_processes``).
    Legacy fields ``primary_sections`` and ``key_control_types`` are accepted
    for backward compatibility but are not used by the risk-driven engine.
    """

    id: str
    name: str
    description: str = ""
    primary_sections: list[str] = Field(default_factory=list)
    key_control_types: list[str] = Field(default_factory=list)
    regulatory_exposure: list[str] = Field(default_factory=list)
    # Computed, not authored in YAML
    processes: list[str] = Field(default_factory=list, exclude=True)


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
    """Risk scoring for a process area (legacy — retained for migration)."""

    inherent_risk: int = 3
    regulatory_intensity: int = 3
    control_density: int = 3
    multiplier: float = 1.0
    rationale: str = ""


class RiskLevel1Category(BaseModel):
    """A top-level risk category in the two-tier taxonomy."""

    model_config = ConfigDict(frozen=True)

    name: str
    code: str  # 3-letter code (e.g., OPS, CYB, CRD)
    definition: str
    grounding: str | None = None
    sub_groups: list[str] = Field(default_factory=list)


class MitigationLink(BaseModel):
    """Weighted link from a risk to a mitigating control type.

    ``effectiveness`` weights allocation: 1.0 = primary, 0.6 = supporting.
    ``line_of_defense`` optionally tags 1st/2nd/3rd LoD.
    """

    model_config = ConfigDict(frozen=True)

    control_type: str
    effectiveness: float = Field(default=1.0, ge=0.0, le=1.0)
    line_of_defense: int | None = Field(default=None, ge=1, le=3)


class RiskCatalogEntry(BaseModel):
    """A risk archetype in the organization's two-tier risk taxonomy.

    Each entry belongs to a ``RiskLevel1Category`` (via ``level_1``) and
    optionally to a ``sub_group`` within that category. The ``default_mitigating_links``
    specify which control types mitigate this risk archetype by default.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    level_1: str = ""
    level_1_code: str = ""
    sub_group: str | None = None
    default_severity: int = Field(default=3, ge=1, le=5)
    description: str = ""
    default_mitigating_links: list[MitigationLink] = Field(default_factory=list)
    grounding: str | None = None

    # Legacy compat: accept flat category or default_mitigating_types
    category: str = ""  # deprecated alias for level_1

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_fields(cls, data: Any) -> Any:
        """Accept legacy flat forms and coerce to new schema."""
        if not isinstance(data, dict):
            return data
        # category → level_1 fallback
        if "category" in data and not data.get("level_1"):
            data["level_1"] = data["category"]
        # default_mitigating_types: list[str] → default_mitigating_links: list[MitigationLink]
        if "default_mitigating_types" in data and "default_mitigating_links" not in data:
            raw_types = data.pop("default_mitigating_types", [])
            links = []
            for i, ct in enumerate(raw_types):
                if isinstance(ct, str):
                    links.append({"control_type": ct, "effectiveness": 1.0})
                elif isinstance(ct, dict):
                    links.append(ct)
            data["default_mitigating_links"] = links
        return data


class RiskInstance(BaseModel):
    """A contextualized risk within a specific process.

    Fields:
        severity: Inherent risk rating (1–5, categorical). Drives reporting,
            heatmaps, and risk appetite. Input from risk management.
        multiplier: Allocation weight tuner (float, default 1.0). Tilts
            control generation budget toward this risk without changing the
            rating. Input from the control generation operator.
        mitigating_links: Weighted references to control types that mitigate
            this risk instance, overriding catalog defaults.
        source_policy_clause: Provenance — populated by PolicyIngestionAgent
            when the risk was derived from a policy document.
    """

    risk_id: str
    severity: int = Field(default=3, ge=1, le=5)
    multiplier: float = Field(default=1.0)
    mitigating_links: list[MitigationLink] = Field(default_factory=list)
    rationale: str = ""
    source_policy_clause: str | None = None

    # Legacy compat
    mitigated_by_types: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_mitigation(cls, data: Any) -> Any:
        """Accept flat mitigated_by_types and coerce to mitigating_links."""
        if not isinstance(data, dict):
            return data
        if "mitigated_by_types" in data and "mitigating_links" not in data:
            raw_types = data.get("mitigated_by_types", [])
            links = [{"control_type": ct, "effectiveness": 1.0} for ct in raw_types if isinstance(ct, str)]
            data["mitigating_links"] = links
        return data

    @model_validator(mode="after")
    def _warn_extreme_multiplier(self) -> "RiskInstance":
        """Warn on likely-misused multiplier values."""
        if self.multiplier > 3.0:
            logger.warning(
                "RiskInstance '%s' has multiplier %.1f > 3.0 — this likely indicates "
                "severity is being expressed via multiplier instead of the severity field.",
                self.risk_id, self.multiplier,
            )
        elif self.multiplier < 0.1 and self.multiplier > 0:
            logger.warning(
                "RiskInstance '%s' has multiplier %.2f < 0.1 — this will nearly "
                "eliminate allocation for this risk.",
                self.risk_id, self.multiplier,
            )
        return self

    @property
    def mitigating_type_names(self) -> list[str]:
        """Return control type names from mitigating_links (convenience)."""
        return [link.control_type for link in self.mitigating_links]


class ResolvedRisk(BaseModel):
    """Fully resolved risk context for a single control assignment.

    Produced by ``RiskAgent`` and consumed by downstream spec/narrative nodes.
    Immutable — frozen after construction.
    """

    model_config = ConfigDict(frozen=True)

    risk_id: str
    risk_name: str
    level_1: str = ""
    sub_group: str | None = None
    severity: int = Field(default=3, ge=1, le=5)
    multiplier: float = 1.0
    description: str = ""
    mitigating_links: list[MitigationLink] = Field(default_factory=list)
    selected_control_type: str = ""


class ProcessConfig(BaseModel):
    """A business process, owned by one or more BUs.

    ``domain_metadata`` carries domain-specific keys without leaking
    domain concepts into the core schema. Banking writes
    ``{"apqc_section_id": "4.0"}``. ``hierarchy_id`` is a domain-neutral
    path whose format is determined by the DomainProfile.
    """

    id: str
    name: str
    domain: str = ""
    domain_metadata: dict[str, Any] = Field(default_factory=dict)
    hierarchy_id: str = ""
    owner_bu_ids: list[str] = Field(default_factory=list)
    risks: list[RiskInstance] = Field(default_factory=list)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    exemplars: list[ExemplarConfig] = Field(default_factory=list)

    # Legacy compat: accept apqc_section_id and migrate to domain_metadata
    apqc_section_id: str = Field(default="", exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _migrate_apqc(cls, data: Any) -> Any:
        """Move apqc_section_id into domain_metadata if present."""
        if not isinstance(data, dict):
            return data
        apqc = data.pop("apqc_section_id", "") or ""
        if apqc:
            dm = data.get("domain_metadata", {}) or {}
            dm["apqc_section_id"] = apqc
            data["domain_metadata"] = dm
            if not data.get("hierarchy_id"):
                data["hierarchy_id"] = apqc
        return data

    @property
    def effective_section_id(self) -> str:
        """Return APQC section ID from metadata, or hierarchy_id, or process id."""
        return self.domain_metadata.get("apqc_section_id", "") or self.hierarchy_id or self.id


class ProcessAreaConfig(BaseModel):
    """One process area / section (legacy — kept for backward compatibility)."""

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
    processes: list[ProcessConfig] = Field(default_factory=list)
    risk_level_1_categories: list[RiskLevel1Category] = Field(default_factory=list)
    risk_catalog: list[RiskCatalogEntry] = Field(default_factory=list)

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

    # ── Auto-migration: process_areas → processes ──────────────────────────

    @model_validator(mode="after")
    def _auto_migrate_process_areas(self) -> "DomainConfig":
        """If only legacy process_areas are provided, synthesize processes + risk_catalog."""
        if self.process_areas and not self.processes:
            known_types = {ct.name for ct in self.control_types}
            catalog: list[RiskCatalogEntry] = []
            procs: list[ProcessConfig] = []
            for pa in self.process_areas:
                risk_id = f"RISK-{pa.id.replace('.', '')}"
                mitigated_by = [t for t in pa.affinity.HIGH if t in known_types]
                links = [MitigationLink(control_type=t, effectiveness=1.0) for t in mitigated_by]
                catalog.append(
                    RiskCatalogEntry(
                        id=risk_id,
                        name=f"{pa.name} Risk",
                        level_1="Operational",
                        level_1_code="OPS",
                        default_severity=pa.risk_profile.inherent_risk,
                        description=pa.risk_profile.rationale,
                        default_mitigating_links=links,
                    )
                )
                owner_bu_ids = [
                    bu.id for bu in self.business_units if pa.id in bu.primary_sections
                ]
                procs.append(
                    ProcessConfig(
                        id=pa.id,
                        name=pa.name,
                        domain=pa.domain,
                        domain_metadata={"apqc_section_id": pa.id},
                        hierarchy_id=pa.id,
                        owner_bu_ids=owner_bu_ids,
                        risks=[
                            RiskInstance(
                                risk_id=risk_id,
                                severity=pa.risk_profile.inherent_risk,
                                multiplier=pa.risk_profile.multiplier,
                                mitigating_links=links,
                                rationale=pa.risk_profile.rationale,
                            )
                        ],
                        registry=pa.registry,
                        exemplars=pa.exemplars,
                    )
                )
            object.__setattr__(self, "processes", procs)
            if not self.risk_catalog:
                object.__setattr__(self, "risk_catalog", catalog)
        return self

    # ── Compute BU→Process from Process→BU ────────────────────────────────

    @model_validator(mode="after")
    def _compute_bu_processes(self) -> "DomainConfig":
        """Populate BU.processes from ProcessConfig.owner_bu_ids (authoritative)."""
        bu_procs: dict[str, list[str]] = {bu.id: [] for bu in self.business_units}
        for proc in self.processes:
            for bu_id in proc.owner_bu_ids:
                if bu_id in bu_procs:
                    bu_procs[bu_id].append(proc.id)
        for bu in self.business_units:
            # Also include legacy primary_sections as process refs if applicable
            existing = set(bu_procs.get(bu.id, []))
            if bu.primary_sections and not existing:
                for sid in bu.primary_sections:
                    existing.add(sid)
            bu.processes = sorted(existing)
        return self

    # ── Cross-reference validation ────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "DomainConfig":
        known_types = {ct.name for ct in self.control_types}
        known_sections = {pa.id for pa in self.process_areas}
        known_placements = {p.name for p in self.placements}
        known_freq_tiers = {ft.label for ft in self.frequency_tiers}
        known_risk_ids = {r.id for r in self.risk_catalog}
        known_l1_categories = {cat.name for cat in self.risk_level_1_categories}
        l1_sub_groups: dict[str, set[str]] = {
            cat.name: set(cat.sub_groups) for cat in self.risk_level_1_categories
        }
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

        # Validate risk catalog entries against L1 categories and control types
        for entry in self.risk_catalog:
            if known_l1_categories and entry.level_1 and entry.level_1 not in known_l1_categories:
                errors.append(
                    f"RiskCatalogEntry '{entry.id}' level_1 '{entry.level_1}' "
                    f"not in declared categories: {sorted(known_l1_categories)}"
                )
            if entry.sub_group and entry.level_1:
                parent_subs = l1_sub_groups.get(entry.level_1, set())
                if parent_subs and entry.sub_group not in parent_subs:
                    errors.append(
                        f"RiskCatalogEntry '{entry.id}' sub_group '{entry.sub_group}' "
                        f"not in {entry.level_1}'s sub_groups: {sorted(parent_subs)}"
                    )
            for link in entry.default_mitigating_links:
                if link.control_type not in known_types:
                    errors.append(
                        f"RiskCatalogEntry '{entry.id}' default_mitigating_links "
                        f"references unknown type: '{link.control_type}'"
                    )

        # Validate process/risk cross-references
        for proc in self.processes:
            for bu_id in proc.owner_bu_ids:
                if self.business_units and bu_id not in {bu.id for bu in self.business_units}:
                    errors.append(f"Process '{proc.id}' references unknown BU: '{bu_id}'")
            for risk in proc.risks:
                if known_risk_ids and risk.risk_id not in known_risk_ids:
                    errors.append(f"Process '{proc.id}' references unknown risk: '{risk.risk_id}'")
                for link in risk.mitigating_links:
                    if link.control_type not in known_types:
                        errors.append(
                            f"Process '{proc.id}' risk '{risk.risk_id}' mitigating_links "
                            f"references unknown type: '{link.control_type}'"
                        )

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

    def get_process(self, process_id: str) -> ProcessConfig | None:
        """Look up a process by ID."""
        for p in self.processes:
            if p.id == process_id:
                return p
        return None

    def get_risk_catalog_entry(self, risk_id: str) -> RiskCatalogEntry | None:
        """Look up a risk catalog entry by ID."""
        for r in self.risk_catalog:
            if r.id == risk_id:
                return r
        return None

    def get_business_unit(self, bu_id: str) -> BusinessUnitConfig | None:
        """Look up a business unit by ID."""
        for bu in self.business_units:
            if bu.id == bu_id:
                return bu
        return None

    def process_ids(self) -> list[str]:
        """Return all process IDs."""
        return [p.id for p in self.processes]

    def placement_names(self) -> list[str]:
        """Return all placement category names."""
        return [p.name for p in self.placements]

    def method_names(self) -> list[str]:
        """Return all method names."""
        return [m.name for m in self.methods]

    def narrative_field_names(self) -> list[str]:
        """Return the ordered list of narrative output field names."""
        return [f.name for f in self.narrative.fields]

    def bu_processes(self, bu_id: str) -> list[str]:
        """Return process IDs owned by a business unit (computed from ProcessConfig.owner_bu_ids)."""
        return [p.id for p in self.processes if bu_id in p.owner_bu_ids]


# ── Loader ────────────────────────────────────────────────────────────────────


def load_domain_config(path: Path) -> DomainConfig:
    """Load and validate a DomainConfig from a YAML file.

    If a sibling ``risk_taxonomy.yaml`` exists, its ``risk_level_1_categories``
    and ``risk_catalog`` are merged into the config (config values take precedence).

    Raises ``pydantic.ValidationError`` if the YAML is malformed or
    cross-references are invalid.
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Check for sibling risk taxonomy
    taxonomy_path = path.parent / "risk_taxonomy.yaml"
    if taxonomy_path.exists():
        with taxonomy_path.open("r", encoding="utf-8") as f:
            tax_raw = yaml.safe_load(f) or {}
        # Merge L1 categories if not already in config
        if "risk_level_1_categories" not in raw and "risk_level_1_categories" in tax_raw:
            raw["risk_level_1_categories"] = tax_raw["risk_level_1_categories"]
        # Merge risk catalog if not already in config
        if "risk_catalog" not in raw and "risk_catalog" in tax_raw:
            raw["risk_catalog"] = tax_raw["risk_catalog"]

    return DomainConfig(**raw)
