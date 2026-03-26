"""Deterministic control validator with 6 rules.

No LLM calls — pure Python validation of narrative output against
locked spec constraints and quality standards.
"""

from __future__ import annotations

import re
from typing import Any

from controlnexus.core.state import ValidationResult

# Vague 'when' terms that should be replaced with specific frequencies
VAGUE_WHEN_TERMS = ("periodic", "ad hoc", "as needed", "various", "as required", "on occasion")

# Risk-related marker words expected in the 'why' field
RISK_MARKERS = (
    "risk",
    "prevent",
    "mitigate",
    "reduce",
    "ensure",
    "compliance",
    "violation",
    "failure",
    "loss",
    "exposure",
    "threat",
    "safeguard",
    "protect",
    "detect",
    "deter",
    "avoid",
)

# Minimum and maximum word count for full_description
MIN_WORDS = 30
MAX_WORDS = 80

# Curated control-domain action verb roots for MULTIPLE_WHATS detection.
# Only these roots are considered "action verbs" — prevents false positives
# from nouns ending in s/ed/ing (e.g. "transactions", "outstanding", "lending").
_ACTION_VERB_ROOTS = (
    "perform",
    "review",
    "validat",
    "reconcil",
    "authoriz",
    "monitor",
    "verif",
    "approv",
    "ensur",
    "confirm",
    "evaluat",
    "assess",
    "execut",
    "examin",
    "inspect",
    "test",
    "check",
    "audit",
    "submit",
    "analyz",
    "investigat",
    "updat",
    "maintain",
    "track",
    "enforc",
    "certif",
    "supervis",
    "escalat",
    "notif",
    "remov",
    "generat",
    "suspend",
    "terminat",
    "consolid",
    "classify",
    "determin",
    "identif",
    "manag",
    "scan",
    "complet",
    "compar",
    "calculat",
)

# Compiled pattern: match any word that starts with one of the verb roots
_ACTION_VERB_RE = re.compile(
    r"\b(?:" + "|".join(_ACTION_VERB_ROOTS) + r")[a-z]*\b",
    re.IGNORECASE,
)

# Noun-form suffixes — words ending in these are likely nouns, not action verbs
_NOUN_SUFFIXES = ("tion", "ment", "ance", "ence", "ity", "ness", "ure")


