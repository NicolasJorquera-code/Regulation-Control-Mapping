"""
Deterministic validator with typed failure codes.

Pattern: The validator checks pipeline artifacts against a fixed set of
rules *without* calling an LLM.  Each rule produces a specific failure
code (e.g., ``SOURCES_MISSING``) so the agent can receive targeted
feedback on exactly what to fix — no fuzzy LLM interpretation needed.

The graph uses the validator as a gate: if ``passed`` is False, it
routes back to the SynthesizerAgent with the failure codes appended
to a retry prompt.

# CUSTOMIZE: Replace these rules with your domain's validation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result from the validator.

    ``failures`` contains machine-readable codes (not prose) so the
    retry prompt can give the agent precise instructions.
    """

    passed: bool
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def _check_sources_missing(summary: dict) -> str | None:
    """SOURCES_MISSING: summary must reference at least one source."""
    sources = summary.get("sources_used", [])
    if not sources:
        return "SOURCES_MISSING"
    return None


def _check_too_short(summary: dict, min_words: int) -> str | None:
    """TOO_SHORT: summary must meet minimum word count."""
    text = summary.get("text", "")
    wc = len(text.split())
    if wc < min_words:
        return "TOO_SHORT"
    return None


def _check_too_long(summary: dict, max_words: int) -> str | None:
    """TOO_LONG: summary must not exceed maximum word count."""
    text = summary.get("text", "")
    wc = len(text.split())
    if wc > max_words:
        return "TOO_LONG"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_summary(
    summary: dict,
    min_words: int = 50,
    max_words: int = 300,
) -> ValidationResult:
    """Run all validation rules against a summary dict.

    Returns a ``ValidationResult`` with ``passed=True`` if all rules pass.

    # CUSTOMIZE: Add more rules here.  Each rule is a function that
    # returns a failure code string or None.
    """
    failures: list[str] = []

    for check_result in [
        _check_sources_missing(summary),
        _check_too_short(summary, min_words),
        _check_too_long(summary, max_words),
    ]:
        if check_result is not None:
            failures.append(check_result)

    text = summary.get("text", "")
    word_count = len(text.split())

    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
        metrics={"word_count": word_count},
    )
