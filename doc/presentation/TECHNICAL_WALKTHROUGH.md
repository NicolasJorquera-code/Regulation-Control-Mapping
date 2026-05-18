# ControlNexus — Technical Walkthrough Script

> **Audience:** Technical stakeholders, solution architects, engineering leads  
> **Format:** Screen-by-screen presenter script with architecture diagrams  
> **Duration:** ~45 minutes  

---

## Opening

**[SAY]**

"Welcome, everyone. Today I'm going to walk you through ControlNexus — our agentic AI platform for regulatory control mapping. What makes this system unique is not just that it uses large language models, but *how* it uses them — through a carefully engineered, multi-stage pipeline with human-in-the-loop gates, deterministic validation at every step, and full traceability of every AI decision.

Let me take you through each screen of the application, and at each step, I'll show you exactly what's happening under the hood — from the user interface down to the LLM prompt construction."

**[TRANSITION]** "Let's start where every analysis begins — with the data."

---

## Screen 1: Upload & Configure (Tab 1 — 📁 Data Sources)

### [SHOW]

The first tab presents a clean configuration interface with three main sections:

1. **Data Sources panel** (expandable) — Auto-detected regulation files, APQC hierarchy, and control datasets from the `data/` directory. Each data source shows a preview table with row counts and column summaries.
2. **Run Scope panel** — A radio selector offering three modes: "All obligations," "Filter by subpart," or "Quick sample." When filtering, a multiselect of available subparts appears; for sampling, a slider controls the count.
3. **Metrics bar** — Four columns showing Groups to Process, Obligations count, Estimated LLM Calls, and the active LLM Provider (ICA/OpenAI/Deterministic).
4. **Launch button** — "🚀 Start Classification" with a demo mode banner if no data has been processed yet.

### [SAY]

"This is the command center. The system auto-detects three data sources: the regulation Excel file — in this case, the Enhanced Prudential Standards — the APQC Process Classification Framework hierarchy, and the institution's existing control inventory spread across multiple section-specific Excel files.

Notice the scope controls. For a regulation with hundreds of obligations, you don't always want to run the full pipeline. The 'Quick sample' mode lets you test with just a few sections — useful for prompt tuning and validation. The 'Filter by subpart' mode lets you target specific regulatory sections, for example just Subpart D on stress testing.

The metrics bar gives you an instant estimate of the workload — how many groups will be processed, how many LLM calls that translates to, and which provider is active. This is important for cost planning: a full run on 71 obligations might make 200+ LLM calls across four agent phases."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 900px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Data Ingestion & Configuration Pipeline</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Orchestration</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #E65100; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Agent</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #7B1FA2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">LLM Call</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Data / Tools</span></span>
  </div>

  <!-- Flow -->
  <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

    <!-- User Input -->
    <div style="background: #1976D2; color: white; padding: 12px 32px; border-radius: 8px; font-size: 15px; font-weight: 600; min-width: 300px; text-align: center;">
      📁 Upload Tab — User selects scope & data sources
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Config Load -->
    <div style="background: #388E3C; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; min-width: 300px; text-align: center;">
      <strong>init_node</strong> — Load default.yaml → PipelineConfig<br>
      <span style="font-size: 12px; opacity: 0.9;">Load risk_taxonomy.json · Detect LLM provider</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Data Sources Row -->
    <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 160px;">
        <strong>regulation_parser</strong><br>Excel → Obligation[]<br>
        <span style="font-size: 11px; opacity: 0.85;">group_obligations() → ObligationGroup[]</span>
      </div>
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 160px;">
        <strong>apqc_loader</strong><br>Excel → APQCNode[]<br>
        <span style="font-size: 11px; opacity: 0.85;">build_apqc_summary() → prompt text</span>
      </div>
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 160px;">
        <strong>control_loader</strong><br>Excel[] → ControlRecord[]<br>
        <span style="font-size: 11px; opacity: 0.85;">build_control_index() → hierarchy lookup</span>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Scope Filter -->
    <div style="background: #388E3C; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; min-width: 300px; text-align: center;">
      <strong>ingest_node</strong> — Apply scope filter<br>
      <span style="font-size: 12px; opacity: 0.9;">All / Subpart filter / Quick sample → filtered groups</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Context injection label -->
    <div style="background: #FFF3E0; color: #E65100; padding: 6px 20px; border-radius: 16px; font-size: 13px; border: 1px dashed #E65100;">
      ⚙️ Context injected: PipelineConfig enums, risk taxonomy, APQC summary, scope constraints
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Output -->
    <div style="background: #1976D2; color: white; padding: 12px 32px; border-radius: 8px; font-size: 15px; min-width: 300px; text-align: center;">
      Session State populated → Ready for Classification
    </div>

  </div>