def validate(
    narrative: dict[str, Any],
    spec: dict[str, Any],
    *,
    min_words: int = MIN_WORDS,
    max_words: int = MAX_WORDS,
) -> ValidationResult:
    """Run all 6 validation rules on a narrative against its locked spec.

    Args:
        narrative: The narrative dict with who/what/when/where/why/full_description.
        spec: The locked spec dict.
        min_words: Minimum word count for full_description (default 30).
        max_words: Maximum word count for full_description (default 80).

    Rules:
        MULTIPLE_WHATS: More than 2 distinct action verbs in 'what'.
        VAGUE_WHEN: 'when' contains vague temporal terms.
        WHO_EQUALS_WHERE: 'who' and 'where' are substrings of each other.
        WHY_MISSING_RISK: 'why' lacks risk-related marker words.
        WORD_COUNT_OUT_OF_RANGE: 'full_description' outside min_words-max_words.
        SPEC_MISMATCH: 'who' or 'where' differs from locked spec values.
    """
    failures: list[str] = []

    what_text = str(narrative.get("what", ""))
    when_text = str(narrative.get("when", ""))
    who_text = str(narrative.get("who", ""))
    where_text = str(narrative.get("where", ""))
    why_text = str(narrative.get("why", ""))
    full_desc = str(narrative.get("full_description", ""))

    # Word count
    words = full_desc.split()
    word_count = len(words)

    # Rule 1: MULTIPLE_WHATS — count distinct control-action verbs only
    action_matches = _ACTION_VERB_RE.findall(what_text.lower())
    # Filter out noun forms (reconciliation, management, etc.) and normalize to roots
    unique_roots: set[str] = set()
    for match in action_matches:
        if any(match.endswith(sfx) or match.endswith(sfx + "s") for sfx in _NOUN_SUFFIXES):
            continue
        for root in _ACTION_VERB_ROOTS:
            if match.startswith(root):
                unique_roots.add(root)
                break
    if len(unique_roots) > 2:
        failures.append("MULTIPLE_WHATS")

    # Rule 2: VAGUE_WHEN
    when_lower = when_text.lower()
    if any(term in when_lower for term in VAGUE_WHEN_TERMS):
        failures.append("VAGUE_WHEN")

    # Rule 3: WHO_EQUALS_WHERE
    who_lower = who_text.lower().strip()
    where_lower = where_text.lower().strip()
    if who_lower and where_lower and (who_lower in where_lower or where_lower in who_lower):
        failures.append("WHO_EQUALS_WHERE")

    # Rule 4: WHY_MISSING_RISK
    why_lower = why_text.lower()
    if not any(marker in why_lower for marker in RISK_MARKERS):
        failures.append("WHY_MISSING_RISK")

    # Rule 5: WORD_COUNT_OUT_OF_RANGE
    if word_count < min_words or word_count > max_words:
        failures.append("WORD_COUNT_OUT_OF_RANGE")

    # Rule 6: SPEC_MISMATCH
    spec_who = str(spec.get("who", "")).strip()
    spec_where = str(spec.get("where_system", "")).strip()
    if spec_who and who_text.strip() != spec_who:
        failures.append("SPEC_MISMATCH")
    if spec_where and where_text.strip() != spec_where:
        failures.append("SPEC_MISMATCH")
    # Deduplicate SPEC_MISMATCH
    if failures.count("SPEC_MISMATCH") > 1:
        while failures.count("SPEC_MISMATCH") > 1:
            failures.remove("SPEC_MISMATCH")

    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
        word_count=word_count,
    )


def build_retry_appendix(
    attempt: int,
    max_attempts: int,
    failures: list[str],
    word_count: int,
    *,
    min_words: int = MIN_WORDS,
    max_words: int = MAX_WORDS,
) -> str:
    """Build failure-specific retry instructions for the NarrativeAgent.

    Produces structured feedback that tells the agent exactly what failed
    and how to fix it.
    """
    lines = [f"ATTEMPT {attempt}/{max_attempts}. Previous failures:"]

    for code in failures:
        if code == "MULTIPLE_WHATS":
            lines.append("- MULTIPLE_WHATS: Use exactly one primary action verb in the 'what' field.")
        elif code == "VAGUE_WHEN":
            lines.append(
                "- VAGUE_WHEN: Your 'when' field contained a vague term. "
                "Replace with a specific frequency like 'monthly', 'quarterly', or 'daily'."
            )
        elif code == "WHO_EQUALS_WHERE":
            lines.append("- WHO_EQUALS_WHERE: The 'who' and 'where' fields are too similar. Make them distinct.")
        elif code == "WHY_MISSING_RISK":
            lines.append(
                "- WHY_MISSING_RISK: The 'why' field must contain a risk-related word "
                "(e.g., 'risk', 'prevent', 'mitigate', 'ensure compliance')."
            )
        elif code == "WORD_COUNT_OUT_OF_RANGE":
            if word_count < min_words:
                lines.append(
                    f"- WORD_COUNT_OUT_OF_RANGE: Word count was {word_count} — increase to at least {min_words}."
                )
            else:
                lines.append(
                    f"- WORD_COUNT_OUT_OF_RANGE: Word count was {word_count} — reduce to {max_words} or fewer."
                )
        elif code == "SPEC_MISMATCH":
            lines.append(
                "- SPEC_MISMATCH: The 'who' or 'where' field does not match the locked spec. Preserve them exactly."
            )

    return "\n".join(lines)
