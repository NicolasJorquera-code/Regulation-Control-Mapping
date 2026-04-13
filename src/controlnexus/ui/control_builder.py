"""Control Builder — 5-step wizard for building a DomainConfig.

Steps:
  1. Basics (name, description)
  2. Control Types (dynamic list with AI auto-fill + profile import)
  3. Business Units (dynamic list)
  4. Process Areas (section-at-a-time with risk/affinity/registry/exemplar tabs)
  5. Review & Export (advanced settings expander + validation + download)

A template picker is shown inline above Step 1 when the form is empty.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from controlnexus.core.domain_config import DomainConfig, load_domain_config

logger = logging.getLogger(__name__)

TOTAL_STEPS = 5
STEP_LABELS = [
    "Basics",
    "Control Types",
    "Business Units",
    "Process Areas",
    "Review & Export",
]

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
    """Return the builder form data dict, initialising if needed."""
    if "builder_form" not in st.session_state:
        st.session_state["builder_form"] = _blank_form()
    return st.session_state["builder_form"]


def _blank_form() -> dict[str, Any]:
    return {
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


def _get_step() -> int:
    return st.session_state.get("builder_step", 0)  # 0 = template picker


def _set_step(step: int) -> None:
    st.session_state["builder_step"] = max(0, min(step, TOTAL_STEPS))


def _auto_code(name: str) -> str:
    consonants = re.sub(r"[aeiouAEIOU\s\-,]", "", name)
    return consonants[:3].upper() or "UNK"


def _profiles_dir() -> Path:
    """Resolve the config/profiles directory."""
    candidates = [
        Path.cwd() / "config" / "profiles",
        Path(__file__).resolve().parents[3] / "config" / "profiles",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def _sections_dir() -> Path:
    """Resolve the config/sections directory."""
    candidates = [
        Path.cwd() / "config" / "sections",
        Path(__file__).resolve().parents[3] / "config" / "sections",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def _seed_form_from_config(config: DomainConfig) -> None:
    """Deep-copy a DomainConfig's data into the builder form."""
    data = config.model_dump()
    form = _blank_form()
    for key in ("name", "description", "control_types", "business_units",
                "process_areas", "placements", "methods", "frequency_tiers",
                "quality_ratings", "narrative"):
        if key in data:
            form[key] = copy.deepcopy(data[key])
    st.session_state["builder_form"] = form


# ── LLM helpers ───────────────────────────────────────────────────────────────


def _run_section_autofill(section_name: str, control_type_names: list[str], config_context: dict) -> dict[str, Any]:
    from controlnexus.agents.base import AgentContext
    from controlnexus.agents.config_proposer import ConfigProposerAgent
    from controlnexus.core.transport import build_client_from_env

    client = build_client_from_env()
    ctx = AgentContext(client=client, model=client.model if client else "none", temperature=0.2, max_tokens=2048, timeout_seconds=120)
    agent = ConfigProposerAgent(ctx, name="ConfigProposer-Section")
    result = asyncio.run(agent.execute(mode="section_autofill", section_name=section_name, control_type_names=control_type_names, config_context=config_context))
    if client is not None:
        asyncio.run(client.close())
    return result


def _run_enrich(type_names: list[str]) -> dict[str, Any]:
    from controlnexus.agents.base import AgentContext
    from controlnexus.agents.config_proposer import ConfigProposerAgent
    from controlnexus.core.transport import build_client_from_env

    client = build_client_from_env()
    ctx = AgentContext(client=client, model=client.model if client else "none", temperature=0.2, max_tokens=2048, timeout_seconds=120)
    agent = ConfigProposerAgent(ctx, name="ConfigProposer-Enrich")
    result = asyncio.run(agent.execute(mode="enrich", type_names=type_names))
    if client is not None:
        asyncio.run(client.close())
    return result


# ── Sidebar ───────────────────────────────────────────────────────────────────


def _render_sidebar(current_step: int) -> None:
    """Step progress sidebar."""
    for i in range(1, TOTAL_STEPS + 1):
        if i < current_step:
            icon = "✅"
        elif i == current_step:
            icon = "●"
        else:
            icon = "○"

        label = f"{icon} Step {i}: {STEP_LABELS[i - 1]}"
        if i <= current_step:
            if st.button(label, key=f"cb_nav_{i}", use_container_width=True):
                _set_step(i)
                st.rerun()
        else:
            st.markdown(f"<div style='padding:6px 12px;color:#a8a8a8;'>{label}</div>", unsafe_allow_html=True)


