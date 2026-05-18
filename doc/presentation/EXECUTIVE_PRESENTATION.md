# ControlNexus — Executive Presentation Script

> **Audience:** C-suite / Senior Stakeholders at a Financial Institution  
> **Format:** Business-outcome-focused walkthrough with curated live demo  
> **Duration:** ~25 minutes  
> **Tone:** Confident, conversational, zero unexplained jargon  

---

## 1. The Problem

### [SAY]

"Thank you for your time today. Before I show you anything, I want to talk about a challenge I know your teams face every day — because it's the same challenge we hear from every large financial institution we work with.

Your regulatory obligations are growing — in volume, in complexity, and in the speed at which they change. Right now, when a new regulation drops — or an existing one is amended — your compliance and risk teams have to do something incredibly labor-intensive: they read every obligation, classify what type of requirement it is, figure out which business processes it affects, check whether your existing controls actually cover it, and identify the risks where gaps exist.

That process — regulation to controls to gaps to risks — is the backbone of your compliance posture. And today, it's largely manual. Subject matter experts spend weeks per regulation mapping obligations to your process taxonomy, cross-referencing your control inventory, and documenting the gaps for your audit committee.

Three things make this unsustainable:

**First, inconsistency.** Two analysts can read the same obligation and categorize it differently. The mapping results depend on who does the work, how much time they have, and which controls they happen to know about. There's no standardized methodology enforced at scale.

**Second, speed.** A regulation with 300 obligations and a thousand candidate controls — you're looking at weeks of analyst time. Multiply that across every regulatory change per year, and you have a permanent backlog. Gaps that exist today aren't identified until months later.

**Third, audit risk.** When regulators ask 'How did you determine that this obligation is covered?' — your answer needs to be traceable, documented, and defensible. Manual spreadsheet-based processes don't give you that. They give you a result, but not the reasoning chain behind it."

### [TRANSITION]

"That's the problem. Let me show you what a solution looks like."

---

## 2. The Solution — ControlNexus

### [SAY]

"ControlNexus is an AI-powered platform that automates the regulation-to-risk pipeline — from raw regulatory text to a fully documented gap analysis and risk register.

Here's what it does, in plain terms:

**You feed it a regulation.** It reads every obligation, understands what type of requirement it is, and classifies it — is it requiring a specific control? An attestation? Documentation? General awareness?

**It maps to your business processes.** Using your institution's own process taxonomy — the APQC framework — it identifies which business processes each obligation affects. Not generic mappings. Your taxonomy, your hierarchy.

**It evaluates your existing controls.** For each obligation-process pair, it checks your control inventory to determine whether you're covered, partially covered, or have a gap. It doesn't just match keywords — it reads the control description, understands the relationship, and makes a judgment call.

**It scores the risks.** Where gaps exist, it identifies the specific risks — using your risk taxonomy and your impact scales — and gives you a scored risk register.

**And every step is reviewable.** Your analysts review and approve at each stage. The AI accelerates the work; your experts validate the results. You get the speed of automation with the judgment of your best people.

The output is a complete compliance package: a gap analysis, a compliance matrix, and a risk register — ready for your audit committee, your board, or your regulator."

### [TRANSITION]

"Let me show you this in action. I have a live instance running against the Enhanced Prudential Standards — a real regulation — with a real control dataset."

---

## 3. Live Walkthrough — Five Key Screens

---

### Screen 1: Intelligent Data Ingestion

### [SHOW]

The Upload & Configure tab is displayed. The system has auto-detected the regulation file, the APQC process hierarchy, and the control inventory. The scope panel shows "71 obligations in 22 groups." A metrics bar displays estimated LLM calls and the active AI provider. A "Start Classification" button is prominent.

### [SAY]

"This is the starting point. Your team uploads the regulation — in this case, the Enhanced Prudential Standards from 12 CFR Part 252 — along with your institution's APQC process hierarchy and your existing control inventory.

The system automatically parses everything: 71 individual regulatory obligations, organized into 22 logical sections. It also gives your team flexible scoping — they can analyze the entire regulation, focus on specific subparts like stress testing or liquidity, or run a quick sample to validate results before committing to a full run.

Notice the metrics bar — it estimates the workload upfront, so your team knows the scope before they start. One click, and the AI begins its analysis."

