# ControlNexus Frontend Redesign v2 — Simplified

> **Guiding principle**: Fewer tabs, fewer clicks, fewer files. Work with Streamlit's grain.

---

## 1. What Changes

### Tab Structure: 4 → 3+1

```
┌──────────────────┬──────────────────────┬──────────┬────────────┐
│ Control Builder   │ ControlForge Modular │ Analysis │ Playground │
└──────────────────┴──────────────────────┴──────────┴────────────┘
```

- **ControlForge tab**: DELETED. The explorer features (risk radar, affinity heatmap) move into the Modular tab's config preview and the Builder's review step as inline visuals — not a separate destination.
- **Control Builder**: The wizard, simplified from 6 steps to 5. Template selection is the *first thing you see* inside the wizard, not a separate flow.
- **ControlForge Modular**: Unchanged in purpose. Config selector + generation + results. Gets a better config preview panel.
- **Analysis + Playground**: Untouched.

### File Count: 14 → 6 touched

| Action | File | Lines (est.) |
|--------|------|-------------|
| **Modify** | `ui/app.py` | ~20 lines changed (remove ControlForge tab, reorder) |
| **Rewrite** | `ui/config_wizard.py` | ~650 lines (down from 865, cleaner) |
| **Modify** | `ui/modular_tab.py` | ~80 lines changed (better config preview) |
| **Modify** | `ui/config_input.py` | ~30 lines changed (simplify) |
| **Modify** | `ui/styles.py` | ~120 lines added (panel styles) |
| **Delete** | `ui/controlforge_tab.py` | Removed entirely |

**No new files.** No component library. No `charts.py`, no `config_scorer.py`, no `template_gallery.py`, no `affinity_grid.py`. The reusable patterns live as functions *inside the files that use them*.

---

## 2. Control Builder — The 5-Step Wizard

### What Changes From Current `config_wizard.py`

The current 6-step wizard is mostly sound. We're making surgical improvements, not a rewrite from scratch:

| Change | Why |
|--------|-----|
| Step 0 (template picker) becomes the first screen in the wizard, before Step 1 | User shouldn't start from zero when good templates exist |
| Step 5 (Narrative & Quality) collapses into Step 5 (Review) as an "Advanced Settings" expander | Almost nobody changes the defaults |
| Step 4 (Process Areas) gets section-at-a-time navigation instead of all-sections-in-expanders | The expander-nesting is the worst UX pain point |
| All steps get CSS polish — bordered panels, consistent spacing, Carbon tag styling | Current look is raw default Streamlit |
| "Use as Template" option on profile selector seeds the wizard | Current template flow is jarring |

### Step Flow

```
[Template Picker] → Step 1: Basics → Step 2: Types → Step 3: BUs → Step 4: Sections → Step 5: Review & Export
```

### Template Picker (replaces Step 0)

This is NOT a separate "starting point selector" with 3 big cards. It's a simple inline element at the top of the wizard when `wizard_form` is empty:

```python
def _render_template_picker():
    """Show template picker only when starting fresh."""
    st.info("💡 Start from a template to save time, or continue below to build from scratch.")
    
    profiles = sorted(_profiles_dir().glob("*.yaml"))
    if not profiles:
        return
    
    cols = st.columns(len(profiles) + 1)
    for i, p in enumerate(profiles):
        with cols[i]:
            name = p.stem.replace("_", " ").replace("-", " ").title()
            config = load_domain_config(p)
            with st.container(border=True):
                st.markdown(f"**{name}**")
                st.caption(f"{len(config.control_types)} types · {len(config.business_units)} BUs · {len(config.process_areas)} sections")
                if st.button("Use as starting point", key=f"tmpl_{i}"):
                    # Deep-copy into wizard form
                    _seed_form_from_config(config)
                    st.rerun()
    
    with cols[-1]:
        with st.container(border=True):
            st.markdown("**Start Fresh**")
            st.caption("Empty config, build from scratch")
            if st.button("Start fresh", key="tmpl_fresh"):
                _set_step(1)
                st.rerun()
```