# ── Template Picker ───────────────────────────────────────────────────────────


def _render_template_picker() -> None:
    """Inline template picker — shown when form is empty."""
    st.info("💡 Start from a template to save time, or skip to build from scratch.")

    profiles_path = _profiles_dir()
    yaml_files = sorted(profiles_path.glob("*.yaml")) if profiles_path.is_dir() else []

    n_cols = len(yaml_files) + 1
    cols = st.columns(min(n_cols, 4))

    for i, yf in enumerate(yaml_files):
        with cols[i % len(cols)]:
            with st.container(border=True):
                try:
                    config = load_domain_config(yf)
                    name = yf.stem.replace("_", " ").replace("-", " ").title()
                    st.markdown(f"**{name}**")
                    st.caption(
                        f"{len(config.control_types)} types · "
                        f"{len(config.business_units)} BUs · "
                        f"{len(config.process_areas)} sections"
                    )
                    if st.button("Use as starting point", key=f"tmpl_{i}"):
                        _seed_form_from_config(config)
                        _set_step(1)
                        st.rerun()
                except Exception:
                    st.caption(f"⚠️ Failed to load {yf.name}")

    with cols[min(len(yaml_files), len(cols) - 1)]:
        with st.container(border=True):
            st.markdown("**Start Fresh**")
            st.caption("Empty config, build from scratch")
            if st.button("Start fresh", key="tmpl_fresh"):
                _set_step(1)
                st.rerun()


# ── Step 1: Basics ────────────────────────────────────────────────────────────


def _render_step_basics(form: dict[str, Any]) -> None:
    st.markdown("#### Step 1: Basics")
    st.caption("Name your configuration and provide a brief description.")

    form["name"] = st.text_input(
        "Config Name",
        value=form.get("name", ""),
        placeholder="e.g. community-bank-demo",
        key="cb_name",
    )
    form["description"] = st.text_area(
        "Description",
        value=form.get("description", ""),
        placeholder="Brief description of the organization and control domain.",
        key="cb_desc",
        height=100,
    )

    if st.button("Next →", type="primary", key="cb_step1_next"):
        if not form["name"].strip():
            st.error("Config name is required.")
        else:
            _set_step(2)
            st.rerun()


# ── Step 2: Control Types ────────────────────────────────────────────────────