### [IMPACT]

**What used to take 2–3 weeks of analyst setup time is reduced to a single click with full visibility into scope and workload.**

---

### Screen 2: Interactive Data Source Explorer

### [SHOW]

The Data Source Explorer tab is displayed, showing three browsable data tables. The Regulations table is expanded — showing obligation citations, summaries, status badges (green "In Force"), and subpart filters. The APQC Hierarchy table shows indented process names forming a visual tree. The Controls table shows control IDs, activity descriptions, and color-coded badges for Control Type (blue "Preventive") and Rating (green "Effective"). Each table has a search bar, filter dropdowns, and pagination.

### [SAY]

"Before we run the analysis, I want to show you something your team will use every day — the Data Source Explorer. This is a searchable, filterable view of all three datasets that feed the engine.

Your regulation — every obligation, with status, subpart, and applicability — is fully browsable. Your team can search by citation or keyword to find any obligation instantly. Your APQC process hierarchy is rendered as an indented tree — drill into any process family like risk management or financial resources. And your entire control inventory — thousands of controls — is searchable by ID, activity description, business unit, or control type.

This isn't just a preview — it's a working reference. During review, when an analyst questions a mapping or a gap, they can flip to this tab and inspect the source data without leaving the platform. Every table supports filtering, toggling additional columns, and pagination. It's the transparency layer that keeps your team connected to the underlying data."

### [IMPACT]

**Full data transparency — your team always knows exactly what data the AI is working with, searchable and filterable in seconds.**

---

### Screen 3: AI-Powered Classification with Human Review

### [SHOW]

The Classification Review tab is shown. A stacked bar chart shows the distribution: ~45% Controls, ~25% Documentation, ~15% Attestation, ~10% General Awareness, ~5% Not Assigned. The master-detail panel shows obligation cards on the left and a detailed view on the right with full regulatory text, classification category, relationship type, criticality tier, and an expandable AI rationale. An "Approve and Continue" button sits at the bottom.

### [SAY]

"Here's where the first phase of AI analysis is complete. Every obligation has been classified using a recognized regulatory methodology — the same Promontory framework your existing RCM processes likely follow.

The distribution chart at the top gives your team an instant quality read. If the proportions look right — majority Controls, reasonable share of Documentation — the AI is interpreting the regulation correctly.

But we don't ask your team to trust the AI blindly. Click any obligation, and you see the full regulatory text, the classification the AI assigned, and — critically — the rationale. The AI explains *why* it categorized an obligation as a Control with High criticality. Your subject matter expert reads that rationale, agrees or disagrees, and can correct it right here.

Your team can also export everything to Excel, review offline, make corrections, and re-upload. Only when they explicitly approve does the analysis proceed.

This is the pattern throughout the platform: AI proposes, humans validate, the pipeline advances."

### [IMPACT]

**Classification that typically requires 3–5 days of SME review is completed in minutes, with full rationale documentation that eliminates the 'two analysts, two answers' problem.**

---

### 📋 REFERENCE — Classification Deep Dive (If They Ask)

> Use this section to answer executive follow-up questions about classification methodology. You do NOT present this proactively — only when asked.

#### "What are the classification categories and why these five?"

The platform uses the **Promontory / IBM Regulatory Change Management (RCM) methodology** — an industry-recognized framework used by major financial institutions. Every regulatory obligation is classified into one of five categories:

| Category | What It Means | Why It Matters |
|----------|--------------|----------------|
| **Controls** | The regulation requires evidence of operating processes, controls, systems, or monitoring — it prescribes *how* something must be done | These drive the bulk of your control inventory — they need active controls to demonstrate compliance |
| **Documentation** | Requires maintenance of written policies, procedures, plans, or records | These need artifact management — controlled documents that are current and retrievable |
| **Attestation** | Requires senior management sign-off, certification, or board approval | These carry governance weight — when leadership formally certifies, personal accountability attaches |
| **General Awareness** | Principle-based, definitional, or provides general authority with no explicit actionable requirement | These don't drive controls but inform the context. Important for training and awareness programs |
| **Not Assigned** | General requirement not directly actionable or too ambiguous to categorize | These get flagged for human review — the AI is explicitly saying "I'm not confident enough to classify this" |