</div>
```

### [TRANSITION]

"Before we kick off classification, let me show you a feature that's invaluable during both setup and review — the Data Source Explorer."

---

## Screen 2: Data Source Explorer (Tab 2 — 🔍 Data Source Explorer)

### [SHOW]

The second tab presents three expandable sections, each containing an interactive, paginated HTML table:

1. **📜 Regulations** (expanded by default) — Shows the full regulation dataset with 8 curated columns: Citation, Regulation, Obligation Summary, Status, Subpart, Section, Applicability, and Effective Date. Status values render as colored badges — green for "In Force," amber for "Pending." Long obligation text is truncated at 120 characters with hover tooltips. A search bar filters across citation and abstract text; multiselect dropdowns filter by Status, Regulation, and Subpart.
2. **🗂️ APQC Process Hierarchy** (collapsed) — Displays the APQC tree with 4 columns: Hierarchy ID, Process Name, PCF ID, and Level. Process names are visually indented by depth — level 2 processes are indented 24px, level 3 by 48px, creating a tree-like display. A "Process Family" dropdown filters by top-level category (e.g., "11 — Manage Enterprise Risk"), showing all descendants.
3. **🛡️ Controls** (collapsed) — Shows the merged control inventory with 10 columns including Control ID, Process ID, Control Type, Control Activity, Frequency, Business Unit, and Rating. Control Type badges are color-coded — blue for Preventive, purple for Detective. Rating badges show green for Effective. A "Row Detail" expander lets you inspect hidden columns — when, where, why, full description, and evidence — for any selected row.

All three tables share a common UI pattern: search bar + filter dropdowns + "Showing X of Y" metric + pagination controls (rows-per-page selector, page navigation, page indicator). A ⚙️ Columns popover lets users toggle additional columns from the underlying data model.

### [SAY]

"This is the Data Source Explorer — a reference view where your team can browse and search the raw data before and during the analysis.

The Regulations table gives you every obligation in the regulation, with smart defaults — the 8 most useful columns are shown, but you can toggle any of the 14 parsed fields via the Columns button. Notice the status badges — green for 'In Force,' amber for 'Pending.' The search bar is live — type a citation or keyword and the table filters instantly across citation and obligation summary.

The APQC hierarchy is rendered as an indented tree. The Process Name column indents based on depth — so you can visually scan the hierarchy structure. The Process Family filter lets you drill into a specific domain — say, '9 — Manage Financial Resources' — and see only the descendants.

The Controls table is the most data-dense — 10 default columns with 5 more available via column toggle. It has five filter dropdowns: Control Type, Control Category, Business Unit, Frequency, and Rating. The Row Detail expander at the bottom lets you inspect the full control description, evidence requirements, and who/what/when/where/why fields without leaving the page.

The key architectural decision here is using HTML tables rather than Streamlit's built-in dataframe widget, because we need inline badge rendering — colored status pills, type indicators, rating badges — that `st.dataframe` can't do. The `render_data_table()` component in components.py is a fully reusable, configuration-driven table that accepts column definitions, badge renderers, truncation rules, and filter configs. It powers all three tables from the same code path."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 900px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Data Source Explorer — Component Architecture</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Data / Ingest</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #455A64; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Shared Component</span></span>
  </div>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

    <!-- Data files -->
    <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 150px;">
        <strong>Regulation Excel</strong><br>
        <span style="font-size: 11px;">parse_regulation_excel()<br>→ Obligation[] (14 fields)</span>
      </div>
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 150px;">
        <strong>APQC Excel</strong><br>
        <span style="font-size: 11px;">load_apqc_hierarchy()<br>→ APQCNode[] (5 fields)</span>
      </div>
      <div style="background: #C62828; color: white; padding: 10px 16px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 150px;">
        <strong>Control Excels</strong><br>
        <span style="font-size: 11px;">load_and_merge_controls()<br>→ ControlRecord[] (15 fields)</span>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Cached loaders -->
    <div style="background: #455A64; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
      <strong>@st.cache_data loaders</strong><br>
      <span style="font-size: 12px;">_load_regulations() · _load_apqc() · _load_controls()<br>Parse once, cache in Streamlit session</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- render_data_table -->
    <div style="background: #455A64; color: white; padding: 12px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 420px;">
      <strong>render_data_table()</strong> — Reusable config-driven table component<br>
      <span style="font-size: 12px;">column_keys · label_overrides · badge_columns · truncate_columns<br>search_columns · filter_columns · indent_column · detail_columns · pagination</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Three table instances -->
    <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 150px;">
        <strong>📜 Regulations</strong><br>
        8 default cols<br>
        <span style="font-size: 11px;">Status badges<br>Text truncation<br>3 filter dropdowns</span>
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 150px;">
        <strong>🗂️ APQC Hierarchy</strong><br>
        4 default cols<br>
        <span style="font-size: 11px;">Depth indentation<br>Process Family filter<br>Prefix-match drill-down</span>
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 150px;">
        <strong>🛡️ Controls</strong><br>
        10 default cols<br>
        <span style="font-size: 11px;">Type/Rating badges<br>5 filter dropdowns<br>Row Detail expander</span>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Badge renderers -->
    <div style="background: #FFF3E0; color: #E65100; padding: 6px 20px; border-radius: 16px; font-size: 13px; border: 1px dashed #E65100; text-align: center;">
      ⚙️ BADGE_RENDERERS dict: status → green/amber · selected_level_1 → blue/purple · quality_rating → green/gray
    </div>

  </div>
</div>
```

### [TRANSITION]

"Now that we've seen the raw data, let's kick off the pipeline. When the user clicks 'Start Classification' on the Upload tab, it launches the classify graph. When it completes, we land on the Classification Review screen."

---

## Screen 3: Classification Review (Tab 3 — 🏷️ Classification)

### [SHOW]

A master-detail layout fills the screen:

1. **Header** — "Classification Review (71 obligations)" with a stacked bar chart showing the category distribution: Controls (blue), Documentation (green), Attestation (purple), General Awareness (gray), Not Assigned (red).
2. **Risk Profile** — Three metric cards showing the High / Medium / Low criticality split.
3. **Filter Bar** — Horizontal row of multiselect dropdowns: Category, Criticality, Subpart. A count reads "Showing 71 of 71."
4. **Master panel (left 60%)** — A scrollable list of obligation cards, grouped by subpart. Each card shows: abbreviated CFR citation (e.g., §252.34(a)), a criticality dot (red/orange/green), a colored category pill, and a one-line preview of the obligation text.
5. **Detail panel (right 40%)** — When a card is clicked, the full obligation detail appears: full citation, breadcrumb hierarchy (Title Level 2 → 5), the complete regulatory text in a blue-bordered panel, the abstract summary, applicability and status fields, and a classification block showing category, relationship type, criticality tier with expandable rationale.
6. **Actions bar** — Download for Review (Excel export), Upload Reviewed File, and "✅ Approve and Continue to Mapping."

### [SAY]

"This is where human expertise meets AI output. The classify graph has just processed every obligation through the ObligationClassifierAgent, and now we're looking at the results in a reviewable format.

Let me point out a few things. First, the stacked bar at the top — this gives you an instant read on the distribution. In a well-structured prudential regulation, you'd expect the majority to be Controls, with a smaller share of Documentation and Attestation. If you see a large 'Not Assigned' block, that's a signal to review the LLM's reasoning.

The master-detail layout is intentional. The left panel is your scanning view — you can quickly scroll through obligations, spot patterns, and filter by category or criticality. When something catches your eye, click it, and the right panel gives you the full regulatory context — including the classification rationale the LLM produced.

Now, this is not a black box. The 'Download for Review' button exports everything to Excel with an 'approved' column. Your subject matter expert can review offline, flag disagreements, and re-upload. The system re-imports those corrections — so the human is always in the loop.