Once a template is selected OR the user clicks "Start fresh", the template picker disappears and the 5-step wizard begins. The template picker only shows when `form["name"]` is empty.

### Step 4: Sections — Section-at-a-Time

The biggest UX fix. Instead of rendering all sections as nested expanders (which is unreadable with 13 sections), show ONE section at a time with a simple selector:

```python
def _render_step_process_areas():
    form = _get_form()
    areas = form["process_areas"]
    
    # Action bar
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("➕ Add Section"):
            areas.append(_blank_section(len(areas) + 1))
            st.rerun()
    with col2:
        if st.button("📥 Import Sections"):
            _render_section_import_inline()
    
    if not areas:
        st.info("Add at least one process area to continue.")
        return
    
    # Section selector — simple selectbox, not a pill strip component
    section_names = [f"{a.get('id', '?')} — {a.get('name', 'Unnamed')}" for a in areas]
    active_idx = st.selectbox(
        "Select section to edit",
        range(len(areas)),
        format_func=lambda i: section_names[i],
        key="wizard_active_section",
    )
    
    pa = areas[active_idx]
    
    # Section header
    st.markdown("---")
    col_id, col_name, col_domain = st.columns([1, 3, 2])
    with col_id:
        pa["id"] = st.text_input("ID", value=pa.get("id", ""), key=f"pa_id_{active_idx}")
    with col_name:
        pa["name"] = st.text_input("Name", value=pa.get("name", ""), key=f"pa_name_{active_idx}")
    with col_domain:
        auto_domain = re.sub(r"[^a-z0-9]+", "_", pa.get("name", "").lower()).strip("_")
        pa["domain"] = st.text_input("Domain", value=pa.get("domain", auto_domain), key=f"pa_domain_{active_idx}")
    
    # AI fill button
    if pa.get("name", "").strip():
        if st.button("🤖 Auto-fill with AI", key=f"pa_ai_{active_idx}"):
            _autofill_section(active_idx)
    
    # 4 panels as tabs (not nested expanders)
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
    
    # Remove section button (at bottom, requires confirmation)
    st.markdown("---")
    if st.button("🗑 Remove this section", key=f"pa_rm_{active_idx}"):
        areas.pop(active_idx)
        st.rerun()
```

### Risk Profile Panel — Sliders Only, No Radar Chart

The radar chart was over-engineering. Four sliders with clear labels and a computed multiplier explanation are simpler and more actionable:

```python
def _render_risk_profile(pa, idx):
    rp = pa.setdefault("risk_profile", {"inherent_risk": 3, "regulatory_intensity": 3, "control_density": 3, "multiplier": 1.0, "rationale": ""})
    
    col1, col2 = st.columns(2)
    with col1:
        rp["inherent_risk"] = st.slider("Inherent Risk", 1, 5, rp.get("inherent_risk", 3), key=f"rp_ir_{idx}")
        rp["regulatory_intensity"] = st.slider("Regulatory Intensity", 1, 5, rp.get("regulatory_intensity", 3), key=f"rp_ri_{idx}")
    with col2:
        rp["control_density"] = st.slider("Control Density", 1, 5, rp.get("control_density", 3), key=f"rp_cd_{idx}")
        rp["multiplier"] = st.number_input("Multiplier", 0.1, 5.0, float(rp.get("multiplier", 1.0)), step=0.1, key=f"rp_mul_{idx}",
            help="Higher = more controls allocated to this section. Banking standard ranges from 1.2 to 3.2.")
    
    rp["rationale"] = st.text_area("Rationale", value=rp.get("rationale", ""), height=60, key=f"rp_rat_{idx}")
```

### Affinity Panel — Colored Selectbox Grid, No Drag-and-Drop

Drop `streamlit-sortables`. A selectbox per type in a 3-column grid with colored labels is simple and works reliably:

```python
def _render_affinity(pa, idx, form):
    type_names = [ct["name"] for ct in form.get("control_types", []) if ct.get("name", "").strip()]
    if not type_names:
        st.info("Define control types in Step 2 first.")
        return
    
    affinity = pa.setdefault("affinity", {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []})
    
    # Build reverse lookup: type_name → level
    current = {}
    for level in ["HIGH", "MEDIUM", "LOW", "NONE"]:
        for t in affinity.get(level, []):
            current[t] = level
    
    # Render grid
    cols = st.columns(3)
    new_affinity = {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []}
    
    for i, name in enumerate(type_names):
        with cols[i % 3]:
            level = st.selectbox(
                name, ["HIGH", "MEDIUM", "LOW", "NONE"],
                index=["HIGH", "MEDIUM", "LOW", "NONE"].index(current.get(name, "MEDIUM")),
                key=f"aff_{idx}_{i}",
            )
            new_affinity[level].append(name)
    
    pa["affinity"] = new_affinity
```

### Registry Panel — Simple Text Areas

No tag-cloud components. The current text-area approach works. Just add better labels and placeholder text:

```python
def _render_registry(pa, idx):
    reg = pa.setdefault("registry", {})
    
    fields = [
        ("roles", "Roles", "e.g. Senior Accountant, Control Owner, Internal Auditor"),
        ("systems", "Systems", "e.g. SAP Financial Close, Oracle EBS, Workiva"),
        ("data_objects", "Data Objects", "e.g. general ledger, trial balance, reconciliation reports"),
        ("evidence_artifacts", "Evidence Artifacts", "e.g. Signed reconciliation report, approval screenshot"),
        ("event_triggers", "Event Triggers", "e.g. at each month-end close, on material transaction"),
        ("regulatory_frameworks", "Regulatory Frameworks", "e.g. SOX Section 404, OCC Heightened Standards"),
    ]
    
    col1, col2 = st.columns(2)
    for i, (key, label, placeholder) in enumerate(fields):
        with (col1 if i % 2 == 0 else col2):
            current = reg.get(key, [])
            text = st.text_area(
                label,
                value="\n".join(current) if isinstance(current, list) else str(current),
                height=100,
                placeholder=placeholder,
                key=f"reg_{idx}_{key}",
            )
            reg[key] = [line.strip() for line in text.split("\n") if line.strip()]
```

### Step 5: Review & Export (absorbs old Step 5 + Step 6)

The review step now includes an "Advanced Settings" expander for the narrative/quality stuff that was Step 5:

```python
def _render_step_review():
    form = _get_form()
    
    # Advanced settings (old Step 5) — collapsed by default
    with st.expander("⚙️ Advanced Settings — Narrative, Quality, Placements", expanded=False):
        _render_narrative_settings(form)
        _render_placement_method_settings(form)
        _render_quality_settings(form)
    
    st.markdown("---")
    
    # Validation
    try:
        config = DomainConfig(**form)
    except Exception as e:
        st.error(f"Config has validation errors: {e}")
        st.info("Go back to the relevant step and fix the issues listed above.")
        return
    
    # Success — show summary
    st.success(f"**{config.name}** is valid!")
    
    # Clean metric summary
    col1, col2, col3 = st.columns(3)
    col1.metric("Control Types", len(config.control_types))
    col2.metric("Business Units", len(config.business_units))
    col3.metric("Process Areas", len(config.process_areas))
    
    # Config details preview (reuse existing render_config_preview)
    render_config_preview(config)
    
    # Export actions
    st.markdown("---")
    col_dl, col_use, col_save = st.columns(3)
    
    with col_dl:
        yaml_str = yaml.dump(form, default_flow_style=False, sort_keys=False, allow_unicode=True)
        st.download_button("📥 Download YAML", data=yaml_str, file_name=f"{config.name}.yaml", mime="text/yaml")
    
    with col_use:
        if st.button("✅ Use this config", type="primary"):
            st.session_state["wizard_active_config"] = config.model_dump()
            st.success("Config activated!")
    
    with col_save:
        if st.button("💾 Save to profiles"):
            path = _profiles_dir() / f"{config.name}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml_str, encoding="utf-8")
            st.success(f"Saved to {path}")
```

---

## 3. ControlForge Modular — Better Config Preview

