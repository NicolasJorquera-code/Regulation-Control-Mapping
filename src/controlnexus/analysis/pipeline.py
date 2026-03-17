"""Analysis pipeline: run all 4 scanners and produce a GapReport.

Orchestrates ingest → scan → scoring → report generation.
"""

from __future__ import annotations

import logging

from controlnexus.analysis.scanners import (
    ecosystem_balance_analysis,
    evidence_sufficiency_scan,
    frequency_coherence_scan,
    regulatory_coverage_scan,
)
from controlnexus.core.models import SectionProfile
from controlnexus.core.state import FinalControlRecord, GapReport

logger = logging.getLogger(__name__)

# Scoring weights
WEIGHT_REGULATORY = 0.40
WEIGHT_BALANCE = 0.25
WEIGHT_FREQUENCY = 0.15
WEIGHT_EVIDENCE = 0.20


def run_analysis(
    controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> GapReport:
    """Run all 4 scanners and build a weighted GapReport.

    Returns a GapReport with per-dimension gaps and an overall 0-100 score.
    """
    logger.info("Running analysis on %d controls", len(controls))

    reg_gaps = regulatory_coverage_scan(controls, section_profiles)
    bal_gaps = ecosystem_balance_analysis(controls, section_profiles)
    freq_issues = frequency_coherence_scan(controls)
    evid_issues = evidence_sufficiency_scan(controls)

    # Score each dimension 0-100 (higher = better)
    reg_score = _regulatory_score(reg_gaps, controls, section_profiles)
    bal_score = _balance_score(bal_gaps, controls, section_profiles)
    freq_score = _frequency_score(freq_issues, controls)
    evid_score = _evidence_score(evid_issues, controls)

    overall = (
        WEIGHT_REGULATORY * reg_score
        + WEIGHT_BALANCE * bal_score
        + WEIGHT_FREQUENCY * freq_score
        + WEIGHT_EVIDENCE * evid_score
    )

    summary_parts = []
    if reg_gaps:
        summary_parts.append(f"{len(reg_gaps)} regulatory coverage gaps")
    if bal_gaps:
        summary_parts.append(f"{len(bal_gaps)} ecosystem balance issues")
    if freq_issues:
        summary_parts.append(f"{len(freq_issues)} frequency coherence issues")
    if evid_issues:
        summary_parts.append(f"{len(evid_issues)} evidence sufficiency issues")
    summary = "; ".join(summary_parts) if summary_parts else "No gaps identified"

    report = GapReport(
        regulatory_gaps=reg_gaps,
        balance_gaps=bal_gaps,
        frequency_issues=freq_issues,
        evidence_issues=evid_issues,
        overall_score=round(overall, 1),
        summary=summary,
    )
    logger.info("Analysis complete: score=%.1f, %s", overall, summary)
    return report


def _regulatory_score(
    gaps: list,
    controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> float:
    """Score 0-100 for regulatory coverage.

    100 if no gaps, decreases proportionally to the number of frameworks
    below threshold.
    """
    total_frameworks = 0
    for profile in section_profiles.values():
        total_frameworks += len(profile.registry.regulatory_frameworks)
    if total_frameworks == 0:
        return 100.0
    passing = total_frameworks - len(gaps)
    return max(0.0, (passing / total_frameworks) * 100)


def _balance_score(
    gaps: list,
    controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> float:
    """Score 0-100 for ecosystem balance.

    100 if all types are within expected ranges. Deducts proportionally.
    """
    if not controls:
        return 100.0
    # Count total unique types across all sections
    total_types = len({c.selected_level_2 or c.control_type for c in controls})
    if total_types == 0:
        return 100.0
    passing = max(0, total_types - len(gaps))
    return max(0.0, (passing / total_types) * 100)


def _frequency_score(
    issues: list,
    controls: list[FinalControlRecord],
) -> float:
    """Score 0-100 for frequency coherence."""
    if not controls:
        return 100.0
    passing = len(controls) - len(issues)
    return max(0.0, (passing / len(controls)) * 100)


def _evidence_score(
    issues: list,
    controls: list[FinalControlRecord],
) -> float:
    """Score 0-100 for evidence sufficiency."""
    if not controls:
        return 100.0
    passing = len(controls) - len(issues)
    return max(0.0, (passing / len(controls)) * 100)