Only after explicit approval — clicking 'Approve and Continue to Mapping' — does the pipeline advance. This gating pattern is fundamental to our architecture."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 950px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Classification Pipeline — LangGraph Classify Graph</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Orchestration (LangGraph Nodes)</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #E65100; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Agent</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #7B1FA2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">LLM Call</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Validation / Tools</span></span>
  </div>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

    <!-- UI Trigger -->
    <div style="background: #1976D2; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
      🚀 User clicks "Start Classification"<br>
      <span style="font-size: 12px; opacity: 0.9;">EventEmitter created · TraceDB run initialized</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Loop container -->
    <div style="border: 2px solid #388E3C; border-radius: 12px; padding: 16px; min-width: 500px; background: #f0fff0;">
      <div style="text-align: center; font-size: 13px; color: #388E3C; font-weight: 600; margin-bottom: 12px;">🔄 CLASSIFICATION LOOP — For each ObligationGroup (idx 0..N)</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

        <!-- classify_group node -->
        <div style="background: #388E3C; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
          <strong>classify_group_node</strong><br>
          <span style="font-size: 12px;">groups[classify_idx] → agent.execute()</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <!-- Agent -->
        <div style="background: #E65100; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
          <strong>ObligationClassifierAgent</strong><br>
          <span style="font-size: 12px;">Promontory/IBM RCM methodology</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <!-- Prompt Construction -->
        <div style="background: #FFF3E0; color: #E65100; padding: 8px 18px; border-radius: 16px; font-size: 13px; border: 1px dashed #E65100; text-align: left; min-width: 420px;">
          <strong>⚙️ Prompt Construction:</strong><br>
          • System: Regulatory classification methodology + valid categories/relationships/tiers<br>
          • User: Section citation, section title, regulation name + obligation texts<br>
          • Output schema: JSON with classifications array
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <!-- LLM Call -->
        <div style="background: #7B1FA2; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
          <strong>call_llm(system, user)</strong><br>
          <span style="font-size: 12px;">GPT-4o · temp=0.2 · max_tokens=8000</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <!-- Validation -->
        <div style="background: #C62828; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
          <strong>validate_classification()</strong><br>
          <span style="font-size: 12px;">Category ∈ valid set · Criticality ∈ tiers · Relationship ∈ types</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <!-- State accumulation -->
        <div style="background: #388E3C; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 300px;">
          classified_obligations += results<br>
          <span style="font-size: 11px; opacity: 0.9;">classify_idx += 1 · Annotated[list, operator.add]</span>
        </div>
      </div>

      <div style="text-align: center; margin-top: 12px;">
        <span style="background: #388E3C; color: white; padding: 4px 16px; border-radius: 12px; font-size: 12px;">has_more_classify_groups? → loop or → end_classify</span>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Checkpoint -->
    <div style="background: #455A64; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
      💾 save_checkpoint(STAGE_CLASSIFIED) → JSON<br>
      <span style="font-size: 12px;">Metadata: timestamp, obligation_count, category_breakdown</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- UI Result -->
    <div style="background: #1976D2; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
      🏷️ Classification Review Tab renders<br>
      <span style="font-size: 12px;">Master-detail layout · Filter bar · Export/Import cycle</span>
    </div>

  </div>
