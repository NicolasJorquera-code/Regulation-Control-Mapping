"""Agent Playground: interactive testing environment for ControlNexus agents.

Allows users to select any registered agent, provide sample input,
execute the agent, and view results.
"""

from __future__ import annotations

import asyncio
import json
import logging

import streamlit as st

from controlnexus.agents import AGENT_REGISTRY, AgentContext
from controlnexus.core.transport import build_client_from_env

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample inputs — must match each agent's execute() keyword-only args exactly.
# ---------------------------------------------------------------------------

_SAMPLE_INPUTS: dict[str, dict] = {
    # SpecAgent.execute(*, leaf, control_type, type_definition, registry,
    #   placement_defs, method_defs, taxonomy_constraints, diversity_context)
    "SpecAgent": {
        "leaf": {
            "hierarchy_id": "4.1.1.1",
            "name": "Develop procurement plan",
            "depth": 4,
            "top_section": "4",
            "is_leaf": True,
        },
        "control_type": "Reconciliation",
        "type_definition": "Comparison of two or more data sets to identify and resolve differences.",
        "registry": {
            "roles": ["Senior Accountant", "Procurement Analyst", "Control Owner"],
            "systems": ["SAP Financial Close Platform", "Oracle EBS", "Workiva"],
            "regulatory_frameworks": ["SOX", "Basel III"],
            "evidence_artifacts": [
                "Reconciliation report with preparer sign-off retained in financial close platform"
            ],
        },
        "placement_defs": {
            "placements": ["Preventive", "Detective", "Corrective"],
        },
        "method_defs": {
            "methods": ["Manual", "Automated", "Semi-automated"],
        },
        "taxonomy_constraints": {
            "level_1_options": ["Preventive", "Detective", "Corrective"],
            "allowed_level_2_for_selected_level_1": [
                "Reconciliation", "Variance Analysis", "Exception Monitoring",
            ],
        },
        "diversity_context": {
            "available_business_units": [
                {"business_unit_id": "BU-011", "name": "Finance/Accounting"},
                {"business_unit_id": "BU-007", "name": "Operations"},
            ],
            "suggested_business_unit": "BU-011",
        },
    },

    # NarrativeAgent.execute(*, locked_spec, standards, phrase_bank_cfg,
    #   exemplars, regulatory_context, retry_appendix=None)
    "NarrativeAgent": {
        "locked_spec": {
            "hierarchy_id": "4.1.1.1",
            "leaf_name": "Develop procurement plan",
            "selected_level_1": "Detective",
            "control_type": "Reconciliation",
            "placement": "Detective",
            "method": "Manual",
            "who": "Senior Accountant",
            "what_action": "Reconciles general ledger accounts",
            "what_detail": "against subsidiary ledger balances",
            "when": "Monthly within 5 business days of month-end",
            "where_system": "SAP Financial Close Platform",
            "why_risk": "Unreconciled account balances",
            "evidence": "Reconciliation report with preparer sign-off retained in financial close platform",
            "business_unit_id": "BU-011",
        },
        "standards": {
            "who": "Must be a specific role title, not a generic term.",
            "what": "Must contain exactly one primary action verb.",
            "when": "Must be a specific frequency with timing details.",
            "where": "Must name a specific system or platform.",
            "why": "Must reference a specific risk or compliance requirement.",
        },
        "phrase_bank_cfg": {
            "action_verbs": ["reconciles", "reviews", "approves", "validates", "monitors"],
            "risk_phrases": ["to prevent", "to mitigate", "to ensure", "to detect"],
        },
        "exemplars": [
            {
                "full_description": (
                    "Monthly, the Senior Accountant reconciles general ledger accounts "
                    "in the SAP Financial Close Platform by reviewing outstanding items "
                    "to prevent unreconciled balances and ensure SOX compliance."
                ),
            }
        ],
        "regulatory_context": ["SOX Section 404", "Basel III"],
    },

    # EnricherAgent.execute(*, validated_control, rating_criteria_cfg, nearest_neighbors)
    "EnricherAgent": {
        "validated_control": {
            "hierarchy_id": "4.1.1.1",
            "who": "Senior Accountant",
            "what": "Reconciles general ledger accounts against subsidiary ledger balances",
            "when": "Monthly within 5 business days of period close",
            "where": "SAP Financial Close Platform",
            "why": "To prevent unreconciled balances and ensure SOX compliance",
            "full_description": (
                "Monthly, the Senior Accountant reconciles general ledger accounts "
                "in the SAP Financial Close Platform by reviewing outstanding items "
                "and investigating discrepancies to prevent unreconciled account "
                "balances and ensure regulatory compliance with SOX requirements "
                "for timely and accurate financial reporting."
            ),
        },
        "rating_criteria_cfg": {
            "Strong": "All 5W specific, audit-grade evidence, 40-60 words.",
            "Effective": "All 5W present, good evidence, 30-70 words.",
            "Satisfactory": "All 5W present, adequate detail, 30-80 words.",
            "Needs Improvement": "One or more 5W vague or generic.",
            "Weak": "Multiple 5W missing or placeholder text.",
        },
        "nearest_neighbors": [
            {
                "control_id": "CTRL-0901-REC-001",
                "full_description": (
                    "Senior Accountant reconciles intercompany balances monthly "
                    "within 5 business days of month-end in Oracle EBS General Ledger "
                    "to prevent undetected intercompany discrepancies."
                ),
            }
        ],
    },

    # AdversarialReviewer.execute(**kwargs)  — uses kwargs.get("control"), kwargs.get("spec")
    "AdversarialReviewer": {
        "control": {
            "who": "Analyst",
            "what": "Reviews transactions",
            "when": "Monthly",
            "where": "Enterprise System",
            "why": "Risk mitigation",
            "full_description": (
                "The analyst reviews transactions monthly in the "
                "enterprise system for risk mitigation."
            ),
        },
        "spec": {
            "who": "Senior Analyst",
            "where_system": "SAP",
        },
    },

    # DifferentiationAgent.execute(**kwargs)  — uses kwargs.get("control"), etc.
    "DifferentiationAgent": {
        "control": {
            "who": "Accountant",
            "what": "Reconciles accounts",
            "when": "Monthly",
            "where": "GL System",
            "why": "Prevent errors",
            "full_description": (
                "The accountant reconciles accounts monthly in the "
                "GL system to prevent errors."
            ),
        },
        "existing_control": (
            "The accountant reconciles accounts monthly in the "
            "GL system to prevent errors."
        ),
        "spec": {},
    },
}