Only the first three categories — Controls, Documentation, Attestation — are **actionable**, meaning they proceed to APQC mapping and coverage assessment. General Awareness and Not Assigned are tracked but don't generate gap findings.

#### "What are the relationship types?"

Every actionable obligation is also tagged with a **relationship type** that describes *what kind of requirement* the regulation imposes:

| Relationship Type | What It Means | Example From Enhanced Prudential Standards |
|-------------------|--------------|----------------------------------------------|
| **Requires Existence** | A function, committee, role, or process must exist | "Must establish a Risk Management Committee" |
| **Constrains Execution** | Specific requirements on *how* a process is performed | "Board must approve risk tolerance levels at least annually" |
| **Requires Evidence** | Documentation, reports, or records must be produced | "Must maintain records of stress test results" |
| **Sets Frequency** | Specifies how often an activity must be performed | "At least quarterly", "Annually" |
| **N/A** | No specific relationship (only for General Awareness / Not Assigned) | General principle statements |

These relationship types matter because they directly inform the coverage assessment — when the AI later checks whether a control covers an obligation, it checks whether the control satisfies the *specific kind of requirement*, not just the topic.

#### "What are the criticality tiers?"

Each obligation is also assigned a **criticality tier** based on regulatory enforcement implications of non-compliance:

| Tier | Impact of Violation | Practical Meaning |
|------|--------------------|--------------------|
| **High** | Triggers enforcement action, consent order, or MRA (Matter Requiring Attention) | These are your highest-priority items — violations have regulatory consequences |
| **Medium** | Results in supervisory criticism or examination findings | Serious but below enforcement threshold — expect examiner comments |
| **Low** | Noted as observation or best-practice gap | Findings that won't trigger formal action but represent improvement opportunities |

#### "Why not just use keyword matching or rules-based classification?"

Regulatory text is nuanced. The same obligation can contain elements of multiple categories. For example, "The board must annually approve a written liquidity policy" requires Attestation (board approval), Documentation (written policy), AND Sets Frequency (annually). The AI reads the full context and assigns the primary classification with rationale — something a rules engine cannot do reliably because regulatory language doesn't follow templates.

---

### Screen 4: Process Mapping with Confidence Scoring

### [SHOW]

The Mapping Review tab shows the same master-detail layout. The metrics bar reads "71 Obligations Mapped, 145 Total Mappings, Avg Confidence 0.87." Clicking an obligation reveals mapping "chips" — each showing an APQC process name (e.g., "Manage enterprise risk framework"), a hierarchy ID (11.1.1), a relationship type, and a confidence score displayed in green (0.92), orange (0.71), or red (0.45) coloring.

### [SAY]

"Now each obligation has been mapped to your institution's business process framework — the APQC hierarchy. And this is where the platform's intelligence really shows.

Look at this obligation on liquidity stress testing. The AI has mapped it to three business processes: enterprise risk management, liquidity risk management, and stress testing operations. Each mapping comes with a confidence score — 0.92 for the risk framework mapping, meaning the AI is highly confident that alignment is correct.

The confidence scores are color-coded for instant scanning. Green means high confidence — your team can review quickly. Orange or red means the AI was less certain — those are the ones your experts should examine closely.

This many-to-many mapping — one obligation affecting multiple processes — is something manual processes struggle with. An analyst might catch the primary mapping but miss secondary impacts. The AI systematically evaluates every possible process alignment and reports its confidence."

### [IMPACT]

**Comprehensive process mapping that captures secondary and tertiary impacts — the kind of thoroughness that's practically impossible at scale with manual analysis.**

---

### 📋 REFERENCE — APQC Mapping Deep Dive (If They Ask)

> Use this section to answer executive follow-up questions about APQC mapping. Reference the image from Tab 4 showing "Manage financial risk → 0.94 → 11.1.5 · Sets Frequency" as a concrete example.

#### "What is APQC and why does it matter?"

**APQC** stands for the **American Productivity & Quality Center Process Classification Framework (PCF)** — it's the industry-standard taxonomy for organizing business processes across an enterprise. Think of it as a universal language for describing *what your organization does*.

Your institution's version of the APQC hierarchy is loaded into the platform as a structured dataset. The AI uses it to answer: "Which of our business processes does this regulatory obligation affect?"