</div>
```

### [TRANSITION]

"Once the analyst approves the classifications, they click the approval button, which triggers the second graph — the assess graph. This starts with APQC mapping. Let's look at that next."

---

## Screen 4: APQC Mapping Review (Tab 4 — 🗺️ Mapping)

### [SHOW]

The Mapping Review tab follows the same master-detail pattern:

1. **Header** — "APQC Mapping Review" with four metric cards: Obligations Mapped, Total Mappings (many-to-many), Average Confidence score, and Relationship Types count.
2. **Stacked bar** — Same category distribution, now with mapping counts overlaid.
3. **Filter bar** — Category, Criticality, Subpart filters.
4. **Master panel (left 60%)** — Obligation cards identical to Tab 3, but each card now shows an extra label: "**3 mapping(s)**" indicating how many APQC processes this obligation maps to.
5. **Detail panel (right 40%)** — Selected obligation detail plus a **Mappings section** below it. Each mapping renders as a "chip" component showing: APQC process name (bold), hierarchy ID (e.g., `11.1.1`), relationship type, and a color-coded confidence score (green ≥ 0.8, orange ≥ 0.5, red < 0.5). Each chip is expandable to show the relationship detail text.
6. **Actions** — Download/upload mappings, checkpoint save/load, and "✅ Approve and Run Coverage Assessment."

### [SAY]

"Now we're looking at the APQC mapping results. This is where each regulatory obligation gets connected to the institution's business process taxonomy. The APQCMapperAgent has mapped each obligation to up to five APQC processes, with confidence scores and relationship details.

Let me click on an obligation — say, §252.34(a) on liquidity stress testing. You can see it's been mapped to three APQC processes: 'Manage enterprise risk' at 11.1.1, 'Manage liquidity risk' at 9.7.1, and 'Manage stress testing' at 11.1.3. Each mapping has a confidence score — 0.92 for the risk framework mapping, which makes sense because that's a direct regulatory-to-process alignment.

The confidence scores matter because they flow into the coverage assessment. A high-confidence mapping with no matching control is a high-priority gap. A low-confidence mapping might indicate the LLM was uncertain about the process alignment, which is where the analyst's review becomes critical.

This is the second human gate — the analyst reviews, corrects if needed, and only then approves the assessment run."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 950px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">APQC Mapping & Coverage Assessment — Assess Graph</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Orchestration</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #E65100; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Agent</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #7B1FA2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">LLM Call</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Tools / Data</span></span>
  </div>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

    <!-- Human Gate -->
    <div style="background: #1976D2; color: white; padding: 10px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 400px;">
      ✅ Analyst approves classifications → triggers Assess Graph
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Phase 1: Mapping Loop -->
    <div style="border: 2px solid #E65100; border-radius: 12px; padding: 16px; min-width: 550px; background: #FFF8E1;">
      <div style="text-align: center; font-size: 13px; color: #E65100; font-weight: 600; margin-bottom: 10px;">PHASE 1: APQC MAPPING LOOP</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
        <div style="background: #388E3C; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>map_group_node</strong> — mappable_groups[map_idx]
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #E65100; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>APQCMapperAgent</strong>.execute(obligations, apqc_summary)
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #FFF3E0; color: #E65100; padding: 6px 16px; border-radius: 12px; font-size: 12px; border: 1px dashed #E65100; text-align: left; min-width: 400px;">
          <strong>⚙️ Context Engineering:</strong><br>
          • APQC hierarchy summary (indented text, depth=3) injected into system prompt<br>
          • Regulation name + section citation provide regulatory context<br>
          • Config: max 5 mappings/obligation, hierarchy depth 3<br>
          • Output: JSON {mappings: [{citation, apqc_id, confidence, relationship_detail}]}
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #7B1FA2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>LLM</strong>: GPT-4o · temp=0.2 · APQC summary (≤15K chars)
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #C62828; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>validate_mapping()</strong> — apqc_id, confidence ∈ [0,1], detail present
        </div>
        <div style="text-align: center; margin-top: 8px;">
          <span style="background: #E65100; color: white; padding: 3px 14px; border-radius: 10px; font-size: 11px;">obligation_mappings += results · map_idx++ · loop until done</span>
        </div>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Phase 2: Prepare Assessment -->
    <div style="background: #388E3C; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 400px;">
      <strong>prepare_assessment_node</strong><br>
      <span style="font-size: 12px;">Build control_index · Match mappings to candidate controls via find_controls_for_apqc()</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Phase 3: Coverage Loop -->
    <div style="border: 2px solid #7B1FA2; border-radius: 12px; padding: 16px; min-width: 550px; background: #F3E5F5;">
      <div style="text-align: center; font-size: 13px; color: #7B1FA2; font-weight: 600; margin-bottom: 10px;">PHASE 2: COVERAGE ASSESSMENT LOOP</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
        <div style="background: #E65100; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>CoverageAssessorAgent</strong> — evaluate each candidate control
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #FFF3E0; color: #E65100; padding: 6px 16px; border-radius: 12px; font-size: 12px; border: 1px dashed #E65100; text-align: left; min-width: 400px;">
          <strong>⚙️ Three-Layer Assessment:</strong><br>
          1. <strong>Structural Match</strong> — Does control hierarchy_id prefix-match APQC?<br>
          2. <strong>Semantic Match</strong> — LLM rates description alignment (Full/Partial/None)<br>
          3. <strong>Relationship Match</strong> — LLM validates control satisfies obligation type<br>
          → Covered = Full semantic + Satisfied relationship
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #455A64; color: white; padding: 6px 16px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 320px;">
          💾 _partial_assessments.append() · Auto-save every 25 items
        </div>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Phase 4: Risk -->
    <div style="border: 2px solid #C62828; border-radius: 12px; padding: 16px; min-width: 550px; background: #FFEBEE;">
      <div style="text-align: center; font-size: 13px; color: #C62828; font-weight: 600; margin-bottom: 10px;">PHASE 3: RISK EXTRACTION & SCORING</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
        <div style="background: #388E3C; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>prepare_risks_node</strong> — filter gaps (Not Covered + Partial)
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #E65100; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>RiskExtractorAndScorerAgent</strong>.execute(gap, taxonomy, scales)
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #FFF3E0; color: #E65100; padding: 6px 16px; border-radius: 12px; font-size: 12px; border: 1px dashed #E65100; text-align: left; min-width: 400px;">
          <strong>⚙️ Context Injection:</strong><br>
          • Risk taxonomy (8 categories × 40+ sub-risks) from risk_taxonomy.json<br>
          • Impact scale (4-point: Minor→Severe with financial/operational descriptors)<br>
          • Frequency scale (4-point: Remote→Likely with temporal definitions)<br>
          • Gap rationale from CoverageAssessor as context for risk identification
        </div>
        <div style="font-size: 14px; color: #888;">↓</div>
        <div style="background: #C62828; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 320px;">
          <strong>derive_inherent_rating()</strong> — impact × frequency → Critical/High/Medium/Low
        </div>
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Finalize -->
    <div style="background: #388E3C; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 400px;">
      <strong>finalize_node</strong> — Assemble GapReport + ComplianceMatrix + RiskRegister
    </div>

  </div>
</div>
```

### [TRANSITION]

"After the full assessment completes — mapping, coverage, risk scoring, and report assembly — the results land on the executive dashboard. This is where all four phases come together."

---

## Screen 5: Results Dashboard (Tab 5 — 📊 Results)

### [SHOW]

The Results tab is a rich executive dashboard:

1. **Partial results warning** (if applicable) — Orange banner showing "45 of 71 assessed. Resume from checkpoint to complete."
2. **Key Metrics row** — Four large cards: Total Assessed (71), ✅ Covered (42, 59%), ❌ Gaps (29, 41% — combines Partial + Not Covered), Risks Identified (18).
3. **Stacked Coverage Bar** — Horizontal bar with three colored segments: green (Covered), orange (Partially Covered), red (Not Covered), with percentage labels below.
4. **Two-column layout**:
   - **Left: Risk Heatmap** — A 4×4 matplotlib grid (Impact 1–4 vs. Frequency 1–4). Cell colors: red (score ≥12), orange (≥8), yellow (≥4), green (<4). Each cell shows the count of risks in that quadrant. Below: risk distribution by category breakdown.
   - **Right: Top Gaps** — The 8 most severe gaps, sorted "Not Covered" first, then "Partially Covered." Each row shows: citation, coverage status badge, APQC process, and control ID.
5. **Expandable: Gap Analysis** — Grouped under "Not Covered" and "Partially Covered" headers. Each gap shows: citation, coverage status, APQC process, semantic/relationship match scores, control ID, and an expandable rationale subsection.
6. **Expandable: Risk Register** — Grouped by risk category (Compliance Risk, Operational Risk, etc.). Each risk shows: risk ID (e.g., RISK-001), source citation, description, rating badge (color-coded), and impact/frequency breakdown.
7. **Export** — Download full compliance report as multi-sheet Excel workbook.

### [SAY]

"This is the executive view — where the analysis crystallizes into actionable intelligence.

The four cards at the top give you the instant snapshot: 71 obligations assessed, 59% fully covered, 41% have gaps, and 18 distinct risks identified. The stacked bar makes that ratio visceral — you can immediately see the green-orange-red split.