The Modular tab stays mostly the same. The key improvement is a richer config preview panel that absorbs the useful Explorer features inline, so the user never needs a separate "explorer" tab.

### Current Config Preview (flat tables in an expander)

```
Control Types  Business Units  Process Areas
    25              17              13
▸ Config Details  (boring tables)
```

### New Config Preview (compact visual panels)

```
┌─────────────────────────────────────────────────────────────────┐
│ Banking Standard                                                │
│ Control Types: 25  ·  Business Units: 17  ·  Sections: 13      │
├─────────────────────────────────────────────────────────────────┤
│ ▸ Control Types (table — same as now, but styled better)        │
│ ▸ Business Units (table)                                        │
│ ▸ Process Areas (table with multiplier column)                  │
│ ▸ Section Risk Overview (simple multiplier bar chart — optional)│
└─────────────────────────────────────────────────────────────────┘
```

The change is cosmetic, not structural. One optional addition: a simple horizontal bar chart showing section multipliers, implemented as inline HTML (no plotly dependency):

```python
def _render_multiplier_bars(config):
    """Inline HTML bar chart for section multipliers."""
    if not config.process_areas:
        return
    max_m = max(pa.risk_profile.multiplier for pa in config.process_areas)
    bars_html = ""
    for pa in config.process_areas:
        pct = (pa.risk_profile.multiplier / max_m) * 100
        bars_html += f'''
        <div style="display:flex;align-items:center;margin:4px 0;font-size:13px;font-family:'IBM Plex Sans',sans-serif;">
            <span style="width:160px;color:#525252;">{pa.id} {pa.name[:20]}</span>
            <div style="flex:1;background:#f4f4f4;border-radius:2px;height:18px;margin:0 8px;">
                <div style="width:{pct}%;background:#0f62fe;height:100%;border-radius:2px;"></div>
            </div>
            <span style="width:40px;text-align:right;color:#161616;font-weight:500;">{pa.risk_profile.multiplier}x</span>
        </div>'''
    st.markdown(bars_html, unsafe_allow_html=True)
```

### Results Section — Lightweight Improvement

Keep the current flat table output but add summary metrics above it:

```python
# After generation completes
st.success(f"Generated **{len(records)}** controls")

# Summary row
col1, col2, col3 = st.columns(3)
col1.metric("Total Controls", len(records))
col2.metric("Types Used", len(set(r["control_type"] for r in records)))
col3.metric("Sections Covered", len(set(r.get("hierarchy_id", "")[:3] for r in records)))

# Table (existing render_data_table — unchanged)
render_data_table(...)
```

No sub-tabs for results. No separate "Distribution" or "Export" tabs. The export buttons go below the table, same as now.

---

## 4. CSS Polish — The Actual Visual Upgrade

The biggest bang-for-buck improvement is CSS, not structural changes. Add these to `styles.py`:

```python
PANEL_STYLES = '''
/* Clean bordered panels for wizard steps */
div.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1rem;
}

/* Wizard sidebar step indicators */
.wizard-step {
    padding: 8px 12px;
    margin: 2px 0;
    border-radius: 6px;
    font-size: 14px;
    font-family: 'IBM Plex Sans', sans-serif;
    cursor: pointer;
    transition: background 0.15s;
}
.wizard-step:hover { background: #f4f4f4; }
.wizard-step.active { background: #e8f0fe; color: #0f62fe; font-weight: 600; }
.wizard-step.completed { color: #24a148; }

/* Better expander headers */
details summary {
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 500;
}

/* Metric cards with subtle borders */
div[data-testid="stMetric"] {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    padding: 12px 16px;
}

/* Tag styling for placements, types, etc */
.cn-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 12px;
    margin: 1px 2px;
    font-family: 'IBM Plex Sans', sans-serif;
}
.cn-tag-blue { background: #d0e2ff; color: #0043ce; }
.cn-tag-green { background: #defbe6; color: #198038; }
.cn-tag-amber { background: #fff8e1; color: #8a6d3b; }
.cn-tag-gray { background: #f4f4f4; color: #525252; }

/* Section selector styling */
div[data-testid="stSelectbox"] label {
    font-weight: 500;
}

/* Cleaner form input spacing */
div[data-testid="stTextInput"], div[data-testid="stTextArea"] {
    margin-bottom: 0.5rem;
}

/* Template cards */
.template-card {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.template-card:hover {
    border-color: #0f62fe;
    box-shadow: 0 2px 8px rgba(15, 98, 254, 0.1);
}

/* Generation button emphasis */
button[data-testid="stBaseButton-primary"] {
    font-weight: 600;
    letter-spacing: 0.3px;
}

/* Results table polish */
div[data-testid="stDataFrame"] {
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    overflow: hidden;
}
'''
```