#### "How does the hierarchy work? What do numbers like 11.1.5 mean?"

The APQC hierarchy is structured in three levels, from broad to specific:

| Level | Format | Example | What It Represents |
|-------|--------|---------|-------------------|
| **Tier 1** | `X` | `11` | Enterprise-level category (e.g., "Manage Enterprise Risk") |
| **Tier 2** | `X.Y` | `11.1` | Major subprocess (e.g., "Manage Financial Risk") |
| **Tier 3** | `X.Y.Z` | `11.1.5` | Detailed process (e.g., "Manage Stress Testing") |

The platform maps to **Tier 3 by default** — the most specific level — because that's where your controls live. A mapping to "11 – Manage Enterprise Risk" is too vague to be actionable; a mapping to "11.1.5 – Manage Stress Testing" tells you *exactly* which process team owns the compliance obligation.

The system can return **up to 5 mappings per obligation** because in practice, one regulatory requirement often affects multiple business processes. For example, a stress testing requirement might map to:
- `11.1.5` — Manage Stress Testing (primary)
- `11.1.1` — Establish enterprise risk framework and policies (secondary — because it sets governance for stress testing)
- `9.5.1` — Manage capital structure (tertiary — because stress test results inform capital decisions)

#### "What does the confidence score mean? How is 0.94 calculated?"

The confidence score is a **0.0 to 1.0 value** that represents how certain the AI is that a given mapping is correct. It is *not* a keyword match score — it's the model's self-assessed certainty based on semantic understanding of both the obligation text and the APQC process description.

The scores are **color-coded** in the UI for instant scanning:

| Score Range | Color | What It Means for Your Reviewer |
|-------------|-------|---------------------------------|
| **≥ 0.80** | 🟢 Green | High confidence — quick review, likely correct |
| **0.50 – 0.79** | 🟠 Orange | Medium confidence — merits closer analyst inspection |
| **< 0.50** | 🔴 Red | Low confidence — AI is flagging uncertainty, analyst should validate carefully |

In the example from the image: **0.94** (green) means the AI is highly confident that the stress testing obligation maps to "Manage financial risk." Your reviewer can quickly confirm and move on.

This triage by confidence is powerful: instead of reviewing all 145 mappings equally, your analysts can focus their time on the orange and red ones — the 10–20% where human judgment adds the most value.

#### "Walk me through the example in the image"

The image shows a single APQC mapping card:

| Field | Value | What It Means |
|-------|-------|---------------|
| **APQC Process** | Manage financial risk | The business process this obligation affects — from your institution's APQC hierarchy |
| **Confidence** | 0.94 (green) | AI is 94% confident this mapping is correct |
| **Hierarchy ID** | 11.1.5 | Tier 3 process identifier — under "11 – Manage Enterprise Risk" → "11.1 – Manage Financial Risk" → "11.1.5" |
| **Relationship Type** | Sets Frequency | This obligation specifies *how often* an activity must be performed |
| **Description** | "Requires stress tests to be conducted annually using financial data as of September 30..." | The AI's specific description of *what the regulation requires OF that process* |

So the full read is: *"This regulatory obligation sets a frequency requirement — annual stress testing using year-end financial data — that applies to your financial risk management process (APQC 11.1.5), and we're 94% confident this mapping is correct."*

#### "What if the AI maps to the wrong process?"

That's exactly what the human review gate is for. Your analyst sees every mapping, examines the rationale, and can correct or reject any mapping before the pipeline proceeds. The AI also explicitly shows lower confidence when it's uncertain — those are the mappings your experts prioritize for review. Nothing proceeds to coverage assessment without analyst approval.

---

### Screen 5: Executive Dashboard — Gaps and Risks

### [SHOW]

The Results Dashboard is displayed. Four large metric cards read: 71 Assessed, 42 Covered (59%), 29 Gaps (41%), 18 Risks. A stacked coverage bar shows green/orange/red segments. On the left, a 4×4 risk heatmap shows clustered risks in the Medium-to-High range. On the right, the Top 8 Gaps are listed with obligation citations and coverage statuses. Below, expandable sections show the full Gap Analysis and Risk Register.

### [SAY]

"This is the view your Chief Risk Officer and Board committee are waiting for.