The risk heatmap is where it gets interesting. This is a standard 4×4 impact-versus-frequency matrix — the same framework your risk team already uses. But instead of being manually populated, it's been generated by the RiskExtractorAndScorerAgent using the institution's own impact scale definitions. Those definitions — 'Severe means ≥2 quarters pre-tax income or ≥$5B outflow' — are injected directly into the LLM prompt from the config. So the AI is scoring against *your* risk appetite, not generic criteria.

The Top Gaps panel prioritizes attention. 'Not Covered' obligations with no matching control surface first. Each gap links back to the specific obligation, APQC process, and the candidate control that fell short.

Down in the expandable sections, you get full transparency. The Gap Analysis shows the three-layer coverage logic — structural, semantic, and relationship match — with rationale text explaining *why* a control was judged insufficient. The Risk Register groups risks by taxonomy category and includes the LLM's impact and frequency rationale.

The Excel export produces a six-sheet workbook: Summary, Classifications, Mappings, Coverage Assessments, Gaps, and Risk Register. This is the artifact that goes to your audit committee."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 900px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Results Dashboard — Data Assembly</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Rendering</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Report Assembly</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Data Sources</span></span>
  </div>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">

    <!-- Data Sources -->
    <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #C62828; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 130px;">
        <strong>classified<br>obligations</strong><br>71 items
      </div>
      <div style="background: #C62828; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 130px;">
        <strong>obligation<br>mappings</strong><br>145 mappings
      </div>
      <div style="background: #C62828; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 130px;">
        <strong>coverage<br>assessments</strong><br>71 assessments
      </div>
      <div style="background: #C62828; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 130px;">
        <strong>scored<br>risks</strong><br>18 risks
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Assembly -->
    <div style="background: #388E3C; color: white; padding: 12px 28px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 420px;">
      <strong>finalize_node</strong> — Report Assembly<br>
      <span style="font-size: 12px;">
        GapReport (coverage_summary, gaps list)<br>
        ComplianceMatrix (obligation × control × APQC rows)<br>
        RiskRegister (risks by category, distribution counts)
      </span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- UI Components -->
    <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 120px;">
        <strong>Metric Cards</strong><br>4 KPI cards<br>coverage %
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 120px;">
        <strong>Coverage Bar</strong><br>Stacked HTML<br>3 segments
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 120px;">
        <strong>Risk Heatmap</strong><br>4×4 matplotlib<br>impact × freq
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 120px;">
        <strong>Gap Analysis</strong><br>Grouped expanders<br>3-layer rationale
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 120px;">
        <strong>Risk Register</strong><br>By category<br>rating badges
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Export -->
    <div style="background: #455A64; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 350px;">
      📥 Excel Export — 6-sheet workbook<br>
      <span style="font-size: 12px;">Summary · Classifications · Mappings · Coverage · Gaps · Risk Register</span>
    </div>

  </div>
</div>
```

### [TRANSITION]

"The results dashboard gives you the 'what.' But for deployment confidence, you need the 'how' and 'why.' That's where traceability comes in."

---

## Screen 6: Traceability (Tab 6 — 🔗 Traceability)

### [SHOW]

The Traceability tab is a developer-facing observability dashboard:

1. **Run Selector** — A dropdown listing all pipeline runs, formatted as "🟢 classify — Enhanced Prudential Standards — 2026-04-13 04:37" with status icons (🟡 Running, 🟢 Completed, 🔴 Failed).
2. **Run Overview** — Five metric cards: Status indicator, Nodes Executed (e.g., 12), LLM Calls (e.g., 89), Total Tokens (e.g., 428,000), Node Time (e.g., 47.3s).
3. **Event Timeline** — A DataFrame table with columns: Time (HH:MM:SS), Event Type (color-coded: blue for pipeline, green for completion, red for errors), Stage, and Message text.
4. **Node Executions** — DataFrame with columns: Node name, Duration (ms), Input summary, Output summary, Error. Accompanied by a horizontal bar chart showing duration by node — the classify_group and assess_coverage nodes dominate.
5. **LLM Call Inspector** — The most detailed section:
   - Summary metrics: Total calls, prompt tokens, completion tokens, average latency.
   - Call table: Time, Node, Agent, Model, Prompt Tokens, Completion Tokens, Latency, Error.
   - Token usage bar chart by node.
   - **Expandable per-call details**: For each LLM call, you can expand to see the complete system prompt, user prompt, and raw response text.
6. **Maintenance** — Purge old runs (keep latest 20), delete individual runs.
7. **Data Lineage** — Nested expanders showing obligation → mapping → assessment → risk chains, organized by subpart.

### [SAY]

"This is where transparency becomes concrete. Every pipeline run generates a complete audit trail in a local SQLite database — zero infrastructure, just a file on disk.

The Event Timeline gives you a chronological record of every pipeline event — when ingestion started, when each group was classified, when validation passed or failed. These aren't just log lines — they're structured PipelineEvent objects with typed event categories.

The Node Executions view is your performance profiling tool. You can see exactly which graph nodes took the longest. In a typical run, classify_group dominates because it's where most LLM calls happen. But if assess_coverage suddenly spikes, that might indicate your control dataset has too many candidates per APQC process, causing unnecessary LLM evaluations.

The LLM Call Inspector is the crown jewel. Expand any call and you see the *exact* system prompt and user prompt that were sent to the model, plus the raw response. This is complete reproducibility — if a classification seems wrong, you can see exactly what context the LLM received, what it returned, and why the validator accepted or rejected it.

The Data Lineage section at the bottom connects the dots vertically. Pick any obligation, and you can trace it from its classification → to its APQC mapping → to its coverage assessment → to its risk score. This is the full chain of evidence that an auditor would need."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 950px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Tracing Architecture — Full Observability Stack</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Orchestration</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #7B1FA2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Tracing Middleware</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Storage</span></span>
  </div>

  <div style="display: flex; gap: 24px; justify-content: center; align-items: flex-start; flex-wrap: wrap;">

    <!-- Left: Trace Capture -->
    <div style="flex: 1; min-width: 350px;">
      <div style="text-align: center; font-weight: 600; color: #333; margin-bottom: 12px;">Capture Layer (Runtime)</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
        <div style="background: #388E3C; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>Graph Node Execution</strong><br>
          <span style="font-size: 11px;">classify_group · map_group · assess_coverage</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #7B1FA2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>trace_node decorator</strong><br>
          <span style="font-size: 11px;">Sets thread-local context (node_name, agent_name)<br>
          Records node start/end/duration/state summary</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #7B1FA2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>TracingTransportClient</strong><br>
          <span style="font-size: 11px;">Wraps AsyncTransportClient<br>
          Intercepts every chat_completion() call<br>
          Records: prompts, response, tokens, latency</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #7B1FA2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>SQLiteTraceListener</strong><br>
          <span style="font-size: 11px;">Persists EventEmitter events to events table<br>
          Updates run status on lifecycle events</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #C62828; color: white; padding: 10px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>SQLite TraceDB</strong><br>
          <span style="font-size: 11px;">
            runs · events · node_executions<br>
            llm_calls · run_metrics · run_comparisons<br>
            WAL mode · zero-config
          </span>
        </div>
      </div>
    </div>

    <!-- Right: Query Layer -->
    <div style="flex: 1; min-width: 350px;">
      <div style="text-align: center; font-weight: 600; color: #333; margin-bottom: 12px;">Query Layer (UI)</div>

      <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
        <div style="background: #1976D2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>Run Selector</strong><br>
          <span style="font-size: 11px;">list_runs(limit=50) → status-tagged dropdown</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #1976D2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>Event Timeline</strong><br>
          <span style="font-size: 11px;">get_run_events(run_id) → DataFrame</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #1976D2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>Node Executions</strong><br>
          <span style="font-size: 11px;">get_run_nodes(run_id) → timing + bar chart</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #1976D2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>LLM Call Inspector</strong><br>
          <span style="font-size: 11px;">get_run_llm_calls(run_id) → per-call detail<br>
          Expandable: system prompt, user prompt, response</span>
        </div>
        <div style="font-size: 16px; color: #888;">↓</div>

        <div style="background: #1976D2; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; text-align: center; min-width: 280px;">
          <strong>Data Lineage</strong><br>
          <span style="font-size: 11px;">Obligation → Mapping → Assessment → Risk<br>
          Nested expanders by subpart</span>
        </div>
      </div>
    </div>

  </div>
</div>
```

