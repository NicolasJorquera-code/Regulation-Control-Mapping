"""
Streamlit 6-tab UI for the Regulatory Obligation Control Mapper.

Tab 1: Upload & Configure  (upload_tab.py)
Tab 2: Classification Review  (review_tabs.py)
Tab 3: Mapping Review  (review_tabs.py)
Tab 4: Results  (results_tab.py)
Tab 5: Traceability  (traceability_tab.py)
Tab 6: Evaluation  (evaluation_tab.py)

Shared helpers live in components.py.
Two graph invocations bridged via st.session_state.
Checkpoint persistence allows resuming after mid-run failures.
"""

from __future__ import annotations

import logging
from typing import Any

from dotenv import load_dotenv
load_dotenv()

# Configure logging so transport/agent messages appear in the terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(message)s",
    datefmt="%H:%M:%S",
)
for _quiet in ("httpx", "httpcore", "urllib3", "matplotlib", "PIL"):
    logging.getLogger(_quiet).setLevel(logging.WARNING)

import streamlit as st

import yaml

from regrisk.graphs.classify_graph import reset_caches as reset_classify_caches
from regrisk.graphs.assess_graph import reset_caches as reset_assess_caches
from regrisk.ui.upload_tab import render_upload_tab
from regrisk.ui.review_tabs import (
    render_classification_review_tab,
    render_mapping_review_tab,
)
from regrisk.ui.results_tab import render_coverage_tab
from regrisk.ui.risk_register_tab import render_risk_register_tab
from regrisk.ui.traceability_tab import render_traceability_tab
from regrisk.ui.evaluation_tab import render_evaluation_tab
from regrisk.ui.data_explorer_tab import render_data_explorer_tab
from regrisk.core.config import default_config_path

# ── Tab registry: label → (icon, render_function) ──
_TAB_REGISTRY: dict[str, tuple[str, Any]] = {
    "Upload & Configure":    ("📁", render_upload_tab),
    "Data Source Explorer":  ("🔍", render_data_explorer_tab),
    "Classification Review": ("🏷️", render_classification_review_tab),
    "Mapping Review":        ("🗺️", render_mapping_review_tab),
    "Coverage":              ("📊", render_coverage_tab),
    "Risk Register":         ("⚠️", render_risk_register_tab),
    "Traceability":          ("🔗", render_traceability_tab),
    "Evaluation":            ("📈", render_evaluation_tab),
}

_ALL_TAB_LABELS = list(_TAB_REGISTRY.keys())


def _visible_tabs() -> list[str]:
    """Return the list of tab labels to show, driven by config/default.yaml."""
    try:
        with open(default_config_path(), "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        configured = raw.get("ui", {}).get("visible_tabs", _ALL_TAB_LABELS)
        # Filter to only known tabs, preserving configured order
        return [t for t in configured if t in _TAB_REGISTRY]
    except Exception:
        return _ALL_TAB_LABELS


# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
/* ── Retained table styles (Tab 5 traceability only) ── */
.wrapped-table-container {
    max-height: 500px;
    overflow-y: auto;
    overflow-x: auto;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    margin-bottom: 1rem;
}
.wrapped-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}
.wrapped-table th {
    position: sticky;
    top: 0;
    background: #f0f2f6;
    border-bottom: 2px solid #ccc;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
    z-index: 1;
}
.wrapped-table td {
    padding: 6px 12px;
    border-bottom: 1px solid #eee;
    white-space: normal;
    word-wrap: break-word;
    overflow-wrap: break-word;
    max-width: 450px;
    vertical-align: top;
    line-height: 1.4;
}
.wrapped-table tr:hover {
    background-color: #f8f9fa;
}

/* ── Category pill badges ── */
.category-pill {
    display: inline-block;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.8rem;
    font-weight: 500;
    color: #333;
    white-space: nowrap;
}

/* ── Citation monospace badges ── */
.citation-badge {
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
    background: #f0f2f6;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.85rem;
    white-space: nowrap;
}

/* ── Obligation detail panel ── */
.obligation-detail {
    padding: 1rem;
    border-left: 3px solid #1E88E5;
    margin-bottom: 0.5rem;
    background: #fafbfc;
    line-height: 1.6;
}

