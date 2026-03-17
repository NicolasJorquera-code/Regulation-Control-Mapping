"""Four analysis scanners for gap identification.

All scanners are pure Python (no LLM). They take control records and
section profiles and produce typed gap/issue models.
"""

from __future__ import annotations

import re

from controlnexus.core.constants import derive_frequency_from_when
from controlnexus.core.models import AffinityMatrix, SectionProfile
from controlnexus.core.state import (
    BalanceGap,
    EvidenceIssue,
    FinalControlRecord,
    FrequencyIssue,
    RegulatoryGap,
)

# -- 1. Regulatory Coverage Scan -----------------------------------------------


def regulatory_coverage_scan(
    controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> list[RegulatoryGap]:
    """Check regulatory framework coverage across controls.

    For each section, loads regulatory_frameworks from its profile.
    Scans each control's why + full_description for keyword matches.
    Frameworks below 60% coverage are flagged.
    """
    gaps: list[RegulatoryGap] = []

    # Group controls by top-level section
    controls_by_section: dict[str, list[FinalControlRecord]] = {}
    for ctrl in controls:
        section_id = _extract_section_id(ctrl.hierarchy_id)
        controls_by_section.setdefault(section_id, []).append(ctrl)

    for section_id, section_controls in controls_by_section.items():
        profile = section_profiles.get(section_id)
        if not profile or not profile.registry.regulatory_frameworks:
            continue

        for framework in profile.registry.regulatory_frameworks:
            # Build keywords from framework name
            keywords = _framework_keywords(framework)
            if not keywords:
                continue

            matching = 0
            for ctrl in section_controls:
                search_text = f"{ctrl.why} {ctrl.full_description}".lower()
                if any(kw in search_text for kw in keywords):
                    matching += 1

            total = len(section_controls)
            coverage = matching / total if total > 0 else 0.0

            if coverage < 0.6:
                gaps.append(RegulatoryGap(
                    framework=framework,
                    required_theme=framework,
                    current_coverage=round(coverage, 3),
                    severity="high" if coverage < 0.3 else "medium",
                ))

    return gaps


def _extract_section_id(hierarchy_id: str) -> str:
    """Extract top-level section from hierarchy ID like '4.1.1.1' → '4.0'."""
    parts = hierarchy_id.split(".")
    return f"{parts[0]}.0" if parts else "0.0"


def _framework_keywords(framework: str) -> list[str]:
    """Generate search keywords from a framework name."""
    # Split on common delimiters, lowercase, filter short words
    words = re.split(r"[\s\-/()]+", framework.lower())
    # Keep meaningful words (length > 3, not common filler)
    filler = {"the", "and", "for", "with", "from", "that", "this", "into"}
    return [w for w in words if len(w) > 3 and w not in filler]


# -- 2. Ecosystem Balance Analysis ----------------------------------------------


def ecosystem_balance_analysis(
    controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> list[BalanceGap]:
    """Check control type distribution against affinity matrix.

    HIGH types should be >=40%, MEDIUM 20-40%, LOW 5-20%, NONE 0-5%.
    """
    gaps: list[BalanceGap] = []

    # Expected percentage ranges for each affinity level
    EXPECTED_RANGES: dict[str, tuple[float, float]] = {
        "HIGH": (0.40, 1.0),
        "MEDIUM": (0.20, 0.40),
        "LOW": (0.05, 0.20),
        "NONE": (0.0, 0.05),
    }

    controls_by_section: dict[str, list[FinalControlRecord]] = {}
    for ctrl in controls:
        section_id = _extract_section_id(ctrl.hierarchy_id)
        controls_by_section.setdefault(section_id, []).append(ctrl)

    for section_id, section_controls in controls_by_section.items():
        profile = section_profiles.get(section_id)
        if not profile:
            continue

        total = len(section_controls)
        if total == 0:
            continue

        # Count by control type (selected_level_2)
        type_counts: dict[str, int] = {}
        for ctrl in section_controls:
            ct = ctrl.selected_level_2 or ctrl.control_type
            type_counts[ct] = type_counts.get(ct, 0) + 1

        # Check each type against its affinity level
        affinity = profile.affinity
        affinity_map = _build_affinity_map(affinity)

        for control_type, count in type_counts.items():
            actual_pct = count / total
            level = affinity_map.get(control_type, "NONE")
            min_pct, max_pct = EXPECTED_RANGES.get(level, (0.0, 1.0))

            if actual_pct < min_pct:
                gaps.append(BalanceGap(
                    control_type=control_type,
                    expected_pct=round(min_pct, 3),
                    actual_pct=round(actual_pct, 3),
                    direction="under",
                ))
            elif actual_pct > max_pct:
                gaps.append(BalanceGap(
                    control_type=control_type,
                    expected_pct=round(max_pct, 3),
                    actual_pct=round(actual_pct, 3),
                    direction="over",
                ))

    return gaps


def _build_affinity_map(affinity: AffinityMatrix) -> dict[str, str]:
    """Build a control_type → affinity_level map."""
    result: dict[str, str] = {}
    for ct in affinity.HIGH:
        result[ct] = "HIGH"
    for ct in affinity.MEDIUM:
        result[ct] = "MEDIUM"
    for ct in affinity.LOW:
        result[ct] = "LOW"
    for ct in affinity.NONE:
        result[ct] = "NONE"
    return result


# -- 3. Frequency Coherence Scan ------------------------------------------------

# Expected minimum frequency per control type (type → min frequency order index)
# Lower index = more frequent: Daily=0, Weekly=1, Monthly=2, Quarterly=3, Semi-Annual=4, Annual=5
FREQUENCY_ORDER = ["Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual", "Other"]

# Control types that should have at least monthly frequency
MONTHLY_OR_BETTER_TYPES = {
    "Reconciliation",
    "Exception Reporting",
    "Automated Rules",
}

# Control types that should have at least quarterly frequency
QUARTERLY_OR_BETTER_TYPES = {
    "Authorization",
    "Verification and Validation",
    "Segregation of Duties",
    "Risk Escalation Processes",
}


def frequency_coherence_scan(
    controls: list[FinalControlRecord],
) -> list[FrequencyIssue]:
    """Check frequency reasonableness for each control type.

    Derives frequency from `when` field and checks if it's reasonable
    for the control type.
    """
    issues: list[FrequencyIssue] = []

    for ctrl in controls:
        derived = derive_frequency_from_when(ctrl.when)
        ct = ctrl.selected_level_2 or ctrl.control_type

        expected = _expected_frequency(ct)
        if expected and derived != "Other":
            derived_idx = FREQUENCY_ORDER.index(derived) if derived in FREQUENCY_ORDER else 6
            expected_idx = FREQUENCY_ORDER.index(expected) if expected in FREQUENCY_ORDER else 6
            if derived_idx > expected_idx:
                issues.append(FrequencyIssue(
                    control_id=ctrl.control_id,
                    hierarchy_id=ctrl.hierarchy_id,
                    expected_frequency=expected,
                    actual_frequency=derived,
                ))

    return issues


def _expected_frequency(control_type: str) -> str | None:
    """Return the minimum expected frequency for a control type, or None."""
    if control_type in MONTHLY_OR_BETTER_TYPES:
        return "Monthly"
    if control_type in QUARTERLY_OR_BETTER_TYPES:
        return "Quarterly"
    return None


# -- 4. Evidence Sufficiency Scan -----------------------------------------------


def evidence_sufficiency_scan(
    controls: list[FinalControlRecord],
) -> list[EvidenceIssue]:
    """Score each evidence field 0-3 and flag controls scoring 0-1.

    Scoring rules:
        +1: Names a specific artifact (not generic)
        +1: Identifies who signed/approved
        +1: Names the retention system
    """
    issues: list[EvidenceIssue] = []

    for ctrl in controls:
        score, missing = _score_evidence(ctrl.evidence)
        if score <= 1:
            issues.append(EvidenceIssue(
                control_id=ctrl.control_id,
                hierarchy_id=ctrl.hierarchy_id,
                issue=f"Evidence score {score}/3: missing {', '.join(missing)}",
            ))

    return issues


def _score_evidence(evidence: str) -> tuple[int, list[str]]:
    """Score evidence 0-3 and return (score, list of missing elements)."""
    score = 0
    missing: list[str] = []
    text = evidence.lower().strip()

    if not text:
        return 0, ["specific artifact", "signer/approver", "retention system"]

    # 1. Specific artifact: look for specific document words beyond generic terms
    generic_artifacts = {"documentation", "records", "files", "data", "information"}
    specific_patterns = [
        "report", "log", "certificate", "scorecard", "checklist",
        "register", "tracker", "template", "form", "schedule",
        "matrix", "dashboard", "reconciliation", "assessment",
    ]
    has_specific = any(p in text for p in specific_patterns)
    all_generic = all(
        any(g in word for g in generic_artifacts)
        for word in re.findall(r"\b\w+\b", text)
        if len(word) > 4
    ) if not has_specific else False

    if has_specific and not all_generic:
        score += 1
    else:
        missing.append("specific artifact")

    # 2. Signer/approver
    signer_patterns = [
        "sign-off", "signoff", "sign off", "approval", "approved",
        "preparer", "reviewer", "authorized", "certified", "attested",
        "signature", "signed",
    ]
    if any(p in text for p in signer_patterns):
        score += 1
    else:
        missing.append("signer/approver")

    # 3. Retention system
    system_patterns = [
        "retained in", "stored in", "maintained in", "housed in",
        "platform", "system", "tool", "application", "database",
        "repository",
    ]
    if any(p in text for p in system_patterns):
        score += 1
    else:
        missing.append("retention system")

    return score, missing
