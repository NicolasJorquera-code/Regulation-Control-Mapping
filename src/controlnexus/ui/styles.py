"""IBM Carbon Design System CSS styles for ControlNexus Streamlit dashboard.

Self-contained CSS (no external token imports) following IBM Carbon
Design System guidelines with IBM Plex Sans typography.
"""

from __future__ import annotations

import streamlit as st


# -- Design Tokens (inline) ---------------------------------------------------

_COLORS = {
    "text_primary": "#161616",
    "text_secondary": "#525252",
    "text_inverse": "#ffffff",
    "ui_background": "#ffffff",
    "ui_01": "#f4f4f4",
    "ui_02": "#e0e0e0",
    "ui_03": "#c6c6c6",
    "interactive_01": "#0f62fe",
    "hover_primary": "#0353e9",
    "hover_ui": "#e5e5e5",
    "focus": "#0f62fe",
    "link_primary": "#0f62fe",
    "support_success": "#24a148",
    "support_warning": "#f1c21b",
    "support_error": "#da1e28",
    "support_info": "#0043ce",
    "tag_blue": "#0f62fe",
    "tag_gray": "#a8a8a8",
    "tag_teal": "#009d9a",
    "tag_purple": "#8a3ffc",
    "tag_green": "#24a148",
    "tag_red": "#da1e28",
    "tag_magenta": "#d02670",
    "tag_cyan": "#0072c3",
}

_SPACING = {
    "01": "0.125rem",
    "02": "0.25rem",
    "03": "0.5rem",
    "04": "0.75rem",
    "05": "1rem",
    "06": "1.5rem",
    "07": "2rem",
}

_TYPOGRAPHY = {
    "font_family": "'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif",
    "font_family_mono": "'IBM Plex Mono', 'Menlo', monospace",
    "size_01": "0.75rem",
    "size_02": "0.875rem",
    "size_03": "1rem",
    "size_04": "1.125rem",
    "size_05": "1.25rem",
    "size_08": "2.25rem",
    "size_10": "2.625rem",
    "weight_light": 300,
    "weight_regular": 400,
    "weight_medium": 500,
    "weight_semibold": 600,
}