/* ── Coverage indicators ── */
.coverage-covered { color: #2e7d32; font-weight: 600; }
.coverage-partial { color: #f57f17; font-weight: 600; }
.coverage-gap { color: #c62828; font-weight: 600; }

/* ── Risk score badges ── */
.risk-critical {
    display: inline-block; background: #c62828; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.risk-high {
    display: inline-block; background: #ef6c00; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.risk-medium {
    display: inline-block; background: #f9a825; color: #333;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.risk-low {
    display: inline-block; background: #2e7d32; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}

/* ── Confidence coloring ── */
.conf-high { color: #2e7d32; font-weight: 600; }
.conf-medium { color: #f57f17; font-weight: 600; }
.conf-low { color: #c62828; font-weight: 600; }

/* ── Muted text ── */
.text-muted { color: #6c757d; font-size: 0.85rem; }

/* ── Risk score highlight ── */
.risk-score-highlight {
    display: inline-block; font-size: 1.3rem; font-weight: 800;
    letter-spacing: 0.02em; line-height: 1;
}
.risk-score-label {
    font-size: 0.75rem; color: #6c757d;
}

/* ── Quality rating badge ── */
.quality-badge {
    display: inline-block; font-size: 0.78rem; font-weight: 600;
    border-radius: 4px; padding: 2px 8px; vertical-align: middle;
}

/* ── Stacked coverage bar ── */
.coverage-bar {
    display: flex; height: 28px; border-radius: 4px; overflow: hidden;
    margin: 0.5rem 0; font-size: 0.75rem; font-weight: 600;
}
.coverage-bar > div {
    display: flex; align-items: center; justify-content: center; color: white;
}
.coverage-bar .bar-covered { background: #2e7d32; }
.coverage-bar .bar-partial { background: #f9a825; color: #333; }
.coverage-bar .bar-gap { background: #c62828; }

/* ── Data Source Explorer badges ── */
.type-badge-preventive {
    display: inline-block; background: #1565C0; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.type-badge-detective {
    display: inline-block; background: #7B1FA2; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.rating-badge-effective {
    display: inline-block; background: #2e7d32; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}
.rating-badge-default {
    display: inline-block; background: #e2e3e5; color: #333;
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600;
}

/* ── Explorer table ── */
.explorer-table-container {
    max-height: 700px;
    overflow-y: auto;
    overflow-x: auto;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    margin-bottom: 1rem;
}
.explorer-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}
.explorer-table th {
    position: sticky;
    top: 0;
    background: #f0f2f6;
    border-bottom: 2px solid #ccc;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
    z-index: 1;
}
.explorer-table td {
    padding: 6px 12px;
    border-bottom: 1px solid #eee;
    white-space: normal;
    word-wrap: break-word;
    overflow-wrap: break-word;
    vertical-align: top;
    line-height: 1.4;
}
.explorer-table tr:hover {
    background-color: #f8f9fa;
}
.explorer-table tr.selected-row {
    background-color: #e3f2fd;
}
.col-narrow { max-width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-flex { max-width: 500px; }
.text-truncated { max-height: 3.2em; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.explorer-count-badge {
    display: inline-block; background: #e2e3e5; color: #333;
    border-radius: 12px; padding: 2px 10px; font-size: 0.8rem; font-weight: 500;
    margin-left: 8px;
}
</style>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Regulatory Obligation Control Mapper",
        page_icon="📋",
        layout="wide",
    )

    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    # Reset graph-module caches once per Streamlit session so the LLM client
    # picks up the latest env-var configuration (timeout, model, etc.).
    if "caches_initialised" not in st.session_state:
        reset_classify_caches()
        reset_assess_caches()
        st.session_state["caches_initialised"] = True

    st.title("📋 Regulatory Obligation Control Mapper")

    # ── Dynamic tabs driven by config/default.yaml → ui.visible_tabs ──
    tabs_to_show = _visible_tabs()
    tab_labels = [f"{_TAB_REGISTRY[t][0]} {t}" for t in tabs_to_show]
    tab_widgets = st.tabs(tab_labels)

    for tab_widget, tab_name in zip(tab_widgets, tabs_to_show):
        with tab_widget:
            _TAB_REGISTRY[tab_name][1]()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