### [TRANSITION]

"Traceability tells you *what happened* in a single run. But when you're iterating on prompts or comparing models, you need to compare *across* runs. That's what the Evaluation tab does."

---

## Screen 7: Evaluation (Tab 7 — 📈 Evaluation)

### [SHOW]

The Evaluation tab is a model-ops dashboard:

1. **Run History** — A table listing all pipeline runs with columns: Run ID, Regulation, Model, Provider, Total Tokens, Estimated Cost (USD), Pass Rate (%), Quality Score, Coverage Rate, LLM Call count. A selectbox chooses a run for detail view.
2. **Run Detail** (when selected):
   - Four metric cards: Total Tokens, Estimated Cost, Quality Score, Pass Rate.
   - **Per-Phase Breakdown** table — rows for Classify, Map, Assess, Risk — showing Total, Passed, Retries, and Pass Rate per phase.
   - **Mapping Confidence** — Average confidence metric.
   - **Coverage Distribution** — Stacked bar (Covered/Partial/Gap).
   - **Category Distribution** — Bar chart of obligation categories.
   - **Risk Distribution** — Bar chart of risk ratings.
3. **Run Comparison** — Select two runs (Run A, Run B) side-by-side:
   - Metrics compared: Tokens, Cost, Quality, Pass Rate, LLM Calls, Avg Latency.
   - Delta indicators — colored arrows (↑ green = better, ↓ red = worse) with delta values.
   - **Agreement metrics** (if same regulation): Classification Agreement %, Mapping Overlap %, Coverage Agreement %.
4. **Cost vs Quality Scatter** — Matplotlib chart: X = Estimated Cost (USD), Y = Quality Score [0,1]. Points colored by model. "Upper-left is best."

### [SAY]

"The Evaluation tab is where engineering meets ROI. Every pipeline run generates aggregated metrics — token usage, estimated cost, quality score, and pass rates — stored alongside the trace data.

The Quality Score is a composite metric — it blends validation pass rate (30%), retry efficiency (25%), mapping confidence (20%), coverage completeness (15%), and latency (10%). It's designed to capture both correctness and cost-effectiveness.

The Per-Phase Breakdown is critical for prompt engineering. If your classify pass rate is 98% but your risk scoring pass rate drops to 70%, you know exactly where to focus. Low pass rates mean the validator is rejecting LLM outputs — maybe the system prompt isn't constraining the output format tightly enough, or the model is generating description lengths outside the 20–60 word window the validator expects.

Run Comparison is where model evaluation becomes data-driven. Select a GPT-4o run versus a Claude run on the same regulation, and you get side-by-side metrics with deltas. The Agreement metrics tell you how much the two models agree — Classification Agreement is the percentage of obligations they assigned to the same category; Mapping Overlap is Jaccard similarity of APQC process sets; Coverage Agreement is the percentage they assessed identically.

The Cost vs Quality scatter puts it all on one chart. Upper-left is the sweet spot — low cost, high quality. If GPT-4o achieves 0.92 quality at $2.40 and a smaller model hits 0.85 at $0.60, you can make an informed decision."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 950px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">Evaluation System — Metrics & Comparison Pipeline</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Computation</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Storage</span></span>
  </div>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">

    <!-- Data source -->
    <div style="background: #C62828; color: white; padding: 10px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 400px;">
      <strong>TraceDB — run_metrics table</strong><br>
      <span style="font-size: 12px;">total_tokens · est_cost · quality_score · pass_rate · phase breakdowns</span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Computation -->
    <div style="background: #388E3C; color: white; padding: 12px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 450px;">
      <strong>compute_run_metrics(run_id)</strong><br>
      <span style="font-size: 12px;">
        Aggregates from llm_calls table:<br>
        • Per-phase pass rates (classify / map / assess / risk)<br>
        • Token usage & cost via COST_PER_1K_TOKENS dict<br>
        • Quality Score = 0.30×pass + 0.25×(1−retry) + 0.20×conf + 0.15×cov + 0.10×latency
      </span>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Run-level views -->
    <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 140px;">
        <strong>Run History</strong><br>list_run_metrics()
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 140px;">
        <strong>Run Detail</strong><br>get_run_metrics()
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 140px;">
        <strong>Comparison</strong><br>compare_runs()
      </div>
      <div style="background: #1976D2; color: white; padding: 10px 14px; border-radius: 8px; font-size: 12px; text-align: center; min-width: 140px;">
        <strong>Cost vs Quality</strong><br>get_cost_history()
      </div>
    </div>
    <div style="font-size: 20px; color: #888;">↓</div>

    <!-- Comparison detail -->
    <div style="background: #388E3C; color: white; padding: 12px 24px; border-radius: 8px; font-size: 14px; text-align: center; min-width: 450px;">
      <strong>compare_runs(A, B)</strong><br>
      <span style="font-size: 12px;">
        Token delta · Cost delta · Quality delta<br>
        Classification Agreement % (same categories on shared citations)<br>
        Mapping Overlap % (Jaccard similarity of APQC sets)<br>
        Coverage Agreement % (same status on shared citations)
      </span>
    </div>

  </div>