def _render_step_control_types(form: dict[str, Any]) -> None:
    st.markdown("#### Step 2: Control Types")
    st.caption("Define the control types in your taxonomy. At least one is required.")

    types_list: list[dict[str, Any]] = form.setdefault("control_types", [])

    # Action buttons
    col_add, col_ai, col_import = st.columns(3)
    with col_add:
        if st.button("➕ Add Control Type", key="cb_add_ct"):
            types_list.append({
                "name": "", "definition": "", "code": "",
                "min_frequency_tier": None, "placement_categories": [], "evidence_criteria": [],
            })
            st.rerun()
    with col_ai:
        if st.button("🤖 Auto-fill Definitions", key="cb_enrich_ct"):
            names = [ct["name"] for ct in types_list if ct.get("name")]
            if names:
                with st.status("Enriching control types…", expanded=True) as status:
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
                        status.update(label="✅ Enrichment complete", state="complete")
                    except Exception as e:
                        status.update(label="❌ Enrichment failed", state="error")
                        st.error(str(e))
                st.rerun()
            else:
                st.warning("Add at least one control type name first.")
    with col_import:
        if st.button("📥 Import from Profile", key="cb_import_ct"):
            st.session_state["_cb_show_type_import"] = not st.session_state.get("_cb_show_type_import", False)
            st.rerun()

    # Type import panel
    if st.session_state.get("_cb_show_type_import"):
        _render_type_import(types_list)

    # Existing placement names for multiselect
    placement_names = [p["name"] for p in form.get("placements", []) if isinstance(p, dict)] or _DEFAULT_PLACEMENTS
    freq_options = [None, "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual"]

    # Render each type in an expander
    to_remove: list[int] = []
    for i, ct in enumerate(types_list):
        with st.expander(f"Control Type {i + 1}: {ct.get('name', '(unnamed)')}", expanded=not ct.get("name")):
            ct["name"] = st.text_input("Name", value=ct.get("name", ""), key=f"cb_ct_name_{i}")
            ct["definition"] = st.text_area("Definition", value=ct.get("definition", ""), key=f"cb_ct_def_{i}", height=80)

            c1, c2 = st.columns(2)
            with c1:
                ct["code"] = st.text_input(
                    "Code (3 letters)",
                    value=ct.get("code", "") or _auto_code(ct.get("name", "")),
                    max_chars=3, key=f"cb_ct_code_{i}",
                )
            with c2:
                current_freq = ct.get("min_frequency_tier")
                freq_idx = freq_options.index(current_freq) if current_freq in freq_options else 0
                ct["min_frequency_tier"] = st.selectbox(
                    "Min Frequency", options=freq_options, index=freq_idx,
                    format_func=lambda x: x or "None", key=f"cb_ct_freq_{i}",
                )

            ct["placement_categories"] = st.multiselect(
                "Placement Categories", options=placement_names,
                default=[p for p in ct.get("placement_categories", []) if p in placement_names],
                key=f"cb_ct_place_{i}",
            )
            evidence_text = "\n".join(ct.get("evidence_criteria", []))
            evidence_input = st.text_area("Evidence Criteria (one per line)", value=evidence_text, key=f"cb_ct_evid_{i}", height=80)
            ct["evidence_criteria"] = [line.strip() for line in evidence_input.split("\n") if line.strip()]

            if st.button("🗑 Remove", key=f"cb_ct_rm_{i}"):
                to_remove.append(i)

    for idx in reversed(to_remove):
        types_list.pop(idx)
    if to_remove:
        st.rerun()

    # Navigation
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", key="cb_step2_back"):
            _set_step(1)
            st.rerun()
    with col_next:
        if st.button("Next →", type="primary", key="cb_step2_next"):
            valid_types = [ct for ct in types_list if ct.get("name", "").strip()]
            if not valid_types:
                st.error("At least one control type with a name is required.")
            else:
                form["control_types"] = valid_types
                _set_step(3)
                st.rerun()


def _render_type_import(types_list: list[dict[str, Any]]) -> None:
    """Import control types from an existing profile."""
    profiles_path = _profiles_dir()
    yaml_files = sorted(profiles_path.glob("*.yaml")) if profiles_path.is_dir() else []
    if not yaml_files:
        st.info("No profiles available for import.")
        return

    selected_profile = st.selectbox(
        "Import types from profile",
        options=yaml_files,
        format_func=lambda p: p.stem.replace("_", " ").title(),
        key="cb_type_import_profile",
    )
    if selected_profile:
        data = yaml.safe_load(selected_profile.read_text(encoding="utf-8"))
        available_types = data.get("control_types", [])
        existing_names = {ct["name"] for ct in types_list}
        importable = [ct for ct in available_types if ct.get("name") and ct["name"] not in existing_names]

        if importable:
            selected_names = st.multiselect(
                "Select types to import",
                options=[ct["name"] for ct in importable],
                key="cb_type_import_select",
            )
            if selected_names and st.button("Import Selected Types", key="cb_type_import_btn"):
                for ct in importable:
                    if ct["name"] in selected_names:
                        types_list.append(copy.deepcopy(ct))
                st.session_state["_cb_show_type_import"] = False
                st.rerun()
        else:
            st.info("All types from this profile are already in your config.")


# ── Step 3: Business Units ───────────────────────────────────────────────────