Four numbers tell the story: 71 obligations analyzed, 42 fully covered by existing controls, 29 gaps identified, and 18 distinct risks scored. The stacked bar makes the coverage ratio immediately visual — 59% green, 41% requiring attention.

The risk heatmap on the left uses a standard 4-by-4 matrix — the same framework your risk team already operates with. What's powerful here is that the impact and frequency scores aren't generic. They're calibrated to your institution's own risk appetite definitions — what 'Severe' means in terms of your pre-tax income, what 'Likely' means in terms of your frequency of occurrence.

The Top Gaps panel prioritizes where your team should focus first. Obligations with no matching controls at all surface at the top. Each gap traces back to the specific obligation, the business process it affects, and the control that was evaluated and found insufficient.

And everything you see here exports to a comprehensive Excel report — six sheets covering every dimension of the analysis. That's the artifact your compliance team presents to your regulators."

### [IMPACT]

**A complete, audit-ready gap analysis and risk register — from raw regulation to board-ready report — produced in hours instead of weeks, with full traceability for every finding.**

---

### 📋 REFERENCE — Coverage Assessment & Risk Scoring Deep Dive (If They Ask)

> Use this section to answer executive follow-up questions about how coverage is determined and risks are scored.

#### "How does the system decide if an obligation is Covered, Partially Covered, or Not Covered?"

The coverage assessment uses a **three-layer analysis** — not just keyword matching. Each obligation-control pair is evaluated through three independent lenses:

| Layer | What It Checks | How It Works |
|-------|---------------|-------------|
| **Layer 1: Structural Match** | Does a control *exist* at the same APQC process node as the obligation? | Deterministic check — either a control is mapped to that business process or it isn't. This is the first filter. |
| **Layer 2: Semantic Match** | Does the control's description *substantively address* what the obligation requires? | AI reads both texts and rates: **Full** (directly addresses), **Partial** (related but incomplete), or **None** (unrelated). Includes written rationale. |
| **Layer 3: Relationship Type Match** | Does the control satisfy the *specific kind of requirement*? | AI checks whether the control satisfies the obligation's relationship type. Example: if the obligation "Sets Frequency" at quarterly, does the control actually operate quarterly? Rated: **Satisfied**, **Partial**, or **Not Satisfied**. |

The three layers combine into the overall coverage status:

| Coverage Status | Condition | What It Means |
|----------------|-----------|---------------|
| **Covered** ✅ | Semantic = Full AND Relationship = Satisfied | Your existing control fully addresses this obligation |
| **Partially Covered** 🟡 | Either Semantic = Partial OR Relationship = Partial | You have a control but it doesn't fully meet the requirement — remediation may be needed |
| **Not Covered** ❌ | Semantic = None OR Relationship = Not Satisfied OR no control exists | Gap — no existing control adequately addresses this obligation |

**Why three layers?** Because a control can match on topic (Layer 2) but still fail on specifics (Layer 3). For example, a control that "manages stress testing" matches semantically, but if the obligation requires *annual* testing and the control operates *quarterly*, the relationship type check catches the nuance. Conversely, a control might exist at the right APQC node (Layer 1) but have nothing to do with the specific obligation (Layer 2 fails). Each layer adds precision.

#### "What are the risk categories? Why these eight?"

The platform uses a **risk taxonomy with 8 top-level categories and 40+ subcategories** — aligned with standard enterprise risk management frameworks used by large financial institutions:

| Risk Category | Subcategories (examples) | Typical Regulatory Relevance |
|---------------|-------------------------|------------------------------|
| **Credit Risk** | Commercial Credit, Consumer Credit | Lending standards, underwriting requirements |
| **Operational Risk** | Technology, InfoSec, Third Party, Process, Model, People, Business Continuity, Fraud | The broadest category — covers most operational requirements |
| **Market Risk** | Commodity, Counterparty, FX, Equity | Trading and market exposure requirements |
| **Compliance Risk** | Conduct, Regulatory Compliance, Financial Crimes | Direct regulatory compliance obligations |
| **Strategic Risk** | Capital Adequacy, New Business, Competitive, Business Model | Capital planning and strategic risk requirements |
| **Reputational Risk** | Media, Political, Social and Public | Public-facing obligations and disclosures |
| **Interest Rate Risk** | Balance Sheet Management, Basis, Repricing, Yield Curve | Rate sensitivity and ALM requirements |
| **Liquidity Risk** | Collateral, Deposit, Funding Gap, Market Liquidity, Contingency Funding | Liquidity coverage and funding requirements |

