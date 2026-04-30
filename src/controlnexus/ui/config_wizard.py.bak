"""Config Wizard — 6-step guided form for building a DomainConfig from scratch.

Steps:
  1. Basics (name, description)
  2. Control Types (dynamic list with LLM auto-fill)
  3. Business Units (dynamic list)
  4. Process Areas (risk profiles, affinity grids, registries, exemplars)
  5. Narrative & Quality (narrative fields, placements, methods, frequencies)
  6. Review & Export (validate, download YAML, use immediately)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import streamlit as st
import yaml

from controlnexus.core.domain_config import DomainConfig

logger = logging.getLogger(__name__)

TOTAL_STEPS = 6
STEP_LABELS = [
    "Basics",
    "Control Types",
    "Business Units",
    "Process Areas",
    "Narrative & Quality",
    "Review & Export",
]

# Default placements, methods, frequency tiers, quality ratings to pre-fill step 5
_DEFAULT_PLACEMENTS = ["Preventive", "Detective", "Contingency Planning"]
_DEFAULT_METHODS = ["Automated", "Manual", "Automated with Manual Component"]
_DEFAULT_FREQUENCY_TIERS = [
    {"label": "Daily", "rank": 1, "keywords": ["daily", "every day", "eod"]},
    {"label": "Weekly", "rank": 2, "keywords": ["weekly", "every week"]},
    {"label": "Monthly", "rank": 3, "keywords": ["monthly", "every month", "month-end"]},
    {"label": "Quarterly", "rank": 4, "keywords": ["quarterly", "every quarter"]},
    {"label": "Semi-Annual", "rank": 5, "keywords": ["semi-annual", "twice a year"]},
    {"label": "Annual", "rank": 6, "keywords": ["annual", "annually", "yearly"]},
]
_DEFAULT_QUALITY_RATINGS = ["Strong", "Effective", "Satisfactory", "Needs Improvement"]
_DEFAULT_NARRATIVE_FIELDS = [
    {"name": "who", "definition": "The specific role responsible for performing the control", "required": True},
    {"name": "what", "definition": "The specific action performed", "required": True},
    {"name": "when", "definition": "The timing or trigger for the control", "required": True},
    {"name": "where", "definition": "The system or location where the control is performed", "required": True},
    {"name": "why", "definition": "The risk or objective the control addresses", "required": True},
    {"name": "full_description", "definition": "Prose narrative incorporating all fields", "required": True},
]
_AFFINITY_LEVELS = ["HIGH", "MEDIUM", "LOW", "NONE"]


# ── Session state helpers ─────────────────────────────────────────────────────


def _get_form() -> dict[str, Any]:
    """Return the wizard form data dict, initialising if needed."""
    if "wizard_form" not in st.session_state:
        st.session_state["wizard_form"] = {
            "name": "",
            "description": "",
            "control_types": [],
            "business_units": [],
            "process_areas": [],
            "placements": [{"name": p, "description": ""} for p in _DEFAULT_PLACEMENTS],
            "methods": [{"name": m, "description": ""} for m in _DEFAULT_METHODS],
            "frequency_tiers": list(_DEFAULT_FREQUENCY_TIERS),
            "quality_ratings": list(_DEFAULT_QUALITY_RATINGS),
            "narrative": {
                "fields": list(_DEFAULT_NARRATIVE_FIELDS),
                "word_count_min": 30,
                "word_count_max": 80,
            },
        }
    return st.session_state["wizard_form"]


def _get_step() -> int:
    return st.session_state.get("wizard_step", 1)


def _set_step(step: int) -> None:
    st.session_state["wizard_step"] = max(1, min(step, TOTAL_STEPS))


def _auto_code(name: str) -> str:
    """Generate a 3-letter code from consonants."""
    consonants = re.sub(r"[aeiouAEIOU\s\-,]", "", name)
    return consonants[:3].upper() or "UNK"


# ── LLM helpers ───────────────────────────────────────────────────────────────


def _run_section_autofill(section_name: str, control_type_names: list[str], config_context: dict) -> dict[str, Any]:
    """Run ConfigProposerAgent in section_autofill mode synchronously."""
    from controlnexus.agents.base import AgentContext
    from controlnexus.agents.config_proposer import ConfigProposerAgent
    from controlnexus.core.transport import build_client_from_env

    client = build_client_from_env()
    ctx = AgentContext(
        client=client,
        model=client.model if client else "none",
        temperature=0.2,
        max_tokens=2048,
        timeout_seconds=120,
    )
    agent = ConfigProposerAgent(ctx, name="ConfigProposer-Section")
    result = asyncio.run(
        agent.execute(
            mode="section_autofill",
            section_name=section_name,
            control_type_names=control_type_names,
            config_context=config_context,
        )
    )
    if client is not None:
        asyncio.run(client.close())
    return result


def _run_enrich(type_names: list[str]) -> dict[str, Any]:
    """Run ConfigProposerAgent in enrich mode synchronously."""
    from controlnexus.agents.base import AgentContext
    from controlnexus.agents.config_proposer import ConfigProposerAgent
    from controlnexus.core.transport import build_client_from_env

    client = build_client_from_env()
    ctx = AgentContext(
        client=client,
        model=client.model if client else "none",
        temperature=0.2,
        max_tokens=2048,
        timeout_seconds=120,
    )
    agent = ConfigProposerAgent(ctx, name="ConfigProposer-Enrich")
    result = asyncio.run(agent.execute(mode="enrich", type_names=type_names))
    if client is not None:
        asyncio.run(client.close())
    return result


# ── Step renderers ────────────────────────────────────────────────────────────


def _render_sidebar(current_step: int) -> None:
    """Render the step progress sidebar."""
    for i in range(1, TOTAL_STEPS + 1):
        if i < current_step:
            icon = "\u2705"
        elif i == current_step:
            icon = "\u25cf"
        else:
            icon = "\u25cb"

        label = f"{icon} Step {i}: {STEP_LABELS[i - 1]}"
        if i <= current_step:
            if st.button(label, key=f"wiz_nav_{i}", use_container_width=True):
                _set_step(i)
                st.rerun()
        else:
            st.markdown(f"<div style='padding:6px 12px;color:#a8a8a8;'>{label}</div>", unsafe_allow_html=True)


def _render_step_basics(form: dict[str, Any]) -> None:
    """Step 1: Config name and description."""
    st.markdown("#### Step 1: Basics")
    st.caption("Name your configuration and provide a brief description.")

    form["name"] = st.text_input(
        "Config Name",
        value=form.get("name", ""),
        placeholder="e.g. community-bank-demo",
        key="wiz_name",
    )
    form["description"] = st.text_area(
        "Description",
        value=form.get("description", ""),
        placeholder="Brief description of the organization and control domain.",
        key="wiz_desc",
        height=100,
    )

    if st.button("Next \u2192", type="primary", key="wiz_step1_next"):
        if not form["name"].strip():
            st.error("Config name is required.")
        else:
            _set_step(2)
            st.rerun()


def _render_step_control_types(form: dict[str, Any]) -> None:
    """Step 2: Define control types."""
    st.markdown("#### Step 2: Control Types")
    st.caption("Define the control types in your taxonomy. At least one is required.")

    types_list: list[dict[str, Any]] = form.setdefault("control_types", [])

    # Add button
    col_add, col_ai = st.columns([1, 1])
    with col_add:
        if st.button("\u2795 Add Control Type", key="wiz_add_ct"):
            types_list.append(
                {
                    "name": "",
                    "definition": "",
                    "code": "",
                    "min_frequency_tier": None,
                    "placement_categories": [],
                    "evidence_criteria": [],
                }
            )
            st.rerun()
    with col_ai:
        if st.button("\U0001f916 Auto-fill Definitions with AI", key="wiz_enrich_ct"):
            names = [ct["name"] for ct in types_list if ct.get("name")]
            if names:
                with st.status("Enriching control types\u2026", expanded=True) as status:
                    try:
                        enriched = _run_enrich(names)
                        enriched_types = {ct["name"]: ct for ct in enriched.get("control_types", [])}
                        for ct in types_list:
                            if ct["name"] in enriched_types:
                                enr = enriched_types[ct["name"]]
                                if not ct.get("definition"):
                                    ct["definition"] = enr.get("definition", "")
                                if not ct.get("code"):
                                    ct["code"] = enr.get("code", "")
                                if not ct.get("evidence_criteria"):
                                    ct["evidence_criteria"] = enr.get("evidence_criteria", [])
                                if ct.get("min_frequency_tier") is None:
                                    ct["min_frequency_tier"] = enr.get("min_frequency_tier")
                                if not ct.get("placement_categories"):
                                    ct["placement_categories"] = enr.get("placement_categories", [])
                        status.update(label="\u2705 Enrichment complete", state="complete")
                    except Exception as e:
                        status.update(label="\u274c Enrichment failed", state="error")
                        st.error(str(e))
                st.rerun()
            else:
                st.warning("Add at least one control type name first.")

    # Existing placement names for multiselect
    placement_names = [p["name"] for p in form.get("placements", _DEFAULT_PLACEMENTS) if isinstance(p, dict)]
    if not placement_names:
        placement_names = _DEFAULT_PLACEMENTS
    freq_options = [None, "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual"]

    # Render each control type
    to_remove = []
    for i, ct in enumerate(types_list):
        with st.expander(f"Control Type {i + 1}: {ct.get('name', '(unnamed)')}", expanded=not ct.get("name")):
            ct["name"] = st.text_input("Name", value=ct.get("name", ""), key=f"wiz_ct_name_{i}")
            ct["definition"] = st.text_area(
                "Definition", value=ct.get("definition", ""), key=f"wiz_ct_def_{i}", height=80
            )

            c1, c2 = st.columns(2)
            with c1:
                ct["code"] = st.text_input(
                    "Code (3 letters)",
                    value=ct.get("code", "") or _auto_code(ct.get("name", "")),
                    max_chars=3,
                    key=f"wiz_ct_code_{i}",
                )
            with c2:
                current_freq = ct.get("min_frequency_tier")
                freq_idx = freq_options.index(current_freq) if current_freq in freq_options else 0
                ct["min_frequency_tier"] = st.selectbox(
                    "Min Frequency Tier",
                    options=freq_options,
                    index=freq_idx,
                    format_func=lambda x: x or "None",
                    key=f"wiz_ct_freq_{i}",
                )

            ct["placement_categories"] = st.multiselect(
                "Placement Categories",
                options=placement_names,
                default=[p for p in ct.get("placement_categories", []) if p in placement_names],
                key=f"wiz_ct_place_{i}",
            )

            evidence_text = "\n".join(ct.get("evidence_criteria", []))
            evidence_input = st.text_area(
                "Evidence Criteria (one per line)",
                value=evidence_text,
                key=f"wiz_ct_evid_{i}",
                height=80,
            )
            ct["evidence_criteria"] = [line.strip() for line in evidence_input.split("\n") if line.strip()]

            if st.button(f"\U0001f5d1 Remove", key=f"wiz_ct_rm_{i}"):
                to_remove.append(i)

    for idx in reversed(to_remove):
        types_list.pop(idx)
    if to_remove:
        st.rerun()

    # Navigation
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", key="wiz_step2_back"):
            _set_step(1)
            st.rerun()
    with col_next:
        if st.button("Next \u2192", type="primary", key="wiz_step2_next"):
            valid_types = [ct for ct in types_list if ct.get("name", "").strip()]
            if not valid_types:
                st.error("At least one control type with a name is required.")
            else:
                form["control_types"] = valid_types
                _set_step(3)
                st.rerun()


def _render_step_business_units(form: dict[str, Any]) -> None:
    """Step 3: Define business units."""
    st.markdown("#### Step 3: Business Units")
    st.caption("Define business units (optional). You can skip this step.")

    bu_list: list[dict[str, Any]] = form.setdefault("business_units", [])
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name")]
    section_ids = [pa["id"] for pa in form.get("process_areas", []) if pa.get("id")]

    if st.button("\u2795 Add Business Unit", key="wiz_add_bu"):
        next_num = len(bu_list) + 1
        bu_list.append(
            {
                "id": f"BU-{next_num:03d}",
                "name": "",
                "description": "",
                "primary_sections": [],
                "key_control_types": [],
                "regulatory_exposure": [],
            }
        )
        st.rerun()

    to_remove = []
    for i, bu in enumerate(bu_list):
        with st.expander(f"Business Unit {i + 1}: {bu.get('name', '(unnamed)')}", expanded=not bu.get("name")):
            c1, c2 = st.columns(2)
            with c1:
                bu["id"] = st.text_input("ID", value=bu.get("id", f"BU-{i + 1:03d}"), key=f"wiz_bu_id_{i}")
            with c2:
                bu["name"] = st.text_input("Name", value=bu.get("name", ""), key=f"wiz_bu_name_{i}")

            bu["description"] = st.text_area(
                "Description", value=bu.get("description", ""), key=f"wiz_bu_desc_{i}", height=60
            )

            if section_ids:
                bu["primary_sections"] = st.multiselect(
                    "Primary Sections",
                    options=section_ids,
                    default=[s for s in bu.get("primary_sections", []) if s in section_ids],
                    key=f"wiz_bu_sec_{i}",
                )
            else:
                sec_text = st.text_input(
                    "Primary Sections (comma-separated IDs)",
                    value=", ".join(bu.get("primary_sections", [])),
                    key=f"wiz_bu_sec_txt_{i}",
                )
                bu["primary_sections"] = [s.strip() for s in sec_text.split(",") if s.strip()]

            bu["key_control_types"] = st.multiselect(
                "Key Control Types",
                options=type_names,
                default=[t for t in bu.get("key_control_types", []) if t in type_names],
                key=f"wiz_bu_types_{i}",
            )

            reg_text = st.text_input(
                "Regulatory Exposure (comma-separated)",
                value=", ".join(bu.get("regulatory_exposure", [])),
                key=f"wiz_bu_reg_{i}",
            )
            bu["regulatory_exposure"] = [r.strip() for r in reg_text.split(",") if r.strip()]

            if st.button(f"\U0001f5d1 Remove", key=f"wiz_bu_rm_{i}"):
                to_remove.append(i)

    for idx in reversed(to_remove):
        bu_list.pop(idx)
    if to_remove:
        st.rerun()

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", key="wiz_step3_back"):
            _set_step(2)
            st.rerun()
    with col_next:
        if st.button("Next \u2192", type="primary", key="wiz_step3_next"):
            form["business_units"] = bu_list
            _set_step(4)
            st.rerun()


def _render_step_process_areas(form: dict[str, Any]) -> None:
    """Step 4: Define process areas with risk profiles, affinity, registries, exemplars."""
    st.markdown("#### Step 4: Process Areas")
    st.caption("Define process areas / sections with risk profiles, affinity grids, and domain registries.")

    pa_list: list[dict[str, Any]] = form.setdefault("process_areas", [])
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name")]
    placement_names = [p["name"] for p in form.get("placements", []) if isinstance(p, dict) and p.get("name")]
    if not placement_names:
        placement_names = _DEFAULT_PLACEMENTS
    method_names = [m["name"] for m in form.get("methods", []) if isinstance(m, dict) and m.get("name")]
    if not method_names:
        method_names = _DEFAULT_METHODS
    quality_options = form.get("quality_ratings", _DEFAULT_QUALITY_RATINGS)

    if st.button("\u2795 Add Process Area", key="wiz_add_pa"):
        next_id = f"{len(pa_list) + 1}.0"
        pa_list.append(
            {
                "id": next_id,
                "name": "",
                "domain": "",
                "risk_profile": {
                    "inherent_risk": 3,
                    "regulatory_intensity": 3,
                    "control_density": 3,
                    "multiplier": 1.0,
                    "rationale": "",
                },
                "affinity": {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []},
                "registry": {
                    "roles": [],
                    "systems": [],
                    "data_objects": [],
                    "evidence_artifacts": [],
                    "event_triggers": [],
                    "regulatory_frameworks": [],
                },
                "exemplars": [],
            }
        )
        st.rerun()

    to_remove = []
    for i, pa in enumerate(pa_list):
        pa_label = pa.get("name") or "(unnamed)"
        with st.expander(f"Section {pa.get('id', '?')}: {pa_label}", expanded=not pa.get("name")):
            # Basic fields
            c1, c2, c3 = st.columns(3)
            with c1:
                pa["id"] = st.text_input("ID", value=pa.get("id", ""), key=f"wiz_pa_id_{i}")
            with c2:
                pa["name"] = st.text_input("Name", value=pa.get("name", ""), key=f"wiz_pa_name_{i}")
            with c3:
                auto_domain = re.sub(r"[^a-z0-9]+", "_", pa.get("name", "").lower()).strip("_")
                pa["domain"] = st.text_input(
                    "Domain", value=pa.get("domain", "") or auto_domain, key=f"wiz_pa_domain_{i}"
                )

            # AI auto-fill button
            if st.button(f"\U0001f916 Auto-fill with AI", key=f"wiz_pa_ai_{i}"):
                if pa.get("name"):
                    with st.status(f"Auto-filling '{pa['name']}'\u2026", expanded=True) as status:
                        try:
                            result = _run_section_autofill(
                                pa["name"],
                                type_names,
                                {"name": form.get("name", ""), "description": form.get("description", "")},
                            )
                            if "risk_profile" in result:
                                pa["risk_profile"] = result["risk_profile"]
                            if "affinity" in result:
                                pa["affinity"] = result["affinity"]
                            if "registry" in result:
                                pa["registry"] = result["registry"]
                            if "exemplars" in result:
                                pa["exemplars"] = result["exemplars"]
                            status.update(label="\u2705 Auto-fill complete", state="complete")
                        except Exception as e:
                            status.update(label="\u274c Auto-fill failed", state="error")
                            st.error(str(e))
                    st.rerun()
                else:
                    st.warning("Enter a section name first.")

            # 4a: Risk Profile
            st.markdown("**Risk Profile**")
            rp = pa.setdefault(
                "risk_profile",
                {"inherent_risk": 3, "regulatory_intensity": 3, "control_density": 3, "multiplier": 1.0, "rationale": ""},
            )
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1:
                rp["inherent_risk"] = st.slider("Inherent Risk", 1, 5, rp.get("inherent_risk", 3), key=f"wiz_rp_ir_{i}")
            with rc2:
                rp["regulatory_intensity"] = st.slider(
                    "Regulatory Intensity", 1, 5, rp.get("regulatory_intensity", 3), key=f"wiz_rp_ri_{i}"
                )
            with rc3:
                rp["control_density"] = st.slider(
                    "Control Density", 1, 5, rp.get("control_density", 3), key=f"wiz_rp_cd_{i}"
                )
            with rc4:
                rp["multiplier"] = st.number_input(
                    "Multiplier",
                    min_value=0.1,
                    max_value=5.0,
                    value=float(rp.get("multiplier", 1.0)),
                    step=0.1,
                    key=f"wiz_rp_mul_{i}",
                )
            rp["rationale"] = st.text_area(
                "Rationale", value=rp.get("rationale", ""), key=f"wiz_rp_rat_{i}", height=60
            )

            # 4b: Affinity Grid
            if type_names:
                st.markdown("**Affinity Grid**")
                st.caption("Assign each control type to an affinity level for this section.")
                affinity = pa.setdefault("affinity", {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []})

                # Build current assignment lookup
                current_assignment: dict[str, str] = {}
                for level in _AFFINITY_LEVELS:
                    for t in affinity.get(level, []):
                        current_assignment[t] = level

                new_affinity: dict[str, list[str]] = {level: [] for level in _AFFINITY_LEVELS}
                cols = st.columns(min(len(type_names), 3))
                for j, tname in enumerate(type_names):
                    with cols[j % len(cols)]:
                        current_level = current_assignment.get(tname, "MEDIUM")
                        level_idx = _AFFINITY_LEVELS.index(current_level) if current_level in _AFFINITY_LEVELS else 1
                        selected = st.selectbox(
                            tname,
                            options=_AFFINITY_LEVELS,
                            index=level_idx,
                            key=f"wiz_aff_{i}_{j}",
                        )
                        new_affinity[selected].append(tname)
                pa["affinity"] = new_affinity

            # 4c: Registry
            st.markdown("**Domain Registry**")
            registry = pa.setdefault(
                "registry",
                {
                    "roles": [],
                    "systems": [],
                    "data_objects": [],
                    "evidence_artifacts": [],
                    "event_triggers": [],
                    "regulatory_frameworks": [],
                },
            )
            registry_fields = [
                ("roles", "Roles (one per line)"),
                ("systems", "Systems (one per line)"),
                ("data_objects", "Data Objects (one per line)"),
                ("evidence_artifacts", "Evidence Artifacts (one per line)"),
                ("event_triggers", "Event Triggers (one per line)"),
                ("regulatory_frameworks", "Regulatory Frameworks (one per line)"),
            ]
            r_cols = st.columns(2)
            for k, (field_key, field_label) in enumerate(registry_fields):
                with r_cols[k % 2]:
                    current_val = "\n".join(registry.get(field_key, []))
                    text = st.text_area(field_label, value=current_val, key=f"wiz_reg_{i}_{field_key}", height=80)
                    registry[field_key] = [line.strip() for line in text.split("\n") if line.strip()]

            # 4d: Exemplars
            st.markdown("**Exemplars** (optional)")
            exemplars = pa.setdefault("exemplars", [])
            if st.button(f"\u2795 Add Exemplar", key=f"wiz_add_ex_{i}"):
                exemplars.append(
                    {
                        "control_type": type_names[0] if type_names else "",
                        "placement": placement_names[0] if placement_names else "Detective",
                        "method": method_names[0] if method_names else "Manual",
                        "full_description": "",
                        "word_count": 0,
                        "quality_rating": "Effective",
                    }
                )
                st.rerun()

            ex_to_remove = []
            for ei, ex in enumerate(exemplars):
                with st.container():
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        ex["control_type"] = st.selectbox(
                            "Control Type",
                            options=type_names or [""],
                            index=type_names.index(ex["control_type"]) if ex.get("control_type") in type_names else 0,
                            key=f"wiz_ex_ct_{i}_{ei}",
                        )
                    with ec2:
                        ex["placement"] = st.selectbox(
                            "Placement",
                            options=placement_names,
                            index=placement_names.index(ex["placement"]) if ex.get("placement") in placement_names else 0,
                            key=f"wiz_ex_pl_{i}_{ei}",
                        )
                    with ec3:
                        ex["method"] = st.selectbox(
                            "Method",
                            options=method_names,
                            index=method_names.index(ex["method"]) if ex.get("method") in method_names else 0,
                            key=f"wiz_ex_mt_{i}_{ei}",
                        )
                    ex["full_description"] = st.text_area(
                        "Narrative (30-80 words)",
                        value=ex.get("full_description", ""),
                        key=f"wiz_ex_desc_{i}_{ei}",
                        height=80,
                    )
                    wc = len(ex["full_description"].split())
                    ex["word_count"] = wc
                    st.caption(f"Word count: {wc}")
                    ex["quality_rating"] = st.selectbox(
                        "Quality Rating",
                        options=quality_options,
                        index=quality_options.index(ex.get("quality_rating", "Effective"))
                        if ex.get("quality_rating") in quality_options
                        else 1,
                        key=f"wiz_ex_qr_{i}_{ei}",
                    )
                    if st.button("\U0001f5d1 Remove Exemplar", key=f"wiz_ex_rm_{i}_{ei}"):
                        ex_to_remove.append(ei)

            for idx in reversed(ex_to_remove):
                exemplars.pop(idx)
            if ex_to_remove:
                st.rerun()

            # Remove section
            if st.button(f"\U0001f5d1 Remove Section", key=f"wiz_pa_rm_{i}"):
                to_remove.append(i)

    for idx in reversed(to_remove):
        pa_list.pop(idx)
    if to_remove:
        st.rerun()

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", key="wiz_step4_back"):
            _set_step(3)
            st.rerun()
    with col_next:
        if st.button("Next \u2192", type="primary", key="wiz_step4_next"):
            form["process_areas"] = pa_list
            _set_step(5)
            st.rerun()


def _render_step_narrative(form: dict[str, Any]) -> None:
    """Step 5: Narrative constraints, placements, methods, frequencies, quality ratings."""
    st.markdown("#### Step 5: Narrative & Quality Settings")
    st.caption("These settings have sensible defaults. Modify only if needed.")

    # Narrative fields
    st.markdown("**Narrative Fields**")
    narrative = form.setdefault("narrative", {"fields": list(_DEFAULT_NARRATIVE_FIELDS), "word_count_min": 30, "word_count_max": 80})
    fields = narrative.setdefault("fields", list(_DEFAULT_NARRATIVE_FIELDS))

    for fi, field in enumerate(fields):
        c1, c2 = st.columns([1, 3])
        with c1:
            field["name"] = st.text_input("Field Name", value=field.get("name", ""), key=f"wiz_nf_name_{fi}")
        with c2:
            field["definition"] = st.text_input(
                "Definition", value=field.get("definition", ""), key=f"wiz_nf_def_{fi}"
            )

    wc1, wc2 = st.columns(2)
    with wc1:
        narrative["word_count_min"] = st.number_input(
            "Min Word Count", min_value=1, max_value=500, value=narrative.get("word_count_min", 30), key="wiz_wc_min"
        )
    with wc2:
        narrative["word_count_max"] = st.number_input(
            "Max Word Count", min_value=1, max_value=500, value=narrative.get("word_count_max", 80), key="wiz_wc_max"
        )

    # Quality ratings
    st.markdown("**Quality Ratings**")
    qr = form.get("quality_ratings", _DEFAULT_QUALITY_RATINGS)
    qr_text = st.text_area(
        "Quality Ratings (one per line)", value="\n".join(qr), key="wiz_qr", height=80
    )
    form["quality_ratings"] = [r.strip() for r in qr_text.split("\n") if r.strip()]

    # Placements
    st.markdown("**Placements**")
    placements = form.get("placements", [{"name": p, "description": ""} for p in _DEFAULT_PLACEMENTS])
    pl_text = st.text_area(
        "Placement Names (one per line)",
        value="\n".join(p["name"] if isinstance(p, dict) else str(p) for p in placements),
        key="wiz_pl",
        height=60,
    )
    form["placements"] = [{"name": n.strip(), "description": ""} for n in pl_text.split("\n") if n.strip()]

    # Methods
    st.markdown("**Methods**")
    methods = form.get("methods", [{"name": m, "description": ""} for m in _DEFAULT_METHODS])
    mt_text = st.text_area(
        "Method Names (one per line)",
        value="\n".join(m["name"] if isinstance(m, dict) else str(m) for m in methods),
        key="wiz_mt",
        height=60,
    )
    form["methods"] = [{"name": n.strip(), "description": ""} for n in mt_text.split("\n") if n.strip()]

    # Frequency tiers (simplified — just labels)
    st.markdown("**Frequency Tiers**")
    st.caption("Edit tier labels. Keywords and ranks are auto-generated from defaults.")
    tiers = form.get("frequency_tiers", list(_DEFAULT_FREQUENCY_TIERS))
    tier_text = st.text_area(
        "Tier Labels (one per line, ranked top=most frequent)",
        value="\n".join(t["label"] if isinstance(t, dict) else str(t) for t in tiers),
        key="wiz_ft",
        height=80,
    )
    new_tiers = []
    for rank, label in enumerate(tier_text.split("\n"), 1):
        label = label.strip()
        if label:
            # Find existing tier with matching label for keywords, else generate
            existing = next((t for t in tiers if isinstance(t, dict) and t.get("label") == label), None)
            keywords = existing["keywords"] if existing else [label.lower()]
            new_tiers.append({"label": label, "rank": rank, "keywords": keywords})
    form["frequency_tiers"] = new_tiers

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", key="wiz_step5_back"):
            _set_step(4)
            st.rerun()
    with col_next:
        if st.button("Next \u2192", type="primary", key="wiz_step5_next"):
            _set_step(6)
            st.rerun()


def _render_step_review(form: dict[str, Any]) -> DomainConfig | None:
    """Step 6: Review, validate, download, and use."""
    st.markdown("#### Step 6: Review & Export")

    # Attempt to build DomainConfig
    try:
        config = DomainConfig(**form)
    except Exception as e:
        st.error(f"**Validation failed:**\n\n{e}")
        st.info("Go back to the relevant step and fix the issues listed above.")

        col_back, _ = st.columns(2)
        with col_back:
            if st.button("\u2190 Back to Edit", key="wiz_step6_back_err"):
                _set_step(5)
                st.rerun()
        return None

    # Valid config — show summary
    st.success(
        f"**{config.name}** is valid! "
        f"{len(config.control_types)} types, "
        f"{len(config.business_units)} BUs, "
        f"{len(config.process_areas)} sections."
    )

    # Preview
    from controlnexus.ui.config_input import render_config_preview

    render_config_preview(config)

    # Export actions
    yaml_data = form.copy()
    yaml_str = yaml.dump(yaml_data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    col_dl, col_use, col_save = st.columns(3)
    with col_dl:
        st.download_button(
            "Download as YAML",
            data=yaml_str,
            file_name=f"{config.name}.yaml",
            mime="text/yaml",
            key="wiz_download",
        )
    with col_use:
        if st.button("Use this config", type="primary", key="wiz_use"):
            st.session_state["wizard_active_config"] = config.model_dump()
            st.session_state["wizard_built_config"] = config.model_dump()
            st.success("Config activated! Scroll down to generate controls.")
            return config
    with col_save:
        if st.button("Save to profiles", key="wiz_save"):
            from controlnexus.ui.config_input import _profiles_dir

            out_path = _profiles_dir() / f"{config.name}.yaml"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(yaml_str, encoding="utf-8")
            st.success(f"Saved to `{out_path}`")

    col_back, _ = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", key="wiz_step6_back"):
            _set_step(5)
            st.rerun()

    # Check if user previously activated this config
    built = st.session_state.get("wizard_built_config")
    if built is not None:
        try:
            return DomainConfig(**built)
        except Exception:
            pass
    return None


# ── Main entry point ──────────────────────────────────────────────────────────


def render_config_wizard() -> DomainConfig | None:
    """Render the multi-step form wizard for building a DomainConfig.

    Returns a ``DomainConfig`` when the user completes and activates
    the config, otherwise ``None``.
    """
    form = _get_form()
    current_step = _get_step()

    # Layout: sidebar with progress, main area with current step
    col_sidebar, col_main = st.columns([1, 4])

    with col_sidebar:
        _render_sidebar(current_step)

    with col_main:
        if current_step == 1:
            _render_step_basics(form)
        elif current_step == 2:
            _render_step_control_types(form)
        elif current_step == 3:
            _render_step_business_units(form)
        elif current_step == 4:
            _render_step_process_areas(form)
        elif current_step == 5:
            _render_step_narrative(form)
        elif current_step == 6:
            return _render_step_review(form)

    return None