def _render_step_business_units(form: dict[str, Any]) -> None:
    st.markdown("#### Step 3: Business Units")
    st.caption("Define business units (optional). You can skip this step.")

    bu_list: list[dict[str, Any]] = form.setdefault("business_units", [])
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name")]
    section_ids = [pa["id"] for pa in form.get("process_areas", []) if pa.get("id")]

    if st.button("➕ Add Business Unit", key="cb_add_bu"):
        next_num = len(bu_list) + 1
        bu_list.append({
            "id": f"BU-{next_num:03d}", "name": "", "description": "",
            "primary_sections": [], "key_control_types": [], "regulatory_exposure": [],
        })
        st.rerun()

    if not section_ids:
        st.info("💡 You'll define sections in Step 4. You can come back to link them.")

    to_remove: list[int] = []
    for i, bu in enumerate(bu_list):
        with st.expander(f"Business Unit {i + 1}: {bu.get('name', '(unnamed)')}", expanded=not bu.get("name")):
            c1, c2 = st.columns(2)
            with c1:
                bu["id"] = st.text_input("ID", value=bu.get("id", ""), key=f"cb_bu_id_{i}")
            with c2:
                bu["name"] = st.text_input("Name", value=bu.get("name", ""), key=f"cb_bu_name_{i}")
            bu["description"] = st.text_area("Description", value=bu.get("description", ""), key=f"cb_bu_desc_{i}", height=60)

            if section_ids:
                bu["primary_sections"] = st.multiselect(
                    "Primary Sections", options=section_ids,
                    default=[s for s in bu.get("primary_sections", []) if s in section_ids],
                    key=f"cb_bu_sec_{i}",
                )
            else:
                sec_text = st.text_input("Primary Sections (comma-separated)", value=", ".join(bu.get("primary_sections", [])), key=f"cb_bu_sec_txt_{i}")
                bu["primary_sections"] = [s.strip() for s in sec_text.split(",") if s.strip()]

            bu["key_control_types"] = st.multiselect(
                "Key Control Types", options=type_names,
                default=[t for t in bu.get("key_control_types", []) if t in type_names],
                key=f"cb_bu_types_{i}",
            )
            reg_text = st.text_input("Regulatory Exposure (comma-separated)", value=", ".join(bu.get("regulatory_exposure", [])), key=f"cb_bu_reg_{i}")
            bu["regulatory_exposure"] = [r.strip() for r in reg_text.split(",") if r.strip()]

            if st.button("🗑 Remove", key=f"cb_bu_rm_{i}"):
                to_remove.append(i)

    for idx in reversed(to_remove):
        bu_list.pop(idx)
    if to_remove:
        st.rerun()

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", key="cb_step3_back"):
            _set_step(2)
            st.rerun()
    with col_next:
        if st.button("Next →", type="primary", key="cb_step3_next"):
            form["business_units"] = bu_list
            _set_step(4)
            st.rerun()


# ── Step 4: Process Areas ────────────────────────────────────────────────────


