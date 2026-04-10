"""Shared utility functions for the ingest layer."""

from __future__ import annotations


def clean_str(val: object) -> str:
    """Convert a cell value to a clean string, handling NaN and 'nan'."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s
