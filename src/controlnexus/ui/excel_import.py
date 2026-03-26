"""Excel import sub-tab — upload a register and get a proposed DomainConfig.

Flow: file upload → RegisterAnalyzer (heuristic) → ConfigProposerAgent (LLM)
→ validated DomainConfig → download YAML / use immediately.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from controlnexus.analysis.register_analyzer import RegisterSummary, analyze_register
from controlnexus.core.domain_config import DomainConfig

logger = logging.getLogger(__name__)


def _run_proposer(summary_dict: dict[str, Any]) -> dict[str, Any]:
    """Run the ConfigProposerAgent synchronously."""
    from controlnexus.agents.base import AgentContext
    from controlnexus.agents.config_proposer import ConfigProposerAgent
    from controlnexus.core.transport import build_client_from_env

    client = build_client_from_env()
    ctx = AgentContext(
        client=client,
        model=client.model if client else "none",
        temperature=0.2,
        max_tokens=4096,
        timeout_seconds=180,
    )
    agent = ConfigProposerAgent(ctx, name="ConfigProposer")
    result = asyncio.run(agent.execute(mode="full", register_summary=summary_dict))

    if client is not None:
        asyncio.run(client.close())

    return result


def render_excel_import() -> DomainConfig | None:
    """Render the Excel import sub-tab.

    Returns a validated DomainConfig if one has been proposed and accepted,
    otherwise None.
    """
    st.markdown(
        "Upload an existing controls register (Excel). The system will "
        "analyze the data and propose a configuration you can download or use directly."
    )

    uploaded = st.file_uploader(
        "Select Excel file",
        type=["xlsx", "xls"],
        key="ci_excel_upload",
        help="Upload an .xlsx file with your existing control register.",
    )

    if uploaded is None:
        # If user previously proposed a config, keep it available
        return _get_accepted_config()

    # Write to temp and analyze
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)

    try:
        summary = analyze_register(tmp_path)
        st.session_state["ci_register_summary"] = summary.model_dump()
    except Exception as e:
        st.error(f"Failed to parse Excel file: {e}")
        logger.exception("Register analysis error")
        return _get_accepted_config()
    finally:
        tmp_path.unlink(missing_ok=True)

    # ── Summary display ───────────────────────────────────────────────
    st.markdown("#### Register Summary")

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Rows", summary.row_count)
    mcol2.metric("Control Types", len(summary.unique_control_types))
    mcol3.metric("Business Units", len(summary.unique_business_units))
    mcol4.metric("Sections", len(summary.unique_sections))

    with st.expander("Detected Details", expanded=False):
        if summary.header_mapping:
            st.markdown("**Header Mapping** (detected → canonical):")
            for canonical, raw in summary.header_mapping.items():
                st.markdown(f"- `{raw}` → **{canonical}**")

        if summary.unique_control_types:
            st.markdown(f"**Control Types:** {', '.join(summary.unique_control_types)}")
        if summary.unique_placements:
            st.markdown(f"**Placements:** {', '.join(summary.unique_placements)}")
        if summary.unique_methods:
            st.markdown(f"**Methods:** {', '.join(summary.unique_methods)}")
        if summary.frequency_values:
            st.markdown(f"**Frequencies:** {', '.join(summary.frequency_values)}")
        if summary.role_mentions:
            st.markdown(f"**Roles:** {', '.join(list(summary.role_mentions)[:10])}")
        if summary.system_mentions:
            st.markdown(f"**Systems:** {', '.join(list(summary.system_mentions)[:10])}")

    # ── Propose config ────────────────────────────────────────────────
    if st.button("Propose Config", type="primary", key="ci_propose_btn"):
        with st.status("Analyzing register and proposing config\u2026", expanded=True) as status:
            summary_dict = st.session_state["ci_register_summary"]
            status.write("\U0001f50d Extracting patterns from register data\u2026")

            try:
                status.write("\U0001f916 Running ConfigProposerAgent\u2026")
                result = _run_proposer(summary_dict)
                config = DomainConfig(**result)
                st.session_state["ci_proposed_config"] = config.model_dump()
                status.update(label="\u2705 Config proposed successfully", state="complete")
            except Exception as e:
                status.update(label="\u274c Proposal failed", state="error")
                st.error(f"Config proposal failed: {e}")
                logger.exception("Config proposal error")
                return _get_accepted_config()

    # ── Show proposed config ──────────────────────────────────────────
    proposed_data = st.session_state.get("ci_proposed_config")
    if proposed_data is None:
        return _get_accepted_config()

    try:
        config = DomainConfig(**proposed_data)
    except Exception as e:
        st.error(f"Proposed config has validation errors: {e}")
        return None

    st.markdown("#### Proposed Config")
    st.success(
        f"**{config.name}** — {len(config.control_types)} types, "
        f"{len(config.business_units)} BUs, {len(config.process_areas)} sections"
    )

    # YAML download
    yaml_str = yaml.dump(proposed_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    col_dl, col_use = st.columns(2)
    with col_dl:
        st.download_button(
            "Download as YAML",
            data=yaml_str,
            file_name=f"{config.name}.yaml",
            mime="text/yaml",
            key="ci_download_yaml",
        )
    with col_use:
        if st.button("Use this config", type="primary", key="ci_use_config"):
            st.session_state["ci_accepted_config"] = proposed_data
            st.session_state["wizard_active_config"] = proposed_data
            st.success("Config activated! Scroll down to generate controls.")

    return _get_accepted_config()


def _get_accepted_config() -> DomainConfig | None:
    """Return the accepted config from session state, if any."""
    data = st.session_state.get("ci_accepted_config")
    if data is not None:
        try:
            return DomainConfig(**data)
        except Exception:
            return None
    return None
