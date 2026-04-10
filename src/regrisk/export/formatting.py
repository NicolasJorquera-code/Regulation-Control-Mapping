"""Shared column formatting utilities for UI and Excel export."""

from __future__ import annotations

from regrisk.core.constants import COL_DISPLAY_OVERRIDES


def display_col_name(col: str) -> str:
    """Convert a snake_case column key to Title Case for display."""
    if col in COL_DISPLAY_OVERRIDES:
        return COL_DISPLAY_OVERRIDES[col]
    return col.replace("_", " ").title()
