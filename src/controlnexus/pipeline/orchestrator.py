"""Core pipeline orchestrator.

Coordinates the full control-generation pipeline: hierarchy loading, scope
selection, target sizing, deterministic mapping, 3-phase control building
(with optional parallel LLM enrichment), and Excel/JSON export.

Ported from controlnexus-blueprint/reference-code/orchestrator.py with:
- controlforge.* → controlnexus.* imports
- Synchronous agents → async agents (asyncio.gather + Semaphore)
- Validator class → standalone validate() function
- Custom logging → standard logging
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from controlnexus.agents import EnricherAgent, NarrativeAgent, SpecAgent
from controlnexus.agents.base import AgentContext
from controlnexus.core.config import (
    load_placement_methods,
    load_section_profiles,
    load_standards,
    load_taxonomy_catalog,
)
from controlnexus.core.models import BusinessUnitProfile, RunConfig
from controlnexus.core.state import FinalControlRecord, HierarchyNode
from controlnexus.core.transport import build_client_from_env
from controlnexus.export.excel import export_to_excel
from controlnexus.hierarchy.parser import load_apqc_hierarchy
from controlnexus.hierarchy.scope import build_section_breakdown, select_scope
from controlnexus.validation.validator import build_retry_appendix, validate

logger = logging.getLogger(__name__)

MAX_CONTROL_TARGET = 10000

TYPE_CODE_MAP = {
    "Reconciliation": "REC",
    "Authorization": "AUT",
    "Verification and Validation": "VNV",
    "Exception Reporting": "EXR",
    "Segregation of Duties": "SOD",
    "Documentation, Data, and Activity Completeness and Appropriateness Checks": "DOC",
    "Internal and External Audits": "AUD",
    "Automated Rules": "ARL",
    "Training and Awareness Programs": "TRN",
    "Risk Escalation Processes": "REP",
    "System and Application Restrictions": "SAR",
    "Data Security and Protection": "DSP",
    "Third Party Due Diligence": "THR",
    "Client Due Diligence and Transaction Monitoring": "CDM",
    "Supervisory Review": "SVR",
    "Surveillance": "SRV",
    "Physical Safeguards": "PHY",
    "Risk and Compliance Assessments": "RCA",
    "Staffing and Resourcing Adequacy": "SRA",
    "Business Continuity Planning and Awareness": "BCP",
    "Crisis Management": "CRS",
    "Technology Disaster Recovery": "TDR",
    "Risk Limit Setting and Monitoring": "RLM",
    "Change Management": "CHM",
}

FREQUENCY_ORDERED_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Daily", ("daily", "every day", "each day", "per day", "day-end", "day end", "end of day", "eod")),
    ("Weekly", ("weekly", "every week", "each week", "per week", "biweekly", "bi-weekly", "fortnight")),
    (
        "Monthly",
        (
            "monthly",
            "every month",
            "each month",
            "per month",
            "month-end",
            "month end",
            "eom",
            "semi-monthly",
            "semimonthly",
        ),
    ),
    ("Quarterly", ("quarterly", "every quarter", "each quarter", "per quarter", "qtr", "quarter-end", "quarter end")),
    ("Semi-Annual", ("semi-annual", "semi annual", "semiannual", "bi-annual", "biannual", "twice a year")),
    ("Annual", ("annual", "annually", "yearly", "once a year", "each year", "per year")),
]


def _derive_frequency_from_when(when_text: Any) -> str:
    """Derive a frequency label from a free-text 'when' field."""
    if not when_text:
        return "Other"
    normalized = re.sub(r"\s+", " ", str(when_text).strip().lower())
    if not normalized:
        return "Other"
    for frequency, keywords in FREQUENCY_ORDERED_RULES:
        if any(keyword in normalized for keyword in keywords):
            return frequency
    return "Other"


@dataclass
class PlanningResult:
    """Results from a completed planning run."""

    run_id: str
    scope_sections: list[str]
    subsection: str | None
    selected_nodes: int
    selected_leaves: int
    target_controls: int
    target_source: str
    section_allocation: dict[str, int]
    section_breakdown: list[dict[str, Any]]
    plan_path: str
    generated_controls: int
    excel_path: str | None
    llm_enabled: bool


class Orchestrator:
    """Pipeline orchestrator for control dataset generation.

    Coordinates hierarchy parsing, scope selection, sizing, deterministic
    assignment mapping, 3-phase control building (with optional parallel
    LLM enrichment), and output export.
    """

    def __init__(self, run_config: RunConfig, project_root: Path):
        self.run_config = run_config
        self.project_root = project_root

    @staticmethod
    def _emit(
        message: str,
        *,
        verbose: bool,
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        logger.info(message)
        if verbose and progress_callback:
            progress_callback(f"[controlforge] {message}")

    async def execute_planning(
        self,
        config_dir: Path,
        *,
        verbose: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        preloaded_nodes: list[HierarchyNode] | None = None,
    ) -> PlanningResult:
        """Execute the full planning pipeline.

        Args:
            config_dir: Root config directory.
            verbose: Enable stage-by-stage progress messages.
            progress_callback: Callable for progress messages.
            preloaded_nodes: Pre-loaded hierarchy nodes (skips file loading).

        Returns:
            PlanningResult with all run metadata and output paths.
        """
        run_t0 = time.monotonic()
        logger.info(
            "Pipeline execution started",
            extra={
                "run_id": self.run_config.run_id,
                "sections": self.run_config.scope.sections,
            },
        )

        # -- Hierarchy loading --
        if preloaded_nodes is not None:
            all_nodes = preloaded_nodes
            self._emit(
                f"Using preloaded hierarchy nodes={len(all_nodes)}",
                verbose=verbose,
                progress_callback=progress_callback,
            )
        else:
            self._emit("Resolving input template", verbose=verbose, progress_callback=progress_callback)
            template_path = self._resolve_template_path()
            self._emit(f"Loading APQC hierarchy from {template_path}", verbose=verbose, progress_callback=progress_callback)
            all_nodes = load_apqc_hierarchy(template_path)
            self._emit(f"Loaded hierarchy nodes={len(all_nodes)}", verbose=verbose, progress_callback=progress_callback)

        # -- Scope selection --
        selected_nodes_typed = select_scope(
            nodes=all_nodes,
            top_sections=self.run_config.scope.sections,
            subsection=self.run_config.scope.subsection,
        )
        selected_leaves_typed = [node for node in selected_nodes_typed if node.is_leaf]

        # Convert to dicts for the rest of the pipeline
        selected_nodes = [n.model_dump() for n in selected_nodes_typed]
        selected_leaves = [n.model_dump() for n in selected_leaves_typed]

        self._emit(
            f"Scope selected sections={self.run_config.scope.sections} nodes={len(selected_nodes)} leaves={len(selected_leaves)}",
            verbose=verbose,
            progress_callback=progress_callback,
        )

        # -- Config loading --
        self._emit("Loading taxonomy and section profiles", verbose=verbose, progress_callback=progress_callback)
        taxonomy_catalog = load_taxonomy_catalog(config_dir / "taxonomy.yaml")
        taxonomy = taxonomy_catalog.control_types
        business_units = taxonomy_catalog.business_units
        section_profiles = load_section_profiles(config_dir=config_dir, section_ids=self.run_config.scope.sections)
        standards_cfg = load_standards(config_dir / "standards.yaml")
        placement_methods_cfg = load_placement_methods(config_dir / "placement_methods.yaml")

        # -- Sizing --
        if self.run_config.sizing.target_count is not None:
            target_controls = int(self.run_config.sizing.target_count)
            target_source = "target_count"
        else:
            target_controls = min(MAX_CONTROL_TARGET, max(20, len(selected_leaves) * 3))
            target_source = "leaf-based default"

        if self.run_config.sizing.dry_run_limit is not None:
            target_controls = min(target_controls, int(self.run_config.sizing.dry_run_limit))
            target_source = f"{target_source} + dry_run_limit"

        self._emit(
            f"Target controls={target_controls} source={target_source}",
            verbose=verbose,
            progress_callback=progress_callback,
        )

        output_dir = (self.project_root / self.run_config.output.directory).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        plan_path = output_dir / f"{self.run_config.run_id}__plan.json"

        # -- Distribution & allocation --
        type_distribution = self._build_type_distribution(
            target_controls=target_controls,
            taxonomy=[item.control_type for item in taxonomy],
        )
        self._emit(
            f"Built control type distribution across {len(type_distribution)} types",
            verbose=verbose,
            progress_callback=progress_callback,
        )

        section_allocation = self._build_section_allocation(
            selected_nodes=selected_nodes,
            selected_leaves=selected_leaves,
            section_profiles=section_profiles,
            target_controls=target_controls,
        )

        # -- Deterministic mapping --
        assignments = self._deterministic_map_with_bu(
            leaf_nodes=selected_leaves,
            type_distribution=type_distribution,
            section_targets=section_allocation,
            business_units=business_units,
            section_profiles=section_profiles,
        )
        self._emit(
            f"Mapped assignments={len(assignments)}",
            verbose=verbose,
            progress_callback=progress_callback,
        )

        # -- 3-phase control building --
        generated_records, llm_enabled = await self._build_control_records(
            assignments,
            section_profiles,
            taxonomy,
            business_units,
            standards_cfg,
            placement_methods_cfg,
            verbose=verbose,
            progress_callback=progress_callback,
        )
        self._emit(
            f"Generated controls={len(generated_records)} llm_enabled={llm_enabled}",
            verbose=verbose,
            progress_callback=progress_callback,
        )

        # -- Export --
        excel_path: Path | None = None
        output_formats = {fmt.lower() for fmt in self.run_config.output.formats}
        if "excel" in output_formats:
            self._emit("Exporting Excel workbook", verbose=verbose, progress_callback=progress_callback)
            excel_output = output_dir / f"{self.run_config.run_id}__controls.xlsx"
            excel_path = export_to_excel(
                records=generated_records,
                output_path=excel_output,
                sheet_name="generated_controls",
            )
            self._emit(f"Excel export complete: {excel_path}", verbose=verbose, progress_callback=progress_callback)

        # -- Plan JSON --
        plan_payload = {
            "run_id": self.run_config.run_id,
            "scope": {
                "sections": self.run_config.scope.sections,
                "subsection": self.run_config.scope.subsection,
            },
            "selected_nodes": len(selected_nodes),
            "selected_leaves": len(selected_leaves),
            "target_controls": target_controls,
            "target_source": target_source,
            "section_allocation": section_allocation,
            "type_distribution": type_distribution,
            "assignments": len(assignments),
            "generated_controls": len(generated_records),
            "section_breakdown": build_section_breakdown(selected_nodes_typed),
            "excel_path": str(excel_path) if excel_path else None,
            "llm_enabled": llm_enabled,
        }
        plan_path.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
        self._emit(f"Plan JSON written: {plan_path}", verbose=verbose, progress_callback=progress_callback)

        run_elapsed = time.monotonic() - run_t0
        logger.info(
            "Pipeline execution completed",
            extra={
                "run_id": self.run_config.run_id,
                "generated_controls": len(generated_records),
                "target_controls": target_controls,
                "llm_enabled": llm_enabled,
                "duration_s": round(run_elapsed, 3),
            },
        )

        return PlanningResult(
            run_id=self.run_config.run_id,
            scope_sections=list(self.run_config.scope.sections),
            subsection=self.run_config.scope.subsection,
            selected_nodes=len(selected_nodes),
            selected_leaves=len(selected_leaves),
            target_controls=target_controls,
            target_source=target_source,
            section_allocation=section_allocation,
            section_breakdown=build_section_breakdown(selected_nodes_typed),
            plan_path=str(plan_path),
            generated_controls=len(generated_records),
            excel_path=str(excel_path) if excel_path else None,
            llm_enabled=llm_enabled,
        )

    def _resolve_template_path(self) -> Path:
        template_path = self.run_config.input.apqc_template
        if not template_path.is_absolute():
            template_path = (self.project_root / template_path).resolve()
        return template_path

    # -- Distribution & allocation (static, no async needed) -------------------

    @staticmethod
    def _build_type_distribution(
        target_controls: int,
        taxonomy: list[str],
    ) -> dict[str, int]:
        if not taxonomy:
            return {"Reconciliation": target_controls}
        per_type = max(1, target_controls // len(taxonomy))
        dist = {t: per_type for t in taxonomy}
        return Orchestrator._normalize_distribution(dist, target_controls)

    @staticmethod
    def _normalize_distribution(dist: dict[str, int], target: int) -> dict[str, int]:
        dist = dict(dist)
        if not dist:
            return {"Reconciliation": target}
        while sum(dist.values()) < target:
            key = max(dist.keys(), key=lambda k: dist[k])
            dist[key] += 1
        while sum(dist.values()) > target:
            key = max([k for k, v in dist.items() if v > 0], key=lambda k: dist[k])
            dist[key] -= 1
            if dist[key] == 0:
                del dist[key]
                if not dist:
                    dist["Reconciliation"] = target
                    break
        return dist

    @staticmethod
    def _build_section_allocation(
        selected_nodes: list[dict[str, Any]],
        selected_leaves: list[dict[str, Any]],
        section_profiles: dict[str, Any],
        target_controls: int,
    ) -> dict[str, int]:
        leaves_by_section: Counter[str] = Counter(node["top_section"] for node in selected_leaves)
        policy_hits: Counter[str] = Counter()
        procedure_hits: Counter[str] = Counter()
        for node in selected_nodes:
            section_id = node["top_section"]
            name = str(node.get("name", "")).lower()
            depth = int(node.get("depth", 0))
            if any(token in name for token in ["policy", "governance", "framework", "standard"]):
                policy_hits[section_id] += 2 if depth <= 2 else 1
            if any(token in name for token in ["procedure", "process", "workflow", "operations", "execute", "perform"]):
                procedure_hits[section_id] += 2 if depth >= 3 else 1

        weights: dict[str, float] = {}
        for section_id, leaf_count in leaves_by_section.items():
            profile = section_profiles.get(section_id)
            multiplier = float(profile.risk_profile.multiplier) if profile else 1.0
            policy_factor = 1.0 + (policy_hits.get(section_id, 0) / max(1, leaf_count * 2))
            procedure_factor = 1.0 + (procedure_hits.get(section_id, 0) / max(1, leaf_count * 3))
            weights[section_id] = max(0.1, leaf_count * multiplier * policy_factor * procedure_factor)

        return Orchestrator._normalize_weighted_targets(weights, target_controls)

    @staticmethod
    def _normalize_weighted_targets(weights: dict[str, float], target: int) -> dict[str, int]:
        if not weights:
            return {}
        if target <= 0:
            return {key: 0 for key in weights}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            total_weight = float(len(weights))
            normalized_weights = {key: 1.0 for key in weights}
        else:
            normalized_weights = dict(weights)

        raw = {
            key: (value / total_weight) * target
            for key, value in normalized_weights.items()
        }
        result = {key: int(value) for key, value in raw.items()}
        allocated = sum(result.values())
        remainder = target - allocated
        if remainder > 0:
            order = sorted(raw.keys(), key=lambda k: (raw[k] - int(raw[k])), reverse=True)
            for key in order[:remainder]:
                result[key] += 1
        return result

    def _deterministic_map_with_bu(
        self,
        leaf_nodes: list[dict[str, Any]],
        type_distribution: dict[str, int],
        section_targets: dict[str, int],
        business_units: list[BusinessUnitProfile],
        section_profiles: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not leaf_nodes:
            return []

        leaves_by_section: dict[str, list[dict[str, Any]]] = {}
        for leaf in leaf_nodes:
            leaves_by_section.setdefault(leaf["top_section"], []).append(leaf)

        type_queue: list[str] = []
        for control_type, count in type_distribution.items():
            type_queue.extend([control_type] * count)
        if not type_queue:
            type_queue = ["Reconciliation"]

        assignments: list[dict[str, Any]] = []
        queue_idx = 0
        for section_id, target_count in section_targets.items():
            section_leaves = leaves_by_section.get(section_id, [])
            if not section_leaves or target_count <= 0:
                continue
            bu_quotas = self._business_unit_quota_for_section(
                section_id=section_id,
                section_target=target_count,
                business_units=business_units,
                section_profile=section_profiles.get(section_id),
            )
            bu_order: list[str] = []
            for bu_id, quota in bu_quotas.items():
                bu_order.extend([bu_id] * quota)
            if not bu_order:
                bu_order = ["BU-UNSPECIFIED"] * target_count

            for idx in range(target_count):
                leaf = section_leaves[idx % len(section_leaves)]
                control_type = type_queue[queue_idx % len(type_queue)]
                queue_idx += 1
                bu_id = bu_order[idx % len(bu_order)]
                assignments.append(
                    {
                        "hierarchy_id": leaf["hierarchy_id"],
                        "leaf_name": leaf["name"],
                        "control_type": control_type,
                        "business_unit_id": bu_id,
                    }
                )

        while len(assignments) < sum(section_targets.values()):
            leaf = leaf_nodes[len(assignments) % len(leaf_nodes)]
            control_type = type_queue[queue_idx % len(type_queue)]
            queue_idx += 1
            assignments.append(
                {
                    "hierarchy_id": leaf["hierarchy_id"],
                    "leaf_name": leaf["name"],
                    "control_type": control_type,
                    "business_unit_id": "BU-UNSPECIFIED",
                }
            )
        return assignments

    @staticmethod
    def _business_unit_quota_for_section(
        section_id: str,
        section_target: int,
        business_units: list[BusinessUnitProfile],
        section_profile: Any,
    ) -> dict[str, int]:
        if section_target <= 0:
            return {}
        if not business_units:
            return {"BU-UNSPECIFIED": section_target}

        section_tag = f"{section_id}.0"
        weights: dict[str, float] = {}
        for bu in business_units:
            weight = 1.0
            if section_tag in bu.primary_sections:
                weight += 2.5
            weights[bu.business_unit_id] = weight
        return Orchestrator._normalize_weighted_targets(weights, section_target)

    # -- 3-phase control building (async) --------------------------------------

    async def _build_control_records(
        self,
        assignments: list[dict[str, Any]],
        section_profiles: dict[str, Any],
        taxonomy: list[Any],
        business_units: list[BusinessUnitProfile],
        standards_cfg: dict[str, Any],
        placement_methods_cfg: dict[str, Any],
        *,
        verbose: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[list[FinalControlRecord], bool]:
        """Build full control records using the 3-phase approach.

        Phase 1 (sequential): pre-compute deterministic defaults.
        Phase 2 (parallel async): optional LLM enrichment.
        Phase 3 (sequential): merge results and assign final CTRL IDs.

        Returns:
            (records, llm_enabled)
        """
        sequence_by_type: Counter[str] = Counter()
        output_sequence_by_type: Counter[str] = Counter()

        client = build_client_from_env(timeout_seconds=self.run_config.transport.timeout_seconds)
        use_llm = client is not None
        if use_llm:
            self._emit("LLM credentials detected: using API generation", verbose=verbose, progress_callback=progress_callback)
        else:
            self._emit(
                "No LLM credentials detected: using baseline defaults (set ICA_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env)",
                verbose=verbose,
                progress_callback=progress_callback,
            )

        type_definitions = {item.control_type: item.definition for item in taxonomy}
        taxonomy_cfg = self._build_taxonomy_constraint_config(placement_methods_cfg)
        business_unit_map = {bu.business_unit_id: bu for bu in business_units}

        available_bus = [
            {
                "business_unit_id": bu.business_unit_id,
                "name": bu.name,
                "description": bu.description,
                "key_control_types": bu.key_control_types,
            }
            for bu in business_units
        ]

        if use_llm:
            agent_ctx = AgentContext(
                client=client,
                model=client.model,
                temperature=self.run_config.transport.temperature,
                max_tokens=self.run_config.transport.max_tokens,
                timeout_seconds=self.run_config.transport.timeout_seconds,
            )
            spec_agent = SpecAgent(agent_ctx)
            narrative_agent = NarrativeAgent(agent_ctx)
            enricher_agent = EnricherAgent(agent_ctx)
        else:
            spec_agent = narrative_agent = enricher_agent = None

        # ── Phase 1: Pre-compute deterministic defaults (sequential) ──────────
        prepared: list[dict[str, Any]] = []
        for assignment in assignments:
            hierarchy_id = assignment["hierarchy_id"]
            section_id = hierarchy_id.split(".")[0]
            profile = section_profiles.get(section_id)

            control_type = assignment["control_type"]
            business_unit_id = assignment.get("business_unit_id", "BU-UNSPECIFIED")
            business_unit = business_unit_map.get(business_unit_id)
            sequence_by_type[control_type] += 1

            role = profile.registry.roles[(sequence_by_type[control_type] - 1) % len(profile.registry.roles)] if profile and profile.registry.roles else "Control Owner"
            system = profile.registry.systems[(sequence_by_type[control_type] - 1) % len(profile.registry.systems)] if profile and profile.registry.systems else "Enterprise System"
            trigger = profile.registry.event_triggers[(sequence_by_type[control_type] - 1) % len(profile.registry.event_triggers)] if profile and profile.registry.event_triggers else "monthly"
            evidence_artifact = profile.registry.evidence_artifacts[(sequence_by_type[control_type] - 1) % len(profile.registry.evidence_artifacts)] if profile and profile.registry.evidence_artifacts else "control evidence log"
            evidence = f"{evidence_artifact} with {role} sign-off, retained in {system}"
            rationale = profile.risk_profile.rationale if profile else "Operational and compliance risk mitigation"

            placement = "Detective"
            method = "Manual"
            if profile and profile.exemplars:
                exemplar = next((e for e in profile.exemplars if e.control_type == control_type), profile.exemplars[0])
                placement = exemplar.placement
                method = exemplar.method

            what_text = f"Performs {control_type.lower()} checks for {assignment['leaf_name']}"
            full_description = (
                f"{trigger}, {role} performs {control_type.lower()} for {assignment['leaf_name']} "
                f"in {system} to reduce control failure risk and support accurate operations."
            )
            taxonomy_constraints = self._taxonomy_constraints_for_type(
                control_type=control_type,
                taxonomy_cfg=taxonomy_cfg,
                type_definitions=type_definitions,
            )

            spec = {
                "hierarchy_id": hierarchy_id,
                "leaf_name": assignment["leaf_name"],
                "selected_level_1": taxonomy_constraints["selected_level_1"],
                "control_type": control_type,
                "placement": placement,
                "method": method,
                "who": role,
                "what_action": what_text,
                "what_detail": "",
                "when": trigger,
                "where_system": system,
                "why_risk": rationale,
                "evidence": evidence,
            }

            narrative = {
                "who": role,
                "what": what_text,
                "when": trigger,
                "where": system,
                "why": rationale,
                "full_description": full_description,
            }
            enriched = {
                "refined_full_description": full_description,
                "quality_rating": "Satisfactory",
                "rationale": "Baseline output (no LLM)",
            }

            prepared.append({
                "assignment": assignment,
                "hierarchy_id": hierarchy_id,
                "section_id": section_id,
                "profile": profile,
                "control_type": control_type,
                "business_unit_id": business_unit_id,
                "business_unit": business_unit,
                "role": role,
                "system": system,
                "trigger": trigger,
                "evidence": evidence,
                "rationale": rationale,
                "placement": placement,
                "method": method,
                "what_text": what_text,
                "full_description": full_description,
                "taxonomy_constraints": taxonomy_constraints,
                "spec": spec,
                "narrative": narrative,
                "enriched": enriched,
                "llm_result": None,
            })

        # ── Phase 2: LLM enrichment (parallel async) ─────────────────────────
        if use_llm and spec_agent and narrative_agent and enricher_agent:
            max_workers = max(1, self.run_config.concurrency.max_parallel_controls)
            self._emit(
                f"Starting parallel LLM enrichment: {len(prepared)} controls, max_workers={max_workers}",
                verbose=verbose,
                progress_callback=progress_callback,
            )
            progress_counter = {"done": 0}
            semaphore = asyncio.Semaphore(max_workers)

            async def _bounded_enrich(item: dict[str, Any]) -> None:
                async with semaphore:
                    result = await self._llm_enrich_single(
                        item=item,
                        spec_agent=spec_agent,
                        narrative_agent=narrative_agent,
                        enricher_agent=enricher_agent,
                        available_bus=available_bus,
                        business_unit_map=business_unit_map,
                        standards_cfg=standards_cfg,
                        taxonomy_cfg=taxonomy_cfg,
                        type_definitions=type_definitions,
                        placement_methods_cfg=placement_methods_cfg,
                    )
                    item["llm_result"] = result
                    progress_counter["done"] += 1
                    done = progress_counter["done"]
                    if verbose and progress_callback and (done == 1 or done % 25 == 0 or done == len(prepared)):
                        progress_callback(f"[controlforge] LLM enrichment progress: {done}/{len(prepared)} controls")

            await asyncio.gather(*[_bounded_enrich(item) for item in prepared])

        # ── Phase 3: Finalize records in original order (sequential) ──────────
        records: list[FinalControlRecord] = []
        for item in prepared:
            llm = item["llm_result"]
            spec = llm["spec"] if llm else item["spec"]
            narrative = llm["narrative"] if llm else item["narrative"]
            enriched = llm["enriched"] if llm else item["enriched"]
            control_type = llm["control_type"] if llm else item["control_type"]
            business_unit_id = llm["business_unit_id"] if llm else item["business_unit_id"]
            business_unit = llm["business_unit"] if llm else item["business_unit"]

            output_sequence_by_type[control_type] += 1
            control_id = build_control_id(item["hierarchy_id"], control_type, output_sequence_by_type[control_type])

            validation_result = validate(narrative, spec)

            records.append(
                FinalControlRecord(
                    control_id=control_id,
                    hierarchy_id=item["hierarchy_id"],
                    leaf_name=item["assignment"]["leaf_name"],
                    control_type=control_type,
                    selected_level_1=spec.get("selected_level_1", "Unspecified"),
                    selected_level_2=control_type,
                    business_unit_id=business_unit_id if business_unit_id != "BU-UNSPECIFIED" else (business_unit.business_unit_id if business_unit else "BU-UNSPECIFIED"),
                    business_unit_name=business_unit.name if business_unit else "Unspecified",
                    placement=spec.get("placement", item["placement"]),
                    method=spec.get("method", item["method"]),
                    who=narrative.get("who", item["role"]),
                    what=narrative.get("what", item["what_text"]),
                    when=narrative.get("when", item["trigger"]),
                    frequency=_derive_frequency_from_when(narrative.get("when", item["trigger"])),
                    where=narrative.get("where", item["system"]),
                    why=narrative.get("why", item["rationale"]),
                    full_description=enriched.get("refined_full_description", narrative.get("full_description", item["full_description"])),
                    quality_rating=enriched.get("quality_rating", "Satisfactory"),
                    validator_passed=validation_result.passed,
                    validator_retries=0,
                    validator_failures=validation_result.failures,
                    evidence=spec.get("evidence", item["evidence"]),
                )
            )
            if verbose and progress_callback and (len(records) == 1 or len(records) % 25 == 0 or len(records) == len(prepared)):
                progress_callback(f"[controlforge] Progress: finalized {len(records)}/{len(prepared)} controls")

        if use_llm and client:
            await client.close()

        return records, use_llm

    async def _llm_enrich_single(
        self,
        item: dict[str, Any],
        spec_agent: SpecAgent,
        narrative_agent: NarrativeAgent,
        enricher_agent: EnricherAgent,
        available_bus: list[dict[str, Any]],
        business_unit_map: dict[str, BusinessUnitProfile],
        standards_cfg: dict[str, Any],
        taxonomy_cfg: dict[str, Any],
        type_definitions: dict[str, str],
        placement_methods_cfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Run Spec -> Narrative (with retries) -> Enricher for one control.

        Returns dict with updated spec/narrative/enriched/control_type/
        business_unit_id/business_unit, or None on failure.
        """
        hierarchy_id = item["hierarchy_id"]
        t0 = time.monotonic()
        try:
            profile = item["profile"]
            control_type = item["control_type"]
            business_unit_id = item["business_unit_id"]
            business_unit = item["business_unit"]
            placement = item["placement"]
            method = item["method"]
            taxonomy_constraints = item["taxonomy_constraints"]
            spec = dict(item["spec"])

            suggested_bu = (
                {
                    "business_unit_id": business_unit.business_unit_id,
                    "name": business_unit.name,
                    "description": business_unit.description,
                    "key_control_types": business_unit.key_control_types,
                }
                if business_unit
                else {}
            )
            spec = await spec_agent.execute(
                leaf={"hierarchy_id": hierarchy_id, "name": item["assignment"]["leaf_name"]},
                control_type=control_type,
                type_definition=type_definitions.get(control_type, ""),
                registry=profile.registry.model_dump() if profile else {},
                placement_defs=placement_methods_cfg,
                method_defs=placement_methods_cfg,
                taxonomy_constraints=taxonomy_constraints,
                diversity_context={
                    "available_business_units": available_bus,
                    "suggested_business_unit": suggested_bu,
                },
            )

            # Resolve LLM-chosen business unit
            llm_bu_id = str(spec.get("business_unit_id", "")).strip()
            if llm_bu_id and llm_bu_id in business_unit_map:
                business_unit_id = llm_bu_id
                business_unit = business_unit_map[llm_bu_id]

            selected_level_1, selected_level_2 = self._sanitize_taxonomy_selection(
                selected_level_1=str(spec.get("selected_level_1", taxonomy_constraints["selected_level_1"])),
                selected_level_2=str(spec.get("control_type", control_type)),
                fallback_level_1=str(taxonomy_constraints["selected_level_1"]),
                fallback_level_2=control_type,
                taxonomy_cfg=taxonomy_cfg,
            )
            spec["selected_level_1"] = selected_level_1
            spec["control_type"] = selected_level_2
            control_type = selected_level_2

            best_narrative = None
            validation = validate({}, spec)  # initial dummy validation
            for attempt in range(1, 4):
                retry_appendix = None
                if attempt > 1:
                    retry_appendix = build_retry_appendix(
                        attempt=attempt,
                        max_attempts=3,
                        failures=validation.failures,
                        word_count=validation.word_count,
                    )
                candidate = await narrative_agent.execute(
                    locked_spec=spec,
                    standards=standards_cfg.get("five_w", {}),
                    phrase_bank_cfg=standards_cfg.get("phrase_bank", {}),
                    exemplars=[e.model_dump() for e in profile.exemplars] if profile else [],
                    regulatory_context=profile.registry.regulatory_frameworks if profile else [],
                    retry_appendix=retry_appendix,
                )
                validation = validate(candidate, spec)
                best_narrative = candidate
                if validation.passed:
                    break

            narrative = best_narrative if best_narrative else item["narrative"]

            enriched_candidate = await enricher_agent.execute(
                validated_control={
                    "control_id": f"CTRL-PENDING-{hierarchy_id}",
                    "hierarchy_id": hierarchy_id,
                    "leaf_name": item["assignment"]["leaf_name"],
                    "control_type": control_type,
                    "placement": spec.get("placement", placement),
                    "method": spec.get("method", method),
                    "narrative": narrative,
                    "validation": validation.model_dump(),
                    "spec": spec,
                },
                rating_criteria_cfg={"allowed": standards_cfg.get("quality_ratings", [])},
                nearest_neighbors=[],
            )
            enriched = enriched_candidate if enriched_candidate else item["enriched"]

            return {
                "spec": spec,
                "narrative": narrative,
                "enriched": enriched,
                "control_type": control_type,
                "business_unit_id": business_unit_id,
                "business_unit": business_unit,
            }
        except Exception:
            elapsed = time.monotonic() - t0
            logger.exception(
                "LLM enrichment failed for control — falling back to deterministic defaults",
                extra={
                    "hierarchy_id": hierarchy_id,
                    "control_type": item.get("control_type"),
                    "duration_s": round(elapsed, 3),
                },
            )
            return None

    # -- Taxonomy helpers (static) ---------------------------------------------

    @staticmethod
    def _build_taxonomy_constraint_config(placement_methods_cfg: dict[str, Any]) -> dict[str, Any]:
        control_taxonomy = placement_methods_cfg.get("control_taxonomy", {}) if isinstance(placement_methods_cfg, dict) else {}
        level_2_by_level_1 = control_taxonomy.get("level_2_by_level_1", {}) if isinstance(control_taxonomy, dict) else {}
        cleaned_map: dict[str, list[str]] = {}
        for level_1, level_2_values in level_2_by_level_1.items():
            if not isinstance(level_1, str) or not isinstance(level_2_values, list):
                continue
            valid_level_2 = [item for item in level_2_values if isinstance(item, str) and item.strip()]
            if valid_level_2:
                cleaned_map[level_1] = valid_level_2

        level_1_options = control_taxonomy.get("level_1_options", []) if isinstance(control_taxonomy, dict) else []
        normalized_level_1 = [item for item in level_1_options if isinstance(item, str) and item.strip()]
        if not normalized_level_1:
            normalized_level_1 = list(cleaned_map.keys())

        reverse: dict[str, str] = {}
        for level_1, level_2_values in cleaned_map.items():
            for level_2 in level_2_values:
                reverse.setdefault(level_2, level_1)

        return {
            "level_1_options": normalized_level_1,
            "level_2_by_level_1": cleaned_map,
            "level_1_by_level_2": reverse,
        }

    def _taxonomy_constraints_for_type(
        self,
        control_type: str,
        taxonomy_cfg: dict[str, Any],
        type_definitions: dict[str, str],
    ) -> dict[str, Any]:
        level_1_options = list(taxonomy_cfg.get("level_1_options", []))
        level_2_by_level_1 = dict(taxonomy_cfg.get("level_2_by_level_1", {}))
        reverse = dict(taxonomy_cfg.get("level_1_by_level_2", {}))

        selected_level_1 = reverse.get(control_type)
        if not selected_level_1 and level_1_options:
            selected_level_1 = level_1_options[0]
        if not selected_level_1:
            selected_level_1 = "Unspecified"

        allowed_level_2 = list(level_2_by_level_1.get(selected_level_1, []))
        if not allowed_level_2 and control_type:
            allowed_level_2 = [control_type]

        return {
            "level_1_options": level_1_options or [selected_level_1],
            "selected_level_1": selected_level_1,
            "allowed_level_2_for_selected_level_1": allowed_level_2,
            "level_2_definitions": {name: type_definitions.get(name, "") for name in allowed_level_2},
        }

    @staticmethod
    def _sanitize_taxonomy_selection(
        selected_level_1: str,
        selected_level_2: str,
        fallback_level_1: str,
        fallback_level_2: str,
        taxonomy_cfg: dict[str, Any],
    ) -> tuple[str, str]:
        level_2_by_level_1 = taxonomy_cfg.get("level_2_by_level_1", {})
        if not isinstance(level_2_by_level_1, dict):
            return fallback_level_1, fallback_level_2

        allowed = level_2_by_level_1.get(selected_level_1)
        if not isinstance(allowed, list) or not allowed:
            selected_level_1 = fallback_level_1
            allowed = level_2_by_level_1.get(selected_level_1, [])

        if not isinstance(allowed, list) or not allowed:
            return fallback_level_1, fallback_level_2

        if selected_level_2 not in allowed:
            if fallback_level_2 in allowed:
                selected_level_2 = fallback_level_2
            else:
                selected_level_2 = allowed[0]
        return selected_level_1, selected_level_2


def type_to_code(control_type: str) -> str:
    """Convert a control type name to a 3-character uppercase code."""
    if control_type in TYPE_CODE_MAP:
        return TYPE_CODE_MAP[control_type]
    cleaned = "".join(ch for ch in control_type if ch.isalpha() or ch == " ")
    words = cleaned.split()
    consonants = "".join(ch for ch in "".join(words).upper() if ch not in "AEIOU ")
    return (consonants[:3] or "CTL").ljust(3, "X")


def build_control_id(hierarchy_id: str, control_type: str, sequence: int) -> str:
    """Build a deterministic control ID like ``CTRL-0501-RCN-001``."""
    parts = hierarchy_id.split(".")
    l1 = int(parts[0])
    l2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return f"CTRL-{l1:02d}{l2:02d}-{type_to_code(control_type)}-{sequence:03d}"


def planning_result_to_dict(result: PlanningResult) -> dict[str, Any]:
    """Serialise a PlanningResult dataclass to a plain dict."""
    return asdict(result)