def load_custom_css() -> None:
    """Inject IBM Carbon Design CSS into the Streamlit page."""
    css = f"""
    <style>
    /* === Font Import === */
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap');

    /* === Base === */
    html, body, [class*="css"] {{
        font-family: {_TYPOGRAPHY["font_family"]};
        color: {_COLORS["text_primary"]};
        background-color: {_COLORS["ui_background"]};
    }}

    /* === Header / Masthead === */
    .cn-header {{
        display: flex;
        align-items: center;
        height: 3rem;
        background-color: {_COLORS["text_primary"]};
        color: {_COLORS["text_inverse"]};
        padding: 0 {_SPACING["05"]};
        margin: -{_SPACING["05"]} -{_SPACING["05"]} {_SPACING["05"]} -{_SPACING["05"]};
        position: sticky;
        top: 0;
        z-index: 1000;
    }}
    .cn-header__brand {{
        display: flex;
        align-items: center;
        gap: {_SPACING["03"]};
        padding-right: {_SPACING["07"]};
        border-right: 1px solid {_COLORS["text_secondary"]};
    }}
    .cn-header__name {{
        font-size: {_TYPOGRAPHY["size_03"]};
        font-weight: {_TYPOGRAPHY["weight_semibold"]};
        color: {_COLORS["text_inverse"]};
        letter-spacing: 0.1px;
    }}

    /* === Report Title === */
    .report-title {{
        font-size: {_TYPOGRAPHY["size_10"]};
        font-weight: {_TYPOGRAPHY["weight_light"]};
        margin-bottom: {_SPACING["02"]};
        line-height: 1.2;
    }}
    .report-subtitle {{
        color: {_COLORS["text_secondary"]};
        font-size: {_TYPOGRAPHY["size_04"]};
        margin-bottom: {_SPACING["07"]};
        border-bottom: 1px solid {_COLORS["ui_03"]};
        padding-bottom: {_SPACING["05"]};
    }}

    /* === Carbon Tile === */
    .carbon-tile {{
        background-color: {_COLORS["ui_01"]};
        border: 1px solid {_COLORS["ui_03"]};
        padding: {_SPACING["05"]};
        margin-bottom: {_SPACING["05"]};
        min-height: 120px;
        border-radius: 4px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        transition: all 0.15s ease;
    }}
    .carbon-tile:hover {{
        background-color: {_COLORS["hover_ui"]};
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    }}

    /* === Metric Display === */
    .metric-label {{
        font-size: {_TYPOGRAPHY["size_02"]};
        color: {_COLORS["text_secondary"]};
        letter-spacing: 0.1px;
        margin-bottom: {_SPACING["04"]};
        text-transform: uppercase;
    }}
    .metric-value {{
        font-size: {_TYPOGRAPHY["size_08"]};
        font-weight: {_TYPOGRAPHY["weight_light"]};
        color: {_COLORS["interactive_01"]};
    }}

    /* === Carbon Tags === */
    .carbon-tag {{
        display: inline-block;
        padding: {_SPACING["02"]} {_SPACING["04"]};
        border-radius: 24px;
        font-size: {_TYPOGRAPHY["size_01"]};
        font-weight: {_TYPOGRAPHY["weight_semibold"]};
        margin-right: {_SPACING["03"]};
        letter-spacing: 0.1px;
    }}
    .tag-blue {{ background-color: {_COLORS["tag_blue"]}; color: white; }}
    .tag-gray {{ background-color: {_COLORS["tag_gray"]}; color: {_COLORS["text_primary"]}; }}
    .tag-teal {{ background-color: {_COLORS["tag_teal"]}; color: white; }}
    .tag-purple {{ background-color: {_COLORS["tag_purple"]}; color: white; }}
    .tag-green {{ background-color: {_COLORS["tag_green"]}; color: white; }}
    .tag-red {{ background-color: {_COLORS["tag_red"]}; color: white; }}
    .tag-magenta {{ background-color: {_COLORS["tag_magenta"]}; color: white; }}
    .tag-cyan {{ background-color: {_COLORS["tag_cyan"]}; color: white; }}

    /* === Score Card === */
    .score-card {{
        text-align: center;
        padding: {_SPACING["05"]};
    }}
    .score-card .score-value {{
        font-size: 2.5rem;
        font-weight: {_TYPOGRAPHY["weight_light"]};
    }}
    .score-card .score-label {{
        font-size: {_TYPOGRAPHY["size_02"]};
        color: {_COLORS["text_secondary"]};
        text-transform: uppercase;
        letter-spacing: 0.1px;
    }}

    /* === Upload Section === */
    .upload-section {{
        background-color: {_COLORS["ui_01"]};
        border: 2px dashed {_COLORS["ui_03"]};
        border-radius: 4px;
        padding: {_SPACING["07"]};
        text-align: center;
        transition: border-color 0.15s ease;
    }}
    .upload-section:hover {{
        border-color: {_COLORS["interactive_01"]};
    }}

    /* === Playground === */
    .playground-output {{
        background-color: {_COLORS["text_primary"]};
        color: {_COLORS["support_success"]};
        font-family: {_TYPOGRAPHY["font_family_mono"]};
        font-size: {_TYPOGRAPHY["size_02"]};
        padding: {_SPACING["05"]};
        border-radius: 4px;
        max-height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
    }}
    .playground-stream-item {{
        padding: {_SPACING["02"]} 0;
        border-bottom: 1px solid #333;
    }}
    .playground-stream-item.success {{ color: {_COLORS["support_success"]}; }}
    .playground-stream-item.error {{ color: {_COLORS["support_error"]}; }}
    .playground-stream-item.info {{ color: {_COLORS["support_info"]}; }}

    /* === Button Override === */
    .stButton button {{
        background-color: {_COLORS["interactive_01"]} !important;
        color: {_COLORS["text_inverse"]} !important;
        border-radius: 4px !important;
        height: 3rem;
        font-weight: {_TYPOGRAPHY["weight_medium"]} !important;
        padding: 0 {_SPACING["05"]} !important;
        border: none !important;
        transition: background-color 0.15s ease !important;
    }}
    .stButton button:hover {{
        background-color: {_COLORS["hover_primary"]} !important;
    }}

    /* === Expander Override === */
    div[data-testid="stExpander"] {{
        border: none;
        background-color: {_COLORS["ui_01"]};
        border-bottom: 1px solid {_COLORS["ui_03"]};
        border-radius: 0;
    }}
    div[data-testid="stExpander"] summary {{
        font-weight: {_TYPOGRAPHY["weight_medium"]};
    }}

    /* === Text Area Override === */
    .stTextArea textarea {{
        font-family: {_TYPOGRAPHY["font_family_mono"]};
        font-size: {_TYPOGRAPHY["size_02"]};
        border: 1px solid {_COLORS["ui_03"]} !important;
        border-radius: 4px !important;
    }}

    /* === ControlForge Affinity Badges === */
    .affinity-high {{ background-color: #198038; color: white; }}
    .affinity-medium {{ background-color: {_COLORS["support_warning"]}; color: {_COLORS["text_primary"]}; }}
    .affinity-low {{ background-color: {_COLORS["ui_02"]}; color: {_COLORS["text_secondary"]}; }}
    .affinity-none {{ background-color: {_COLORS["ui_01"]}; color: {_COLORS["tag_gray"]}; }}

    /* === Status Indicators === */
    .status-success {{ color: {_COLORS["support_success"]}; }}
    .status-error {{ color: {_COLORS["support_error"]}; }}
    .status-warning {{ color: {_COLORS["support_warning"]}; }}
    .status-info {{ color: {_COLORS["support_info"]}; }}

    /* === Wizard Step Indicator === */
    .wizard-step {{
        padding: {_SPACING["03"]} {_SPACING["05"]};
        border-radius: 4px;
        margin-bottom: {_SPACING["02"]};
        font-size: {_TYPOGRAPHY["size_02"]};
    }}
    .wizard-step.active {{
        background-color: {_COLORS["interactive_01"]};
        color: {_COLORS["text_inverse"]};
        font-weight: {_TYPOGRAPHY["weight_medium"]};
    }}

    /* === Metric with Border === */
    .cn-metric-bordered {{
        border-left: 3px solid {_COLORS["interactive_01"]};
        padding-left: {_SPACING["04"]};
    }}

    /* === Template Card === */
    .template-card {{
        background-color: {_COLORS["ui_01"]};
        border: 1px solid {_COLORS["ui_03"]};
        border-radius: 4px;
        padding: {_SPACING["05"]};
        transition: border-color 0.15s ease;
    }}
    .template-card:hover {{
        border-color: {_COLORS["interactive_01"]};
    }}

    /* === Form Spacing === */
    .form-section {{
        margin-bottom: {_SPACING["06"]};
    }}

    /* === Hide Streamlit Branding === */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def get_masthead_html(active_tab: str = "Control Builder") -> str:
    """Generate the Carbon masthead header HTML."""
    tabs = ["Risk Inventory Builder", "Control Builder", "ControlForge Modular", "Analysis", "Playground"]
    nav_items = []
    for tab in tabs:
        cls = "active" if tab == active_tab else ""
        nav_items.append(f'<span class="cn-header__nav-item {cls}">{tab}</span>')
    nav_html = "\n".join(nav_items)
    return f"""
    <header class="cn-header">
        <div class="cn-header__brand">
            <span class="cn-header__name">ControlNexus</span>
        </div>
        <nav style="display:flex;align-items:center;margin-left:1rem;gap:0.25rem;">
            {nav_html}
        </nav>
    </header>
    """


def score_color(score: float, max_score: float = 100.0) -> str:
    """Return a hex color based on a score percentage."""
    pct = (score / max_score * 100) if max_score else 0
    if pct >= 80:
        return _COLORS["support_success"]
    if pct >= 50:
        return _COLORS["support_warning"]
    return _COLORS["support_error"]
