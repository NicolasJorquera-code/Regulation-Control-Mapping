"""DomainProfile — packaging a domain as a directory of config + taxonomy + plugins.

A ``DomainProfile`` bundles everything the engine needs from a single
domain: the ``DomainConfig``, the risk taxonomy (loaded from a sibling
``risk_taxonomy.yaml``), a ``ControlIdBuilder`` strategy, regulatory
keywords, and optional prompt fragments.

A ``DomainProfileRegistry`` discovers and loads profiles from a
conventional directory layout.

Example directory layout::

    domains/
      banking/
        domain_config.yaml
        risk_taxonomy.yaml
        regulatory_keywords.yaml
        prompts/
          spec_context.txt
          narrative_style.txt
      healthcare/
        domain_config.yaml
        ...
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict, Field

from controlnexus.core.domain_config import DomainConfig, load_domain_config

logger = logging.getLogger(__name__)


# ── ControlIdBuilder protocol ─────────────────────────────────────────────────


@runtime_checkable
class ControlIdBuilder(Protocol):
    """Protocol for domain-specific control ID generation."""

    def build_id(
        self,
        hierarchy_id: str,
        type_code: str,
        sequence: int,
    ) -> str:
        """Build a control ID string from components."""
        ...


class DefaultControlIdBuilder:
    """Default banking-style control ID builder.

    Format: ``CTRL-{L1:02d}{L2:02d}-{TypeCode}-{Seq:03d}``
    """

    def build_id(self, hierarchy_id: str, type_code: str, sequence: int) -> str:
        parts = hierarchy_id.split(".")
        l1 = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
        l2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return f"CTRL-{l1:02d}{l2:02d}-{type_code}-{sequence:03d}"


# ── DomainProfile model ──────────────────────────────────────────────────────


class DomainProfile(BaseModel):
    """A packaged domain — config, taxonomy, and plugins.

    Immutable after construction. Passed through graph state instead
    of the raw ``DomainConfig`` when a full profile is available.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    config: DomainConfig
    regulatory_keywords: dict[str, list[str]] = Field(default_factory=dict)
    prompt_fragments: dict[str, str] = Field(default_factory=dict)

    @property
    def risk_catalog_size(self) -> int:
        return len(self.config.risk_catalog)

    @property
    def l1_category_count(self) -> int:
        return len(self.config.risk_level_1_categories)


# ── DomainProfileRegistry ────────────────────────────────────────────────────


class DomainProfileRegistry:
    """Discovers and loads DomainProfiles from a directory of domain directories.

    Expected layout::

        base_dir/
          banking/
            domain_config.yaml   # required
            risk_taxonomy.yaml   # optional, auto-merged by loader
            regulatory_keywords.yaml  # optional
            prompts/             # optional
              spec_context.txt
              narrative_style.txt
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir
        self._profiles: dict[str, DomainProfile] = {}
        self._builders: dict[str, ControlIdBuilder] = {}

    @property
    def available_domains(self) -> list[str]:
        """Return names of registered/discovered domains."""
        if self._base_dir and self._base_dir.exists():
            discovered = [
                d.name for d in self._base_dir.iterdir()
                if d.is_dir() and not d.name.startswith("_") and (d / "domain_config.yaml").exists()
            ]
            return sorted(set(list(self._profiles.keys()) + discovered))
        return sorted(self._profiles.keys())

    def register(
        self,
        name: str,
        profile: DomainProfile,
        builder: ControlIdBuilder | None = None,
    ) -> None:
        """Manually register a domain profile."""
        self._profiles[name] = profile
        self._builders[name] = builder or DefaultControlIdBuilder()

    def get(self, name: str) -> DomainProfile | None:
        """Get a profile by name, loading from disk if necessary."""
        if name in self._profiles:
            return self._profiles[name]
        if self._base_dir:
            profile = self._load_from_dir(name)
            if profile:
                self._profiles[name] = profile
                return profile
        return None

    def get_builder(self, name: str) -> ControlIdBuilder:
        """Get the control ID builder for a domain, defaulting if not found."""
        return self._builders.get(name, DefaultControlIdBuilder())

    def _load_from_dir(self, name: str) -> DomainProfile | None:
        """Load a profile from a domain directory."""
        if not self._base_dir:
            return None
        domain_dir = self._base_dir / name
        config_path = domain_dir / "domain_config.yaml"
        if not config_path.exists():
            logger.warning("Domain directory '%s' has no domain_config.yaml", domain_dir)
            return None

        try:
            config = load_domain_config(config_path)
        except Exception:
            logger.exception("Failed to load domain config from %s", config_path)
            return None

        # Load regulatory keywords
        regulatory_keywords: dict[str, list[str]] = {}
        kw_path = domain_dir / "regulatory_keywords.yaml"
        if kw_path.exists():
            try:
                with kw_path.open("r", encoding="utf-8") as f:
                    regulatory_keywords = yaml.safe_load(f) or {}
            except Exception:
                logger.warning("Failed to load regulatory keywords from %s", kw_path)

        # Load prompt fragments
        prompt_fragments: dict[str, str] = {}
        prompts_dir = domain_dir / "prompts"
        if prompts_dir.is_dir():
            for txt_file in prompts_dir.glob("*.txt"):
                try:
                    prompt_fragments[txt_file.stem] = txt_file.read_text(encoding="utf-8")
                except Exception:
                    logger.warning("Failed to load prompt fragment %s", txt_file)

        profile = DomainProfile(
            name=name,
            config=config,
            regulatory_keywords=regulatory_keywords,
            prompt_fragments=prompt_fragments,
        )
        self._builders[name] = DefaultControlIdBuilder()
        return profile