</div>
```

### [TRANSITION]

"Let me step back and give you a bird's-eye view of the entire system architecture — how all these pieces fit together."

---

## System Architecture Overview

### [SHOW]

"I want to show you one final diagram that captures the complete system architecture."

### [SAY]

"Here's the full picture. ControlNexus is a three-layer architecture: the Streamlit UI on top, the LangGraph orchestration layer in the middle, and the agent-tool-LLM stack at the bottom.

The key architectural decisions:

**First, the deterministic-stochastic-deterministic sandwich.** Ingest and export are fully deterministic — no AI, just data transformation. The four middle phases use LLMs with validation gates. This means your inputs and outputs are predictable and auditable; only the reasoning steps involve AI.

**Second, the context engineering.** Every LLM call receives carefully constructed context: the APQC hierarchy summary, the control descriptions, the risk taxonomy with financial impact definitions, the relationship type vocabulary. This isn't generic prompt engineering — it's domain knowledge injection from the institution's own frameworks.

**Third, the accumulation pattern.** LangGraph's `Annotated[list, operator.add]` enables loop state — each node appends its results, and conditional edges control the loop. This gives us batch processing with per-item tracing.

**Fourth, resilience.** Partial assessment checkpoints save every 25 items. If the pipeline fails at item 45 of 71, you don't lose the first 44. The checkpoint system saves stage-specific state with full metadata — timestamp, mode, counts — so you can resume precisely.

**Fifth, multi-provider support.** The AsyncTransportClient abstracts over IBM Cloud AI and OpenAI APIs. The TracingTransportClient wraps it transparently for observability. Switching providers is a configuration change, not a code change.

**Sixth, config-driven UI.** The tab layout is driven by `default.yaml` — the `ui.visible_tabs` list controls which of the 7 registered tabs appear. By default, the workflow tabs are visible — Upload, Data Explorer, Classification Review, Mapping Review, and Results — while the developer-facing Traceability and Evaluation tabs are hidden. Uncommenting a single line in the config restores them. This keeps the analyst-facing experience clean while preserving full diagnostic capabilities for engineering."

### [DEEP DIVE DIAGRAM]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; background: #fafafa; border-radius: 12px; max-width: 1000px; margin: 0 auto;">
  <h3 style="text-align: center; color: #333; margin-bottom: 20px;">ControlNexus — Complete System Architecture</h3>

  <!-- Legend -->
  <div style="display: flex; gap: 16px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap;">
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #1976D2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">UI Layer (Streamlit)</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #388E3C; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Orchestration (LangGraph)</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #E65100; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Agents</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #7B1FA2; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">LLM Provider</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #C62828; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Data / Tools</span></span>
    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 14px; height: 14px; background: #455A64; border-radius: 3px; display: inline-block;"></span> <span style="font-size: 13px;">Persistence</span></span>
  </div>

  <!-- LAYER 1: UI -->
  <div style="border: 2px solid #1976D2; border-radius: 12px; padding: 12px; margin-bottom: 12px; background: #E3F2FD;">
    <div style="font-size: 12px; color: #1976D2; font-weight: 700; margin-bottom: 8px;">PRESENTATION LAYER — Config-Driven Tab Application (7 registered, 5 visible by default)</div>
    <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #1976D2; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">📁 Upload &<br>Configure</div>
      <div style="background: #1976D2; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">🔍 Data Source<br>Explorer</div>
      <div style="background: #1976D2; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">🏷️ Classification<br>Review</div>
      <div style="background: #1976D2; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">🗺️ Mapping<br>Review</div>
      <div style="background: #1976D2; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">📊 Results<br>Dashboard</div>
      <div style="background: #757575; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px; opacity: 0.6;">🔗 Trace<br>Viewer</div>
      <div style="background: #757575; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px; opacity: 0.6;">📈 Evaluation<br>Metrics</div>
    </div>
    <div style="text-align: center; margin-top: 8px; font-size: 11px; color: #666;">
      Session State · EventEmitter events · Config-driven tab visibility (default.yaml → ui.visible_tabs)
    </div>
  </div>

  <!-- Human gates -->
  <div style="display: flex; justify-content: center; gap: 60px; margin: 8px 0;">
    <div style="background: #FFF3E0; color: #E65100; padding: 4px 14px; border-radius: 12px; font-size: 11px; border: 1px dashed #E65100;">🧑 Human Gate: Approve Classification</div>
    <div style="background: #FFF3E0; color: #E65100; padding: 4px 14px; border-radius: 12px; font-size: 11px; border: 1px dashed #E65100;">🧑 Human Gate: Approve Mapping</div>
  </div>

  <!-- LAYER 2: ORCHESTRATION -->
  <div style="border: 2px solid #388E3C; border-radius: 12px; padding: 12px; margin-bottom: 12px; background: #E8F5E9;">
    <div style="font-size: 12px; color: #388E3C; font-weight: 700; margin-bottom: 8px;">ORCHESTRATION LAYER — Two LangGraph State Machines</div>
    <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
      <!-- Classify Graph -->
      <div style="border: 1px solid #388E3C; border-radius: 8px; padding: 10px; min-width: 300px; background: white;">
        <div style="font-size: 12px; font-weight: 600; color: #388E3C; margin-bottom: 6px;">Graph 1: Classify</div>
        <div style="font-size: 11px; color: #555;">
          init → ingest → <strong>classify_group</strong> ↻ → end<br>
          <span style="color: #888;">ClassifyState with accumulation (operator.add)</span>
        </div>
      </div>
      <!-- Assess Graph -->
      <div style="border: 1px solid #388E3C; border-radius: 8px; padding: 10px; min-width: 300px; background: white;">
        <div style="font-size: 12px; font-weight: 600; color: #388E3C; margin-bottom: 6px;">Graph 2: Assess</div>
        <div style="font-size: 11px; color: #555;">
          <strong>map_group</strong> ↻ → prepare → <strong>assess_coverage</strong> ↻<br>
          → prepare_risks → <strong>extract_and_score</strong> ↻ → finalize<br>
          <span style="color: #888;">AssessState · auto-save every 25 items</span>
        </div>
      </div>
    </div>
    <div style="text-align: center; margin-top: 8px; font-size: 11px; color: #666;">
      GraphInfra singleton: LLM client cache · Agent cache · Event loop management
    </div>
  </div>

  <!-- LAYER 3: AGENTS -->
  <div style="border: 2px solid #E65100; border-radius: 12px; padding: 12px; margin-bottom: 12px; background: #FFF3E0;">
    <div style="font-size: 12px; color: #E65100; font-weight: 700; margin-bottom: 8px;">AGENT LAYER — Four Specialized Agents (BaseAgent subclasses)</div>
    <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #E65100; color: white; padding: 8px 12px; border-radius: 6px; font-size: 11px; text-align: center; min-width: 170px;">
        <strong>ObligationClassifier</strong><br>
        Promontory/IBM RCM<br>
        Category · Relationship · Criticality
      </div>
      <div style="background: #E65100; color: white; padding: 8px 12px; border-radius: 6px; font-size: 11px; text-align: center; min-width: 170px;">
        <strong>APQCMapper</strong><br>
        APQC PCF framework<br>
        Hierarchy ID · Confidence
      </div>
      <div style="background: #E65100; color: white; padding: 8px 12px; border-radius: 6px; font-size: 11px; text-align: center; min-width: 170px;">
        <strong>CoverageAssessor</strong><br>
        3-layer evaluation<br>
        Structural · Semantic · Relationship
      </div>
      <div style="background: #E65100; color: white; padding: 8px 12px; border-radius: 6px; font-size: 11px; text-align: center; min-width: 170px;">
        <strong>RiskExtractor&Scorer</strong><br>
        8-category taxonomy<br>
        4×4 impact × frequency
      </div>
    </div>
    <div style="text-align: center; margin-top: 8px; font-size: 11px; color: #666;">
      AgentContext injection · Deterministic fallbacks · JSON parse with recovery · Validation per output
    </div>
  </div>

  <!-- LAYER 4: Infrastructure -->
  <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
    <!-- LLM -->
    <div style="border: 2px solid #7B1FA2; border-radius: 12px; padding: 10px; min-width: 200px; background: #F3E5F5; text-align: center;">
      <div style="font-size: 12px; color: #7B1FA2; font-weight: 700; margin-bottom: 4px;">LLM Provider</div>
      <div style="font-size: 11px; color: #555;">
        AsyncTransportClient<br>
        → TracingTransportClient (wrapper)<br>
        IBM Cloud AI / OpenAI<br>
        Exponential backoff + jitter
      </div>
    </div>

    <!-- Data Sources -->
    <div style="border: 2px solid #C62828; border-radius: 12px; padding: 10px; min-width: 200px; background: #FFEBEE; text-align: center;">
      <div style="font-size: 12px; color: #C62828; font-weight: 700; margin-bottom: 4px;">Data Sources</div>
      <div style="font-size: 11px; color: #555;">
        Regulation (Excel)<br>
        APQC Hierarchy (Excel)<br>
        Controls (multi-Excel)<br>
        Risk Taxonomy (JSON)
      </div>
    </div>

    <!-- Persistence -->
    <div style="border: 2px solid #455A64; border-radius: 12px; padding: 10px; min-width: 200px; background: #ECEFF1; text-align: center;">
      <div style="font-size: 12px; color: #455A64; font-weight: 700; margin-bottom: 4px;">Persistence</div>
      <div style="font-size: 11px; color: #555;">
        Checkpoints (JSON files)<br>
        TraceDB (SQLite · WAL mode)<br>
        Excel exports (6-sheet reports)
      </div>
    </div>

    <!-- Config -->
    <div style="border: 2px solid #FF6F00; border-radius: 12px; padding: 10px; min-width: 200px; background: #FFF8E1; text-align: center;">
      <div style="font-size: 12px; color: #FF6F00; font-weight: 700; margin-bottom: 4px;">Configuration</div>
      <div style="font-size: 11px; color: #555;">
        default.yaml (PipelineConfig)<br>
        risk_taxonomy.json<br>
        Environment variables<br>
        (ICA/OpenAI credentials)
      </div>
    </div>
  </div>

</div>
```