---

## 5. What We're NOT Doing

| Feature from v1 spec | Why we're dropping it |
|---|---|
| Separate `config_cards.py` component | Functions live inside the file that uses them |
| `charts.py` with 8 Plotly functions | One inline HTML bar chart replaces all of them |
| `config_scorer.py` with 8-dimension scoring | Replaced by simple validation pass/fail in Step 5 |
| `template_gallery.py` | 30-line inline function in `config_wizard.py` |
| `section_import.py` | 40-line inline function in `config_wizard.py` |
| `affinity_grid.py` with streamlit-sortables | Selectbox grid (already works, just style it) |
| `control_builder.py` (parallel wizard) | Modify existing `config_wizard.py` instead |
| Cross-tab navigation system | Not needed — no tab-switching flows |
| Plotly dependency | Not needed — HTML bar chart is sufficient |
| streamlit-sortables dependency | Not needed — selectboxes work fine |
| 7 new files | 0 new files |
| Undo stack | Nice-to-have but adds complexity; defer |

**New dependencies: ZERO.**

---

## 6. Implementation Plan

### Phase 1: Remove + Restructure (Day 1)

1. Delete the ControlForge tab from `app.py`. Update tab list to: Control Builder, ControlForge Modular, Analysis, Playground.
2. The Control Builder tab renders `render_config_wizard()` from the existing `config_wizard.py`.
3. Add CSS panel styles to `styles.py`.
4. Verify everything still works.

### Phase 2: Wizard Simplification (Day 2-3)

1. Add template picker to top of wizard (shows when form is empty).
2. Collapse Step 5 into Step 6 → now Step 5 (Review & Export) with Advanced Settings expander.
3. Rewrite Step 4 from nested-expanders to section-at-a-time with selectbox navigator + tabs for Risk/Affinity/Registry/Exemplars.
4. Add section import inline function (reads `config/sections/section_*.yaml`).
5. Add type import inline function (reads from profile YAMLs).
6. Update step count from 6 to 5, update labels and navigation.

### Phase 3: Modular Tab Polish (Day 4)

1. Better config preview panel with inline multiplier bar chart.
2. Summary metrics above results table.
3. Clean up the duplicate "Organization Config" rendering.
4. Style the generation settings section.

### Phase 4: CSS Polish Pass (Day 4-5)

1. Apply all panel styles from Section 4.
2. Test with both Community Bank (small config) and Banking Standard (large config).
3. Verify all existing functionality works — generation, LLM toggle, distribution sliders, export.

---

## 7. Summary Comparison

| Metric | v1 (over-engineered) | v2 (this plan) |
|--------|---------------------|----------------|
| New files | 7 | 0 |
| Modified files | 8 | 5 |
| New dependencies | 2 (plotly, sortables) | 0 |
| Total lines changed | ~4,680 | ~800 |
| Tabs | 5 | 4 |
| Wizard steps | 6 + starting point | 5 (template picker is inline, not a step) |
| Component library files | 6 | 0 (inline functions) |
| Plotly charts | 8 | 0 (HTML bar chart) |
| Config quality scorer | 8-dimension 100pt system | Pydantic validation pass/fail |
| Affinity grid | Drag-and-drop kanban | Styled selectbox grid |
| Risk profile | Plotly radar chart | 4 sliders (same as current, just styled) |