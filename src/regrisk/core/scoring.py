"""Pure business-logic scoring helpers (no validation, no I/O)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from regrisk.core.constants import RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM, RISK_LOW


def derive_inherent_rating(impact: int, frequency: int) -> str:
    """Derive inherent risk rating from impact x frequency."""
    score = impact * frequency
    if score >= 12:
        return RISK_CRITICAL
    if score >= 8:
        return RISK_HIGH
    if score >= 4:
        return RISK_MEDIUM
    return RISK_LOW


def deduplicate_risks(
    risks: list[dict[str, Any]],
    id_prefix: str = "RISK",
) -> list[dict[str, Any]]:
    """Keep only the highest-scoring risk per (source_citation, risk_category).

    When multiple risks share the same obligation citation *and* risk category,
    the one with the highest ``impact_rating × frequency_rating`` is retained.
    Ties are broken by higher ``impact_rating``, then by earlier position.

    After deduplication the risk IDs are re-sequenced (RISK-001, RISK-002, …)
    so they remain contiguous.

    Returns
    -------
    list[dict]
        Deduplicated risks with updated ``risk_id`` values.
    """
    # Group by dedup key, remembering insertion order
    best: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for idx, r in enumerate(risks):
        key = (r.get("source_citation", ""), r.get("risk_category", ""))
        impact = int(r.get("impact_rating", 0))
        freq = int(r.get("frequency_rating", 0))
        score = impact * freq

        prev = best.get(key)
        if prev is None:
            best[key] = (idx, r)
        else:
            p_impact = int(prev[1].get("impact_rating", 0))
            p_freq = int(prev[1].get("frequency_rating", 0))
            p_score = p_impact * p_freq
            if (score, impact) > (p_score, p_impact):
                best[key] = (prev[0], r)  # keep first-seen position

    # Sort winners by their original position to preserve ordering
    winners = sorted(best.values(), key=lambda t: t[0])

    # Re-sequence IDs
    deduped: list[dict[str, Any]] = []
    for new_idx, (_, r) in enumerate(winners, start=1):
        updated = dict(r)
        updated["risk_id"] = f"{id_prefix}-{new_idx:03d}"
        deduped.append(updated)

    return deduped