def render_playground() -> None:
    """Render the interactive agent playground."""
    agent_names = sorted(AGENT_REGISTRY.keys())

    if not agent_names:
        st.warning("No agents registered.")
        return

    # Agent selector
    st.markdown("### Select Agent")

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_agent = st.selectbox(
            "Choose an agent to test",
            options=agent_names,
            key="playground_agent_select",
        )

    with col2:
        agent_cls = AGENT_REGISTRY.get(selected_agent)
        if agent_cls:
            st.info(f"**Class:** `{agent_cls.__name__}`")

    # Detect agent change and refresh sample data automatically
    if st.session_state.get("_playground_last_agent") != selected_agent:
        st.session_state["_playground_last_agent"] = selected_agent
        st.session_state.pop("playground_last_result", None)

    # Handle "Reset to Sample" — must clear BEFORE the widget is instantiated
    reset_key = f"_playground_reset_{selected_agent}"
    if st.session_state.pop(reset_key, False):
        st.session_state.pop(f"playground_input_json_{selected_agent}", None)

    st.markdown("---")

    # Input data — always derive fresh default from selected agent
    st.markdown("### Input Data")
    st.caption("Edit the JSON below to customise the agent's input.")

    sample = _SAMPLE_INPUTS.get(selected_agent, {"note": "Provide agent-specific input"})
    default_json = json.dumps(sample, indent=2)

    input_json_str = st.text_area(
        "Agent Input (JSON)",
        value=default_json,
        height=320,
        key=f"playground_input_json_{selected_agent}",
    )

    col_gen, col_run = st.columns(2)
    with col_gen:
        if st.button("Reset to Sample", width="stretch"):
            st.session_state[reset_key] = True
            st.rerun()

    with col_run:
        run_agent = st.button("Run Agent", type="primary", width="stretch")

    st.markdown("---")

    # Output
    st.markdown("### Output")

    if run_agent:
        _execute_agent(selected_agent, input_json_str)
    elif "playground_last_result" in st.session_state:
        st.info("Showing last result. Click **Run Agent** to execute again.")
        _display_result(st.session_state["playground_last_result"])
    else:
        st.markdown(
            '<div class="playground-output">'
            '<span style="color:#6f6f6f;">Click "Run Agent" to see output...</span>'
            "</div>",
            unsafe_allow_html=True,
        )


def _execute_agent(agent_name: str, input_json_str: str) -> None:
    """Parse input, run the agent, and display results."""
    try:
        input_data = json.loads(input_json_str)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
        return

    agent_cls = AGENT_REGISTRY.get(agent_name)
    if not agent_cls:
        st.error(f"Agent '{agent_name}' not found in registry.")
        return

    client = build_client_from_env()
    ctx = AgentContext(client=client)
    agent = agent_cls(ctx)

    status = st.status(f"Running {agent_name}...", expanded=True)

    try:
        status.write(f"Executing `{agent_name}.execute()`...")

        # All agents are async
        result = asyncio.run(agent.execute(**input_data))

        status.update(label=f"{agent_name} completed", state="complete", expanded=False)

        st.session_state["playground_last_result"] = result
        _display_result(result)

    except Exception as e:
        status.update(label=f"{agent_name} failed", state="error")
        st.error(f"Error: {e}")
        logger.exception("Playground agent error")


def _display_result(result: dict) -> None:
    """Render agent result in formatted and raw views."""
    with st.expander("Formatted Result", expanded=True):
        for key, value in result.items():
            st.markdown(f"**{key.replace('_', ' ').title()}:**")
            if isinstance(value, list):
                if not value:
                    st.write("(empty)")
                elif isinstance(value[0], dict):
                    for i, item in enumerate(value[:10]):
                        with st.expander(f"Item {i + 1}", expanded=False):
                            st.json(item)
                    if len(value) > 10:
                        st.caption(f"... and {len(value) - 10} more")
                else:
                    for item in value[:10]:
                        st.write(f"- {item}")
            elif isinstance(value, dict):
                st.json(value)
            else:
                st.write(value)

    with st.expander("Raw JSON", expanded=False):
        st.json(result)

    st.download_button(
        "Download Result (JSON)",
        data=json.dumps(result, indent=2),
        file_name="agent_result.json",
        mime="application/json",
        width="stretch",
    )