---

## Closing

### [SAY]

"Let me wrap up with the key architectural principles that make ControlNexus production-ready:

**One — Explainability over automation.** Every AI decision is traceable. You can inspect the exact prompt, response, and validation result for every LLM call. This isn't a black box — it's a glass box with audit-grade transparency.

**Two — Human-in-the-loop by design.** The pipeline has explicit approval gates between classification and mapping, and between mapping and assessment. Analysts can review, correct, and re-import at every stage. The AI accelerates; the human validates.

**Three — Resilience.** Partial checkpoints, auto-save intervals, deterministic fallbacks, and graceful degradation to non-LLM mode mean the pipeline can handle failures without losing work.

**Four — Cost-aware engineering.** The evaluation system tracks token usage, estimates costs, and benchmarks quality — giving you the data to make informed decisions about model selection and prompt optimization.

**Five — Domain-native context.** The system speaks the language of financial regulation — APQC process classification, Promontory-style obligation categorization, SCB-framework risk scoring scales. The AI is grounded in institutional frameworks, not generic knowledge.

**Six — Configurable experience.** The tab layout, visible features, and even which data columns appear are all configuration-driven. The same platform serves both the analyst who needs a clean five-tab workflow and the engineer who needs full diagnostic depth — controlled by a single YAML file.

Thank you. I'm happy to take questions on any part of the architecture."

---

*End of Technical Walkthrough Script*