These categories are loaded from your institution's risk taxonomy file — they can be customized to match your existing risk framework exactly. The AI uses them to classify identified risks into the right bucket, ensuring the output aligns with how your risk team already thinks about risk.

#### "How are Impact and Frequency scored? What do the numbers mean?"

Risks are scored on two dimensions using a **4-point scale each**, calibrated to financial institution thresholds:

**Impact Scale:**

| Score | Label | Financial Impact | Operational Impact | Reputational Impact |
|-------|-------|------------------|--------------------|--------------------|
| **1** | Minor | <5% annual pre-tax income or <$1B outflow | Non-critical activity impact | Employee-level media coverage |
| **2** | Moderate | 5–25% annual pre-tax income or $1–3B outflow | <1 day critical activity disruption | Localized media coverage |
| **3** | Major | 1–2 quarters pre-tax income or $3–5B outflow | 1 day partial system failure | National / short-term media |
| **4** | Severe | ≥2 quarters pre-tax income or ≥$5B outflow | >1 day critical system failure | National media, cease and desist |

**Frequency Scale:**

| Score | Label | How Often |
|-------|-------|-----------|
| **1** | Remote | Once every 3+ years |
| **2** | Unlikely | Once every 1–3 years |
| **3** | Possible | Once per year |
| **4** | Likely | Once per quarter or more |

#### "How is the risk rating calculated?"

The **Inherent Risk Rating** = Impact × Frequency, mapped to four tiers:

| Score (Impact × Frequency) | Rating | Color on Heatmap |
|---------------------------|--------|-----------------|
| **≥ 12** | **Critical** | Dark Red |
| **8 – 11** | **High** | Red |
| **4 – 7** | **Medium** | Orange / Yellow |
| **1 – 3** | **Low** | Green |

For example, a risk with Impact = 3 (Major) and Frequency = 4 (Likely) scores 12 → **Critical**. A risk with Impact = 2 (Moderate) and Frequency = 2 (Unlikely) scores 4 → **Medium**.

The 4×4 heatmap on the dashboard visualizes this: each cell represents an Impact-Frequency combination, and risks are plotted into the appropriate cell. Clusters in the upper-right corner indicate your highest-priority gaps.

#### "These are inherent risk scores — what about residual risk?"

These are **inherent risk scores** — they represent the risk *before* considering any mitigating controls. For gaps (Not Covered), inherent = residual because there's no control mitigation. For Partially Covered items, the residual risk would be lower based on the partial control effectiveness. Your risk team uses these inherent scores as the starting point for their remediation prioritization — which is exactly how the output is designed to be used.

---

### Screen 6: Complete Audit Trail

### [SHOW]

The Traceability tab is shown (briefly — this is a curated view for executives). The Data Lineage section is expanded, showing a single obligation traced through all four stages: Classification → APQC Mapping → Coverage Assessment → Risk Score. Each step shows the relevant details and rationale.

### [SAY]

"And finally — the question every regulator will ask: 'How did you arrive at this conclusion?'

This is the audit trail. Pick any obligation in the system, and you can trace its complete journey — from the original regulatory text, through its classification and rationale, to the business process it was mapped against, to the coverage assessment that found it wasn't covered, to the risk that was identified and scored as a result.

Every step has documented reasoning. Every AI decision has an explanation. And every data point traces back to its source. This is the kind of defensible documentation that turns a regulatory conversation from reactive to proactive.

Your team isn't explaining a spreadsheet. They're presenting an evidence chain."

### [IMPACT]

**Regulatory-grade traceability that transforms audit responses from 'we believe this is covered' to 'here is the documented chain of evidence.'"**

---

### 📋 REFERENCE — Traceability & Methodology Deep Dive (If They Ask)

> Use this section to answer questions about the end-to-end evidence chain and the overall analytical methodology.

#### "Walk me through the complete chain for a single obligation"

Pick any obligation — say, §252.34(a)(1)(i) on annual stress testing. Here's the full chain the system builds:

