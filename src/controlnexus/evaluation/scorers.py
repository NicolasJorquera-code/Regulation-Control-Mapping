"""Four independent scoring functions for generated controls.

1. Faithfulness (0-4): spec adherence
2. Completeness (0-6): field quality
3. Diversity (0.0-1.0): semantic distinctness
4. Gap Closure (delta): improvement in overall score
"""

from __future__ import annotations

import math
from typing import Any

from controlnexus.analysis.pipeline import run_analysis
from controlnexus.core.constants import derive_frequency_from_when
from controlnexus.core.models import SectionProfile
from controlnexus.core.state import FinalControlRecord
from controlnexus.memory.embedder import Embedder


# -- 1. Faithfulness Scorer (0-4) -----------------------------------------------


def score_faithfulness(
    record: FinalControlRecord,
    spec: dict[str, Any],
    placement_config: dict[str, Any],
) -> tuple[int, list[str]]:
    """Score how well a control matches its locked spec.

    +1: who matches spec.who
    +1: where matches spec.where_system
    +1: control type valid for its level_1
    +1: placement valid per placement_methods.yaml
    """
    score = 0
    failures: list[str] = []

    # Who matches spec
    spec_who = spec.get("who", "")
    if spec_who and record.who.lower().strip() == spec_who.lower().strip():
        score += 1
    elif spec_who:
        failures.append("who_mismatch")

    # Where matches spec
    spec_where = spec.get("where_system", "")
    if spec_where and record.where.lower().strip() == spec_where.lower().strip():
        score += 1
    elif spec_where:
        failures.append("where_mismatch")

    # Control type valid for level_1
    l2_by_l1 = placement_config.get("control_taxonomy", {}).get("level_2_by_level_1", {})
    allowed = l2_by_l1.get(record.selected_level_1, [])
    if record.selected_level_2 in allowed:
        score += 1
    else:
        failures.append("type_invalid_for_l1")

    # Placement valid
    valid_placements = placement_config.get("placements", [])
    if record.selected_level_1 in valid_placements:
        score += 1
    else:
        failures.append("placement_invalid")

    return score, failures


# -- 2. Completeness Scorer (0-6) -----------------------------------------------


GENERIC_ROLES = {"control owner", "owner", "manager", "user", "person"}
GENERIC_SYSTEMS = {"enterprise system", "system", "application", "platform"}

ACTION_VERBS = [
    "reviews", "reconciles", "validates", "approves", "investigates",
    "monitors", "verifies", "assesses", "evaluates", "performs",
    "conducts", "analyzes", "generates", "confirms", "certifies",
]

RISK_WORDS = [
    "risk", "prevent", "mitigate", "ensure", "compliance",
    "detect", "avoid", "safeguard", "protect", "reduce",
    "exposure", "violation", "breach", "fraud", "error",
    "discrepancy",
]


def score_completeness(record: FinalControlRecord) -> tuple[int, list[str]]:
    """Score field quality of a control.

    +1: who contains a role title (not generic)
    +1: what contains an action verb from phrase bank
    +1: when derives to a real frequency (not "Other")
    +1: where names a specific system (not generic)
    +1: why contains a risk-related word
    +1: full_description is 30-80 words
    """
    score = 0
    failures: list[str] = []

    # Who: role title
    if record.who and record.who.lower().strip() not in GENERIC_ROLES:
        score += 1
    else:
        failures.append("generic_role")

    # What: action verb
    what_lower = record.what.lower()
    if any(v in what_lower for v in ACTION_VERBS):
        score += 1
    else:
        failures.append("no_action_verb")

    # When: real frequency
    freq = derive_frequency_from_when(record.when)
    if freq != "Other":
        score += 1
    else:
        failures.append("no_real_frequency")

    # Where: specific system
    if record.where and record.where.lower().strip() not in GENERIC_SYSTEMS:
        score += 1
    else:
        failures.append("generic_system")

    # Why: risk word
    why_lower = record.why.lower()
    if any(w in why_lower for w in RISK_WORDS):
        score += 1
    else:
        failures.append("no_risk_word")

    # Word count: 30-80
    word_count = len(record.full_description.split())
    if 30 <= word_count <= 80:
        score += 1
    else:
        failures.append(f"word_count_{word_count}")

    return score, failures


# -- 3. Diversity Scorer (0.0-1.0) ----------------------------------------------


def score_diversity(
    records: list[FinalControlRecord],
    embedder: Embedder | None = None,
    threshold: float = 0.92,
) -> tuple[float, int]:
    """Score semantic distinctness across all controls.

    Returns (diversity_score, near_duplicate_count).
    diversity_score = 1 - mean(pairwise_similarities)
    near_duplicate_count = pairs with similarity > threshold
    """
    if len(records) < 2:
        return 1.0, 0

    if embedder is None:
        # No embedder — return neutral score
        return 0.5, 0

    texts = [r.full_description for r in records]
    embeddings = embedder.embed(texts)

    # Compute pairwise cosine similarities
    n = len(embeddings)
    total_sim = 0.0
    pair_count = 0
    near_dup_count = 0

    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            total_sim += sim
            pair_count += 1
            if sim > threshold:
                near_dup_count += 1

    mean_sim = total_sim / pair_count if pair_count > 0 else 0.0
    diversity = max(0.0, 1.0 - mean_sim)

    return round(diversity, 4), near_dup_count


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# -- 4. Gap Closure Scorer (delta) -----------------------------------------------


def score_gap_closure(
    original_controls: list[FinalControlRecord],
    generated_controls: list[FinalControlRecord],
    section_profiles: dict[str, SectionProfile],
) -> float:
    """Score improvement by re-running analysis on combined controls.

    Returns delta = new_score - original_score (positive = improvement).
    """
    if not original_controls:
        return 0.0

    original_report = run_analysis(original_controls, section_profiles)
    combined = original_controls + generated_controls
    combined_report = run_analysis(combined, section_profiles)

    return round(combined_report.overall_score - original_report.overall_score, 2)
