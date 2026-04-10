"""Pure business-logic scoring helpers (no validation, no I/O)."""

from __future__ import annotations

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