| Stage | What Happens | Output |
|-------|-------------|--------|
| **1. Ingest** | Raw regulatory text is parsed and segmented into individual obligations | Citation: §252.34(a)(1)(i), Full text, Subpart context |
| **2. Classify** | AI reads the obligation and assigns category + relationship type + criticality | Category: **Controls**, Relationship: **Sets Frequency**, Criticality: **High**, Rationale: *"Obligation prescribes an operating frequency for stress testing — annual conduct using specific data as-of date"* |
| **3. Map to APQC** | AI identifies which business processes this obligation affects | Mapping 1: **11.1.5 – Manage Financial Risk** (confidence: 0.94, relationship: Sets Frequency), Mapping 2: **11.1.1 – Establish risk framework** (confidence: 0.82) |
| **4. Assess Coverage** | For each mapping, AI evaluates your controls | Structural: ✅ (control exists at node), Semantic: **Partial** (control addresses stress testing but doesn't specify annual frequency), Relationship: **Not Satisfied** (control operates quarterly, obligation requires annual with Sept 30 data), Result: **Partially Covered** |
| **5. Score Risk** | For gaps/partial coverage, AI identifies and scores the risk | Risk: **Model Risk** (under Operational Risk), Impact: 3 (Major), Frequency: 3 (Possible), Inherent Rating: **High** (score: 9), Rationale: *"Inadequate stress test frequency could lead to underestimation of capital requirements during periods of rapid economic change"* |

Every field in every stage has a timestamp, the AI model version, and the analyst who approved it. That's the evidence chain your regulators see.

#### "What AI models are you using? Can we use our own?"

The platform is **model-agnostic** — it's designed to work with any large language model. The current configuration supports multiple providers and can be switched in the configuration file without code changes. Your institution can use your internally approved AI provider. The AI is used for judgment calls (classification, mapping, assessment); the scoring formulas and thresholds are deterministic and configurable.

#### "What if the AI makes a mistake?"

Three safeguards:
1. **Human review gates** — Every stage requires explicit analyst approval before proceeding. Nothing is final until a human says so.
2. **Confidence transparency** — The AI explicitly reports its confidence. Low-confidence results are flagged visually for priority review.
3. **Validation-driven retries** — If the AI produces output that doesn't conform to the expected format or violates business rules, the system automatically retries with corrective feedback — before a human ever sees the result.

The platform is designed as an **accelerator**, not a replacement. Your SMEs remain the decision-makers; the AI handles the volume and consistency.

---

## 4. How It Works — One Slide

### [SAY]

"You don't need to understand the engineering to use ControlNexus — but here's the one-minute version of what's under the hood."

### [DEEP DIVE DIAGRAM — Simplified Architecture]

```html
<div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 32px; background: white; border-radius: 16px; max-width: 800px; margin: 0 auto; box-shadow: 0 2px 16px rgba(0,0,0,0.08);">
  <h3 style="text-align: center; color: #1a1a1a; margin-bottom: 28px; font-size: 22px;">How ControlNexus Works</h3>

  <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">

    <!-- Your Data -->
    <div style="background: #E3F2FD; border: 2px solid #1976D2; color: #0D47A1; padding: 14px 48px; border-radius: 12px; font-size: 16px; font-weight: 600; text-align: center; min-width: 380px;">
      📄 Your Data<br>
      <span style="font-size: 13px; font-weight: 400;">Regulations · Process Taxonomy · Control Inventory</span>
    </div>

    <div style="font-size: 24px; color: #1976D2;">↓</div>

    <!-- Platform -->
    <div style="background: linear-gradient(135deg, #1976D2, #1565C0); color: white; padding: 20px 48px; border-radius: 14px; font-size: 16px; text-align: center; min-width: 380px; box-shadow: 0 4px 12px rgba(25,118,210,0.3);">
      <div style="font-size: 18px; font-weight: 700; margin-bottom: 8px;">ControlNexus Platform</div>
      <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; margin-top: 8px;">
        <div style="background: rgba(255,255,255,0.2); padding: 6px 14px; border-radius: 8px; font-size: 13px;">Classify</div>
        <div style="font-size: 16px; line-height: 28px;">→</div>
        <div style="background: rgba(255,255,255,0.2); padding: 6px 14px; border-radius: 8px; font-size: 13px;">Map</div>
        <div style="font-size: 16px; line-height: 28px;">→</div>
        <div style="background: rgba(255,255,255,0.2); padding: 6px 14px; border-radius: 8px; font-size: 13px;">Assess</div>
        <div style="font-size: 16px; line-height: 28px;">→</div>
        <div style="background: rgba(255,255,255,0.2); padding: 6px 14px; border-radius: 8px; font-size: 13px;">Score</div>
      </div>
      <div style="margin-top: 10px; font-size: 12px; opacity: 0.9;">AI-powered analysis with human review gates at every stage</div>
    </div>

    <!-- Human review callout -->
    <div style="display: flex; align-items: center; gap: 8px;">
      <div style="width: 60px; height: 2px; background: #E65100;"></div>
      <div style="background: #FFF3E0; color: #E65100; padding: 6px 18px; border-radius: 20px; font-size: 13px; font-weight: 600; border: 1px solid #E65100;">
        🧑 Your experts review & approve at each stage
      </div>
      <div style="width: 60px; height: 2px; background: #E65100;"></div>
    </div>

    <div style="font-size: 24px; color: #1976D2;">↓</div>

    <!-- Results -->
    <div style="display: flex; gap: 14px; justify-content: center; flex-wrap: wrap;">
      <div style="background: #E8F5E9; border: 2px solid #388E3C; color: #1B5E20; padding: 12px 20px; border-radius: 10px; font-size: 14px; text-align: center; min-width: 150px;">
        <div style="font-size: 22px; margin-bottom: 4px;">📊</div>
        <strong>Gap Analysis</strong><br>
        <span style="font-size: 12px;">Coverage status for<br>every obligation</span>
      </div>
      <div style="background: #FFF3E0; border: 2px solid #E65100; color: #BF360C; padding: 12px 20px; border-radius: 10px; font-size: 14px; text-align: center; min-width: 150px;">
        <div style="font-size: 22px; margin-bottom: 4px;">⚠️</div>
        <strong>Risk Register</strong><br>
        <span style="font-size: 12px;">Scored risks with<br>impact & frequency</span>
      </div>
      <div style="background: #E3F2FD; border: 2px solid #1976D2; color: #0D47A1; padding: 12px 20px; border-radius: 10px; font-size: 14px; text-align: center; min-width: 150px;">
        <div style="font-size: 22px; margin-bottom: 4px;">🔗</div>
        <strong>Audit Trail</strong><br>
        <span style="font-size: 12px;">Full reasoning chain<br>for every decision</span>
      </div>
    </div>

  </div>
</div>
```

### [SAY]

"Your data goes in — regulations, your process taxonomy, your control inventory. The platform runs four stages of analysis — classify, map, assess, and score — with your experts reviewing and approving at each stage. Out the other end comes a gap analysis, a scored risk register, and a complete audit trail. No black boxes. No spreadsheet gymnastics. Just structured, traceable, defensible compliance intelligence."

---

## 5. Why ControlNexus — Next Steps

### [SAY]

"Let me leave you with three reasons this matters for your institution:

**Speed.** A regulation that takes your team weeks to analyze — ControlNexus processes it in hours. That's not just efficiency — it's the ability to respond to regulatory changes while they're still relevant, not months after the fact.

**Consistency.** Every obligation is analyzed using the same methodology, against the same taxonomy, with the same scoring framework. The output doesn't depend on which analyst happened to be available. Your compliance posture becomes standardized and repeatable.

**Defensibility.** When a regulator asks how you determined coverage, you don't point to a spreadsheet — you point to a documented chain of evidence: the regulatory text, the classification rationale, the process mapping with confidence scores, the coverage assessment with three layers of analysis, and the risk score with impact and frequency justification. Every decision is traceable, explainable, and auditable.

Here's what I'd propose as a next step: a focused pilot. We take one regulation that's currently on your team's backlog — something they haven't gotten to yet or something that's due for a refresh. We run it through ControlNexus, side-by-side with your existing process, and compare the results: coverage, accuracy, time to completion, and traceability depth.

That pilot gives your team a concrete, apples-to-apples comparison — and gives you the data to make a decision.

I'd love to set that up. Who on your team would be the right person to coordinate the pilot regulation and control dataset?"

---

*End of Executive Presentation Script*