def _render_step_process_areas(form: dict[str, Any]) -> None:
    st.markdown("#### Step 4: Process Areas")
    st.caption("Define sections with risk profiles, affinity grids, registries, and exemplars.")

    pa_list: list[dict[str, Any]] = form.setdefault("process_areas", [])
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name")]

    # Action bar
    col_add, col_import = st.columns(2)
    with col_add:
        if st.button("➕ Add Section", key="cb_add_pa"):
            next_id = f"{len(pa_list) + 1}.0"
            pa_list.append(_blank_section(next_id))
            st.rerun()
    with col_import:
        if st.button("📥 Import Sections", key="cb_import_sections"):
            st.session_state["_cb_show_section_import"] = not st.session_state.get("_cb_show_section_import", False)
            st.rerun()

    # Section import panel
    if st.session_state.get("_cb_show_section_import"):
        imported = _render_section_import_inline(pa_list)
        if imported:
            pa_list.extend(imported)
            st.session_state["_cb_show_section_import"] = False
            st.success(f"Imported {len(imported)} section(s)!")
            st.rerun()

    if not pa_list:
        st.info("Add at least one process area, or import from YAML.")
        col_back, _ = st.columns(2)
        with col_back:
            if st.button("← Back", key="cb_step4_back_empty"):
                _set_step(3)
                st.rerun()
        return

    # Section selector — simple selectbox
    section_names = [f"{a.get('id', '?')} — {a.get('name', 'Unnamed')}" for a in pa_list]
    active_idx = st.selectbox(
        "Select section to edit",
        range(len(pa_list)),
        format_func=lambda i: section_names[i],
        key="wizard_active_section",
    )

    pa = pa_list[active_idx]

    # Section header
    st.markdown("---")
    col_id, col_name, col_domain = st.columns([1, 3, 2])
    with col_id:
        pa["id"] = st.text_input("ID", value=pa.get("id", ""), key=f"cb_pa_id_{active_idx}")
    with col_name:
        pa["name"] = st.text_input("Name", value=pa.get("name", ""), key=f"cb_pa_name_{active_idx}")
    with col_domain:
        auto_domain = re.sub(r"[^a-z0-9]+", "_", pa.get("name", "").lower()).strip("_")
        pa["domain"] = st.text_input("Domain", value=pa.get("domain", "") or auto_domain, key=f"cb_pa_domain_{active_idx}")

    # AI fill + remove
    col_ai, col_rm = st.columns([3, 1])
    with col_ai:
        if pa.get("name", "").strip():
            if st.button("🤖 Auto-fill with AI", key=f"cb_pa_ai_{active_idx}"):
                with st.status(f"Auto-filling '{pa['name']}'…", expanded=True) as status:
                    try:
                        result = _run_section_autofill(pa["name"], type_names, {"name": form.get("name", ""), "description": form.get("description", "")})
                        for k in ("risk_profile", "affinity", "registry", "exemplars"):
                            if k in result:
                                pa[k] = result[k]
                        status.update(label="✅ Auto-fill complete", state="complete")
                    except Exception as e:
                        status.update(label="❌ Auto-fill failed", state="error")
                        st.error(str(e))
                st.rerun()
    with col_rm:
        if st.button("🗑 Remove Section", key=f"cb_pa_rm_{active_idx}"):
            pa_list.pop(active_idx)
            st.rerun()

    # 4 panels as tabs
    tab_risk, tab_affinity, tab_registry, tab_exemplars = st.tabs(
        ["Risk Profile", "Affinity", "Registry", "Exemplars"]
    )

    with tab_risk:
        _render_risk_profile(pa, active_idx)
    with tab_affinity:
        _render_affinity(pa, active_idx, form)
    with tab_registry:
        _render_registry(pa, active_idx)
    with tab_exemplars:
        _render_exemplars(pa, active_idx, form)

    # Navigation
    st.markdown("---")
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", key="cb_step4_back"):
            _set_step(3)
            st.rerun()
    with col_next:
        if st.button("Next →", type="primary", key="cb_step4_next"):
            form["process_areas"] = pa_list
            _set_step(5)
            st.rerun()


def _blank_section(section_id: str = "1.0") -> dict[str, Any]:
    return {
        "id": section_id, "name": "", "domain": "",
        "risk_profile": {"inherent_risk": 3, "regulatory_intensity": 3, "control_density": 3, "multiplier": 1.0, "rationale": ""},
        "affinity": {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []},
        "registry": {"roles": [], "systems": [], "data_objects": [], "evidence_artifacts": [], "event_triggers": [], "regulatory_frameworks": []},
        "exemplars": [],
    }


