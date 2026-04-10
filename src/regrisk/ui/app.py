"""
Streamlit 5-tab UI for the Regulatory Obligation Control Mapper.

Tab 1: Upload & Configure  (upload_tab.py)
Tab 2: Classification Review  (review_tabs.py)
Tab 3: Mapping Review  (review_tabs.py)
Tab 4: Results  (results_tab.py)
Tab 5: Traceability  (traceability_tab.py)

Shared helpers live in components.py.
Two graph invocations bridged via st.session_state.
Checkpoint persistence allows resuming after mid-run failures.
"""

from __future__ import annotations

import logging

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

from regrisk.graphs.classify_graph import reset_caches as reset_classify_caches
from regrisk.graphs.assess_graph import reset_caches as reset_assess_caches
from regrisk.ui.checkpoint import (
    STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED,
)
from regrisk.ui.components import pipeline_phase, phase_badge
from regrisk.ui.upload_tab import render_upload_tab
from regrisk.ui.review_tabs import (
    render_classification_review_tab,
    render_mapping_review_tab,
)
from regrisk.ui.results_tab import render_results_tab
from regrisk.ui.traceability_tab import render_traceability_tab


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
    st.caption("Map regulatory obligations → APQC processes → control coverage → risk scoring")

    # ── Pipeline status bar ──
    phase = pipeline_phase()
    status_cols = st.columns(4)
    with status_cols[0]:
        st.markdown(phase_badge("Classification", phase in (STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED)))
    with status_cols[1]:
        st.markdown(phase_badge("APQC Mapping", phase in (STAGE_MAPPED, STAGE_ASSESSED)))
    with status_cols[2]:
        st.markdown(phase_badge("Coverage & Risk", phase == STAGE_ASSESSED))
    with status_cols[3]:
        reg = st.session_state.get("regulation_name", "")
        if reg:
            st.markdown(f"📜 *{reg}*")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📁 Upload & Configure",
        "🏷️ Classification Review",
        "🗺️ Mapping Review",
        "📊 Results",
        "🔗 Traceability",
    ])

    with tab1:
        render_upload_tab()
    with tab2:
        render_classification_review_tab()
    with tab3:
        render_mapping_review_tab()
    with tab4:
        render_results_tab()
    with tab5:
        render_traceability_tab()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