def _render_section_import_inline(existing_sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inline section import from config/sections/ YAMLs."""
    sections_path = _sections_dir()
    yaml_files = sorted(sections_path.glob("section_*.yaml")) if sections_path.is_dir() else []

    if not yaml_files:
        st.info("No section YAML files found in `config/sections/`.")
        return []

    existing_ids = {pa["id"] for pa in existing_sections}
    available: list[dict[str, Any]] = []
    for yf in yaml_files:
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                sid = data.get("section_id", yf.stem)
                domain = data.get("domain", "")
                name = domain.replace("_", " ").title() if domain else yf.stem
                available.append({"file": yf.name, "section_id": sid, "name": name, "domain": domain, "data": data, "imported": sid in existing_ids})
        except Exception:
            pass

    options = [f"{s['section_id']}: {s['name']}" + (" (imported)" if s["imported"] else "") for s in available]
    selected = st.multiselect("Select sections to import", options=options, key="cb_sec_imp_select")

    if not selected or not st.button("📥 Import Selected", key="cb_sec_imp_btn", type="primary"):
        return []

    imported: list[dict[str, Any]] = []
    for sel_label in selected:
        idx = options.index(sel_label)
        sec = available[idx]
        data = sec["data"]
        imported.append({
            "id": data.get("section_id", sec["section_id"]),
            "name": sec["name"],
            "domain": data.get("domain", ""),
            "risk_profile": data.get("risk_profile", {"inherent_risk": 3, "regulatory_intensity": 3, "control_density": 3, "multiplier": 1.0, "rationale": ""}),
            "affinity": data.get("affinity", {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []}),
            "registry": data.get("registry", {"roles": [], "systems": [], "data_objects": [], "evidence_artifacts": [], "event_triggers": [], "regulatory_frameworks": []}),
            "exemplars": data.get("exemplars", []),
        })
    return imported


def _render_risk_profile(pa: dict, idx: int) -> None:
    """Sliders-only risk profile panel."""
    rp = pa.setdefault("risk_profile", {"inherent_risk": 3, "regulatory_intensity": 3, "control_density": 3, "multiplier": 1.0, "rationale": ""})

    col1, col2 = st.columns(2)
    with col1:
        rp["inherent_risk"] = st.slider("Inherent Risk", 1, 5, rp.get("inherent_risk", 3), key=f"cb_rp_ir_{idx}")
        rp["regulatory_intensity"] = st.slider("Regulatory Intensity", 1, 5, rp.get("regulatory_intensity", 3), key=f"cb_rp_ri_{idx}")
    with col2:
        rp["control_density"] = st.slider("Control Density", 1, 5, rp.get("control_density", 3), key=f"cb_rp_cd_{idx}")
        rp["multiplier"] = st.number_input(
            "Multiplier", 0.1, 5.0, float(rp.get("multiplier", 1.0)), step=0.1, key=f"cb_rp_mul_{idx}",
            help="Higher = more controls allocated to this section. Banking standard ranges from 1.2 to 3.2.",
        )
    rp["rationale"] = st.text_area("Rationale", value=rp.get("rationale", ""), height=60, key=f"cb_rp_rat_{idx}")


def _render_affinity(pa: dict, idx: int, form: dict) -> None:
    """Selectbox grid for affinity assignments."""
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name", "").strip()]
    if not type_names:
        st.info("Define control types in Step 2 first.")
        return

    affinity = pa.setdefault("affinity", {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []})

    # Build reverse lookup
    current: dict[str, str] = {}
    for level in _AFFINITY_LEVELS:
        for t in affinity.get(level, []):
            current[t] = level

    cols = st.columns(3)
    new_affinity: dict[str, list[str]] = {level: [] for level in _AFFINITY_LEVELS}
    for j, name in enumerate(type_names):
        with cols[j % 3]:
            level = st.selectbox(
                name, _AFFINITY_LEVELS,
                index=_AFFINITY_LEVELS.index(current.get(name, "MEDIUM")),
                key=f"cb_aff_{idx}_{j}",
            )
            new_affinity[level].append(name)
    pa["affinity"] = new_affinity


def _render_registry(pa: dict, idx: int) -> None:
    """Plain text areas for registry fields."""
    reg = pa.setdefault("registry", {
        "roles": [], "systems": [], "data_objects": [],
        "evidence_artifacts": [], "event_triggers": [], "regulatory_frameworks": [],
    })

    fields = [
        ("roles", "Roles", "e.g. Senior Accountant, Control Owner, Internal Auditor"),
        ("systems", "Systems", "e.g. SAP Financial Close, Oracle EBS, Workiva"),
        ("data_objects", "Data Objects", "e.g. general ledger, trial balance, reconciliation reports"),
        ("evidence_artifacts", "Evidence Artifacts", "e.g. Signed reconciliation report, approval screenshot"),
        ("event_triggers", "Event Triggers", "e.g. at each month-end close, on material transaction"),
        ("regulatory_frameworks", "Regulatory Frameworks", "e.g. SOX Section 404, OCC Heightened Standards"),
    ]

    col1, col2 = st.columns(2)
    for k, (key, label, placeholder) in enumerate(fields):
        with (col1 if k % 2 == 0 else col2):
            current = reg.get(key, [])
            text = st.text_area(
                label,
                value="\n".join(current) if isinstance(current, list) else str(current),
                height=100, placeholder=placeholder, key=f"cb_reg_{idx}_{key}",
            )
            reg[key] = [line.strip() for line in text.split("\n") if line.strip()]


def _render_exemplars(pa: dict, idx: int, form: dict) -> None:
    """Exemplar editor."""
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name")]
    placement_names = [p["name"] for p in form.get("placements", []) if isinstance(p, dict)] or _DEFAULT_PLACEMENTS
    method_names = [m["name"] for m in form.get("methods", []) if isinstance(m, dict)] or _DEFAULT_METHODS
    quality_options = form.get("quality_ratings", _DEFAULT_QUALITY_RATINGS)

    exemplars = pa.setdefault("exemplars", [])

    if st.button("➕ Add Exemplar", key=f"cb_add_ex_{idx}"):
        exemplars.append({
            "control_type": type_names[0] if type_names else "",
            "placement": placement_names[0] if placement_names else "Detective",
            "method": method_names[0] if method_names else "Manual",
            "full_description": "", "word_count": 0, "quality_rating": "Effective",
        })
        st.rerun()

    to_remove: list[int] = []
    for ei, ex in enumerate(exemplars):
        with st.container(border=True):
            ec1, ec2, ec3 = st.columns(3)
            with ec1:
                ex["control_type"] = st.selectbox(
                    "Control Type", options=type_names or [""],
                    index=type_names.index(ex["control_type"]) if ex.get("control_type") in type_names else 0,
                    key=f"cb_ex_ct_{idx}_{ei}",
                )
            with ec2:
                ex["placement"] = st.selectbox(
                    "Placement", options=placement_names,
                    index=placement_names.index(ex["placement"]) if ex.get("placement") in placement_names else 0,
                    key=f"cb_ex_pl_{idx}_{ei}",
                )
            with ec3:
                ex["method"] = st.selectbox(
                    "Method", options=method_names,
                    index=method_names.index(ex["method"]) if ex.get("method") in method_names else 0,
                    key=f"cb_ex_mt_{idx}_{ei}",
                )
            ex["full_description"] = st.text_area(
                "Narrative (30-80 words)", value=ex.get("full_description", ""),
                key=f"cb_ex_desc_{idx}_{ei}", height=80,
            )
            wc = len(ex["full_description"].split())
            ex["word_count"] = wc
            ex["quality_rating"] = st.selectbox(
                "Quality Rating", options=quality_options,
                index=quality_options.index(ex.get("quality_rating", "Effective")) if ex.get("quality_rating") in quality_options else 1,
                key=f"cb_ex_qr_{idx}_{ei}",
            )
            col_wc, col_rm = st.columns([3, 1])
            with col_wc:
                wc_ok = "✅" if 30 <= wc <= 80 else "⚠️"
                st.caption(f"Word count: {wc} {wc_ok}")
            with col_rm:
                if st.button("🗑 Remove", key=f"cb_ex_rm_{idx}_{ei}"):
                    to_remove.append(ei)

    for i in reversed(to_remove):
        exemplars.pop(i)
    if to_remove:
        st.rerun()


# ── Step 5: Review & Export ──────────────────────────────────────────────────


def _render_step_review(form: dict[str, Any]) -> None:
    st.markdown("#### Step 5: Review & Export")

    # Advanced settings (narrative, quality, placements) — collapsed
    with st.expander("⚙️ Advanced Settings — Narrative, Quality, Placements", expanded=False):
        _render_narrative_settings(form)
        _render_placement_method_settings(form)
        _render_quality_settings(form)

    st.markdown("---")

    # Validation
    try:
        config = DomainConfig(**form)
    except Exception as e:
        st.error(f"**Config has validation errors:**\n\n{e}")
        st.info("Go back to the relevant step and fix the issues listed above.")
        if st.button("← Back to Edit", key="cb_step5_back_err"):
            _set_step(4)
            st.rerun()
        return

    # Success
    st.success(f"**{config.name}** is valid!")

    col1, col2, col3 = st.columns(3)
    col1.metric("Control Types", len(config.control_types))
    col2.metric("Business Units", len(config.business_units))
    col3.metric("Process Areas", len(config.process_areas))

    # Config preview
    from controlnexus.ui.config_input import render_config_preview
    render_config_preview(config)

    # Export actions
    st.markdown("---")
    yaml_str = yaml.dump(form, default_flow_style=False, sort_keys=False, allow_unicode=True)

    col_dl, col_use, col_save = st.columns(3)
    with col_dl:
        st.download_button("📥 Download YAML", data=yaml_str, file_name=f"{config.name}.yaml", mime="text/yaml", key="cb_download")
    with col_use:
        if st.button("✅ Use this config", type="primary", key="cb_use"):
            st.session_state["wizard_active_config"] = config.model_dump()
            st.success("Config activated! Switch to the **ControlForge Modular** tab to generate controls.")
    with col_save:
        if st.button("💾 Save to profiles", key="cb_save"):
            out_path = _profiles_dir() / f"{config.name}.yaml"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(yaml_str, encoding="utf-8")
            st.success(f"Saved to `{out_path}`")

    if st.button("← Back", key="cb_step5_back"):
        _set_step(4)
        st.rerun()


def _render_narrative_settings(form: dict[str, Any]) -> None:
    """Narrative fields and word count limits."""
    narrative = form.setdefault("narrative", {"fields": list(_DEFAULT_NARRATIVE_FIELDS), "word_count_min": 30, "word_count_max": 80})
    st.markdown("**Narrative Fields**")
    fields = narrative.setdefault("fields", list(_DEFAULT_NARRATIVE_FIELDS))
    for fi, field in enumerate(fields):
        c1, c2 = st.columns([1, 3])
        with c1:
            field["name"] = st.text_input("Field", value=field.get("name", ""), key=f"cb_nf_name_{fi}")
        with c2:
            field["definition"] = st.text_input("Definition", value=field.get("definition", ""), key=f"cb_nf_def_{fi}")

    wc1, wc2 = st.columns(2)
    with wc1:
        narrative["word_count_min"] = st.number_input("Min Words", min_value=1, max_value=500, value=narrative.get("word_count_min", 30), key="cb_wc_min")
    with wc2:
        narrative["word_count_max"] = st.number_input("Max Words", min_value=1, max_value=500, value=narrative.get("word_count_max", 80), key="cb_wc_max")


def _render_placement_method_settings(form: dict[str, Any]) -> None:
    """Placement and method settings."""
    st.markdown("**Placements**")
    placements = form.get("placements", [{"name": p, "description": ""} for p in _DEFAULT_PLACEMENTS])
    pl_text = st.text_area("Placement Names (one per line)", value="\n".join(p["name"] if isinstance(p, dict) else str(p) for p in placements), key="cb_pl", height=60)
    form["placements"] = [{"name": n.strip(), "description": ""} for n in pl_text.split("\n") if n.strip()]

    st.markdown("**Methods**")
    methods = form.get("methods", [{"name": m, "description": ""} for m in _DEFAULT_METHODS])
    mt_text = st.text_area("Method Names (one per line)", value="\n".join(m["name"] if isinstance(m, dict) else str(m) for m in methods), key="cb_mt", height=60)
    form["methods"] = [{"name": n.strip(), "description": ""} for n in mt_text.split("\n") if n.strip()]

    st.markdown("**Frequency Tiers**")
    tiers = form.get("frequency_tiers", list(_DEFAULT_FREQUENCY_TIERS))
    tier_text = st.text_area("Tier Labels (one per line)", value="\n".join(t["label"] if isinstance(t, dict) else str(t) for t in tiers), key="cb_ft", height=80)
    new_tiers = []
    for rank, label in enumerate(tier_text.split("\n"), 1):
        label = label.strip()
        if label:
            existing = next((t for t in tiers if isinstance(t, dict) and t.get("label") == label), None)
            keywords = existing["keywords"] if existing else [label.lower()]
            new_tiers.append({"label": label, "rank": rank, "keywords": keywords})
    form["frequency_tiers"] = new_tiers


def _render_quality_settings(form: dict[str, Any]) -> None:
    """Quality rating settings."""
    st.markdown("**Quality Ratings**")
    qr = form.get("quality_ratings", _DEFAULT_QUALITY_RATINGS)
    qr_text = st.text_area("Quality Ratings (one per line)", value="\n".join(qr), key="cb_qr", height=80)
    form["quality_ratings"] = [r.strip() for r in qr_text.split("\n") if r.strip()]


# ── Main entry point ──────────────────────────────────────────────────────────


def render_control_builder_tab() -> None:
    """Render the Control Builder tab."""
    st.markdown('<div class="report-title">Control Builder</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="report-subtitle">Create your organization\'s control configuration</div>',
        unsafe_allow_html=True,
    )

    form = _get_form()
    current_step = _get_step()

    # Show template picker when starting fresh (step 0 or form empty)
    if current_step == 0:
        _render_template_picker()
        return

    # Layout: sidebar + main
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
            _render_step_review(form)
