# ControlNexus — Checkpoint Patch Plan: Add Missing APQC Section Controls & Re-Assess

> **Purpose:** Standalone implementation brief for an AI agent or developer to execute without additional context.  
> **Scope:** Create `scripts/patch_checkpoint.py` — a CLI tool that patches a Full Assessment checkpoint with new controls and re-runs only the affected coverage assessments and risk scoring via the existing LLM agents.

---

## 1. The Problem

The ControlNexus pipeline runs a 5-stage analysis:
**Ingest → Classify → Map to APQC → Assess Coverage → Score Risks**

The current Full Assessment checkpoint file:
```
data/checkpoints/Full_Assessment_Enhanced_Prudential_Standards__71obs_llm_2026-04-13_15h22_57.json
```

Contains **81 coverage assessments** across 71 obligations. Approximately **47 assessments** are mapped to APQC section 11 hierarchy nodes (e.g., `11.1.1`, `11.1.5`, `11.2.1`). These all show **"Not Covered"** because:

- Control Excel files exist for sections 1–10: `data/Control Dataset/section_1__controls.xlsx` through `section_10__controls.xlsx`
- **No control files exist for sections 11 or 12**
- When no controls exist at an APQC node, `find_controls_for_apqc()` returns an empty list, and `CoverageAssessorAgent.execute()` deterministically returns "Not Covered"

The full pipeline takes multiple hours to run end-to-end. We need a way to **patch the checkpoint** with new section 11 controls and re-assess only the ~47 affected obligations, without re-running the entire pipeline.

---

## 2. Solution: `scripts/patch_checkpoint.py`

A standalone CLI script that:
1. Loads an existing Full Assessment checkpoint JSON
2. Loads a JSON file containing new `ControlRecord` entries (generated externally)
3. Merges the new controls into the checkpoint
4. Identifies affected assessments (those mapped to APQC hierarchy IDs prefixed by the new controls' hierarchy IDs)
5. Re-runs `CoverageAssessorAgent.execute()` for each affected assessment via the real LLM
6. Re-runs `RiskExtractorAndScorerAgent.execute()` for any remaining gaps
7. Rebuilds `gap_report`, `compliance_matrix`, `risk_register`
8. Saves a new patched checkpoint file alongside the original

---

## 3. Checkpoint JSON Structure

The checkpoint is a single JSON file with this top-level structure:

```json
{
  "_meta": {
    "stage": "assessed",
    "stage_label": "Full Assessment",
    "regulation_name": "Enhanced Prudential Standards (Regulation YY) (12 CFR Part 252)",
    "timestamp": "2026-04-13 15:22:57 UTC",
    "llm_mode": "LLM-assisted",
    "obligation_count": 71,
    "mapping_count": 125,
    "assessment_count": 81,
    "category_breakdown": {"Controls": 32, "Documentation": 17, "Attestation": 14, "...": "..."},
    "criticality_breakdown": {"High": 28, "Medium": 35, "Low": 8},
    "keys_saved": ["classified_obligations", "obligation_groups", "apqc_nodes", "controls", "..."]
  },
  "classified_obligations": [ "... 71 items — obligation metadata ..." ],
  "obligation_groups": [ "..." ],
  "apqc_nodes": [ "..." ],
  "controls": [ "... existing controls (sections 1-10) ..." ],
  "regulation_name": "...",
  "pipeline_config": { "... includes impact_scale, frequency_scale, risk_id_prefix ..." },
  "risk_taxonomy": { "... 8 categories with sub_risks ..." },
  "llm_enabled": true,
  "obligation_mappings": [ "... 125+ mappings (citation → APQC hierarchy ID) ..." ],
  "coverage_assessments": [ "... 81 assessments ..." ],
  "scored_risks": [ "... 191 scored risks ..." ],
  "gap_report": { "..." },
  "compliance_matrix": { "..." },
  "risk_register": { "..." }
}
```

### Key Data Schemas

**`ControlRecord` (15 fields)** — used in `controls` array:
```json
{
  "control_id": "CTRL-11-001",
  "hierarchy_id": "11.1.1",
  "leaf_name": "Establish enterprise risk framework and policies",
  "full_description": "...",
  "selected_level_1": "Preventive",
  "selected_level_2": "Policy Control",
  "who": "Chief Risk Officer",
  "what": "Establish and maintain enterprise-wide risk management framework...",
  "when": "Annually and upon significant regulatory changes",
  "frequency": "Annual",
  "where": "Enterprise-wide",
  "why": "To ensure comprehensive risk identification and mitigation...",
  "evidence": "Board-approved risk management policy, risk appetite statement...",
  "quality_rating": "Effective",
  "business_unit_name": "Enterprise Risk Management"
}
```

**`CoverageAssessment` (9 fields)** — used in `coverage_assessments` array:
```json
{
  "citation": "§252.33(a)(1)",
  "apqc_hierarchy_id": "11.1.5",
  "control_id": "CTRL-11-003",
  "structural_match": true,
  "semantic_match": "Full",
  "semantic_rationale": "The control directly addresses...",
  "relationship_match": "Satisfied",
  "relationship_rationale": "The control operates at the required frequency...",
  "overall_coverage": "Covered"
}
```

**`ScoredRisk` (12 fields)** — used in `scored_risks` array:
```json
{
  "risk_id": "RISK-001",
  "source_citation": "§252.33(a)(1)",
  "source_apqc_id": "11.1.5",
  "risk_description": "...",
  "risk_category": "Compliance Risk",
  "sub_risk_category": "Regulatory Compliance Risk",
  "impact_rating": 3,
  "impact_rationale": "...",
  "frequency_rating": 2,
  "frequency_rationale": "...",
  "inherent_risk_rating": "Medium",
  "coverage_status": "Not Covered"
}
```

---

## 4. Codebase Reference — Key Functions to Reuse

All paths are relative to the repository root.

### 4.1 Control Loading (`src/regrisk/ingest/control_loader.py`)

```python
def build_control_index(controls: list[ControlRecord]) -> dict[str, list[ControlRecord]]:
    """Index controls by hierarchy_id. Returns dict[hierarchy_id → list[ControlRecord]]."""

def find_controls_for_apqc(control_index, apqc_hierarchy_id: str) -> list[ControlRecord]:
    """Prefix match: returns controls whose hierarchy_id == apqc_hierarchy_id
    or starts with apqc_hierarchy_id + '.'. Used for structural matching."""
```

### 4.2 Coverage Assessment (`src/regrisk/agents/coverage_assessor.py`)

```python
class CoverageAssessorAgent(BaseAgent):
    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Required kwargs:
          - obligation: dict  (must have 'citation', 'abstract', 'obligation_category',
                               'relationship_type', 'criticality_tier')
          - control: dict | None  (ControlRecord as dict, or None for no-control case)
          - apqc_hierarchy_id: str
          - apqc_process_name: str

        Returns dict with keys:
          citation, apqc_hierarchy_id, control_id, structural_match,
          semantic_match, semantic_rationale, relationship_match,
          relationship_rationale, overall_coverage
        """
```

**Candidate selection logic** (from `assess_coverage_node` in `src/regrisk/graphs/assess_graph.py`):
- If no candidates → call with `control=None` → deterministic "Not Covered"
- If candidates exist → evaluate each, keep best:
  - If any returns "Covered" → use that (break early)
  - If any returns "Partially Covered" and current best is "Not Covered" → upgrade
  - Otherwise keep first result

### 4.3 Risk Scoring (`src/regrisk/agents/risk_extractor_scorer.py`)

```python
class RiskExtractorAndScorerAgent(BaseAgent):
    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Required kwargs:
          - obligation: dict  (citation, abstract, criticality_tier)
          - coverage_status: str  ("Not Covered" or "Partially Covered")
          - gap_rationale: str  (the semantic_rationale from the assessment)
          - apqc_hierarchy_id: str
          - apqc_process_name: str
          - risk_taxonomy: dict  (loaded from checkpoint's risk_taxonomy key)
          - config: dict  (loaded from checkpoint's pipeline_config key —
                          must contain impact_scale, frequency_scale, risk_id_prefix)
          - risk_counter: int  (for sequential risk IDs: RISK-001, RISK-002...)

        Returns dict with key "risks": list of scored risk dicts.
        """
```

### 4.4 Finalization Logic (`src/regrisk/graphs/assess_graph.py`, `finalize_node()`)

The `finalize_node()` function rebuilds three outputs from the raw data:

**gap_report:**
```python
gap_report = {
    "regulation_name": state["regulation_name"],
    "total_obligations": len(approved),
    "classified_counts": {category: count, ...},
    "mapped_obligation_count": len(set(m["citation"] for m in mappings)),
    "coverage_summary": {status: count, ...},  # e.g. {"Covered": 42, "Not Covered": 20, ...}
    "gaps": [assessments where overall_coverage in ("Not Covered", "Partially Covered")],
}
```

**compliance_matrix:**
```python
compliance_matrix = {"rows": [
    {
        "citation": cit,
        "obligation_category": ob["obligation_category"],
        "criticality_tier": ob["criticality_tier"],
        "apqc_hierarchy_id": apqc_id,
        "apqc_process_name": m["apqc_process_name"],
        "control_id": assessment.get("control_id", ""),
        "overall_coverage": assessment.get("overall_coverage", ""),
        "risk_ids": [r["risk_id"] for r in risks_for_this_citation],
    }
    for each obligation × mapping pair
]}
```

**risk_register:**
```python
risk_register = {
    "scored_risks": risks,
    "total_risks": len(risks),
    "risk_distribution": {category: count, ...},
    "critical_count": N,
    "high_count": N,
}
```

### 4.5 Agent Initialization Pattern (`src/regrisk/graphs/graph_infra.py`)

```python
from regrisk.agents.base import AgentContext
from regrisk.core.transport import build_client_from_env

# Create LLM client from env vars (OPENAI_API_KEY or ICA_API_KEY + ICA_BASE_URL)
client = build_client_from_env()

# Build context
context = AgentContext(client=client, model=client.model, max_tokens=2048)

# Instantiate agents
assessor = CoverageAssessorAgent(context)
risk_scorer = RiskExtractorAndScorerAgent(AgentContext(client=client, model=client.model, max_tokens=4096))

# Call (async)
import asyncio
loop = asyncio.new_event_loop()
result = loop.run_until_complete(assessor.execute(
    obligation=ob_dict,
    control=ctrl_dict,
    apqc_hierarchy_id="11.1.5",
    apqc_process_name="Manage Stress Testing",
))
```

### 4.6 Checkpoint Save/Load (`src/regrisk/ui/checkpoint.py`)

```python
from regrisk.ui.checkpoint import load_checkpoint, save_checkpoint, STAGE_ASSESSED

data = load_checkpoint("data/checkpoints/Full_Assessment_*.json")
# data["_meta"] has metadata
# data["coverage_assessments"], data["scored_risks"], etc.

# To save:
save_checkpoint(STAGE_ASSESSED, session_data_dict, directory=Path("data/checkpoints"))
# Generates filename like: Full_Assessment_{reg_name}_{Nobs}_{mode}_{timestamp}.json
```

---

## 5. Implementation Steps

### Step 1: Create `scripts/patch_checkpoint.py`

**CLI interface:**
```
python scripts/patch_checkpoint.py \
  --checkpoint data/checkpoints/Full_Assessment_Enhanced_Prudential_Standards__71obs_llm_2026-04-13_15h22_57.json \
  --controls data/Control\ Dataset/section_11_controls.json
```

**Arguments:**
- `--checkpoint` (required): Path to existing Full Assessment checkpoint JSON
- `--controls` (required): Path to JSON file containing an array of new ControlRecord dicts (15 fields each)

### Step 2: Load and Validate Inputs

```python
import json
from pathlib import Path
from regrisk.core.models import ControlRecord

# Load checkpoint
checkpoint = json.loads(Path(args.checkpoint).read_text())
meta = checkpoint["_meta"]
assert meta["stage"] == "assessed", "Checkpoint must be a Full Assessment"

# Load new controls and validate schema
new_controls_raw = json.loads(Path(args.controls).read_text())
REQUIRED_FIELDS = [
    "control_id", "hierarchy_id", "leaf_name", "full_description",
    "selected_level_1", "selected_level_2", "who", "what", "when",
    "frequency", "where", "why", "evidence", "quality_rating", "business_unit_name"
]
for c in new_controls_raw:
    missing = [f for f in REQUIRED_FIELDS if f not in c]
    if missing:
        raise ValueError(f"Control {c.get('control_id', '?')} missing fields: {missing}")
    # Verify it can construct a ControlRecord
    ControlRecord(**c)
```

### Step 3: Merge Controls

```python
# Existing controls from checkpoint
existing_controls = checkpoint.get("controls", [])
existing_ids = {c["control_id"] for c in existing_controls}

# Deduplicate and merge
added = 0
for c in new_controls_raw:
    if c["control_id"] not in existing_ids:
        existing_controls.append(c)
        existing_ids.add(c["control_id"])
        added += 1

print(f"Merged {added} new controls (total: {len(existing_controls)})")
checkpoint["controls"] = existing_controls
```

### Step 4: Identify Affected Assessments

```python
from regrisk.ingest.control_loader import build_control_index, find_controls_for_apqc

# Get unique hierarchy_id prefixes from new controls
new_prefixes = set()
for c in new_controls_raw:
    hid = c["hierarchy_id"]
    top = hid.split(".")[0]  # e.g., "11"
    new_prefixes.add(top)

# Build full control index from merged controls
all_control_records = [ControlRecord(**c) for c in existing_controls]
control_index = build_control_index(all_control_records)
# Convert to dict-of-dicts for find_controls_for_apqc
control_index_dicts = {
    hid: [c.model_dump() for c in ctrls]
    for hid, ctrls in control_index.items()
}

# Split assessments: affected vs preserved
old_assessments = checkpoint.get("coverage_assessments", [])
affected = []
preserved = []
for a in old_assessments:
    apqc_id = a.get("apqc_hierarchy_id", "")
    top = apqc_id.split(".")[0]
    if top in new_prefixes:
        affected.append(a)
    else:
        preserved.append(a)

print(f"Affected assessments: {len(affected)}, Preserved: {len(preserved)}")

# Split risks similarly
old_risks = checkpoint.get("scored_risks", [])
affected_citations = {a["citation"] for a in affected}
# Note: risks are keyed by source_citation, not APQC. Remove risks for affected citations.
preserved_risks = [r for r in old_risks if r["source_citation"] not in affected_citations]
```

### Step 5: Re-run Coverage Assessment for Affected Items

```python
import asyncio
from regrisk.agents.coverage_assessor import CoverageAssessorAgent
from regrisk.agents.base import AgentContext
from regrisk.core.transport import build_client_from_env

# Initialize LLM client and agent
client = build_client_from_env()
context = AgentContext(client=client, model=client.model, max_tokens=2048)
assessor = CoverageAssessorAgent(context)
loop = asyncio.new_event_loop()

# Build obligation lookup from classified_obligations
ob_lookup = {}
for ob in checkpoint.get("classified_obligations", []):
    ob_lookup[ob["citation"]] = ob

# Build mapping lookup
mapping_lookup = {}
for m in checkpoint.get("obligation_mappings", []):
    key = (m["citation"], m["apqc_hierarchy_id"])
    mapping_lookup[key] = m

# Re-assess each affected item
new_assessments = []
for i, old_a in enumerate(affected):
    cit = old_a["citation"]
    apqc_id = old_a["apqc_hierarchy_id"]
    mapping = mapping_lookup.get((cit, apqc_id), {})
    obligation = ob_lookup.get(cit, {"citation": cit})

    # Find candidate controls (now including section 11 controls)
    candidates = find_controls_for_apqc(control_index_dicts, apqc_id)

    if not candidates:
        # Still no controls → deterministic Not Covered
        result = loop.run_until_complete(assessor.execute(
            obligation=obligation,
            control=None,
            apqc_hierarchy_id=apqc_id,
            apqc_process_name=mapping.get("apqc_process_name", ""),
        ))
    else:
        # Evaluate candidates, keep best (same logic as assess_coverage_node)
        best = None
        for ctrl in candidates:
            result = loop.run_until_complete(assessor.execute(
                obligation=obligation,
                control=ctrl,
                apqc_hierarchy_id=apqc_id,
                apqc_process_name=mapping.get("apqc_process_name", ""),
            ))
            if best is None:
                best = result
            elif result.get("overall_coverage") == "Covered":
                best = result
                break
            elif (result.get("overall_coverage") == "Partially Covered"
                  and best.get("overall_coverage") == "Not Covered"):
                best = result
        result = best

    new_assessments.append(result)
    status = result.get("overall_coverage", "?")
    print(f"  [{i+1}/{len(affected)}] {cit} @ {apqc_id} → {status}")
```

### Step 6: Re-run Risk Scoring for Remaining Gaps

```python
from regrisk.agents.risk_extractor_scorer import RiskExtractorAndScorerAgent

risk_context = AgentContext(client=client, model=client.model, max_tokens=4096)
risk_scorer = RiskExtractorAndScorerAgent(risk_context)

# Find remaining gaps in new assessments
new_gaps = [a for a in new_assessments
            if a.get("overall_coverage") in ("Not Covered", "Partially Covered")]

risk_counter = len(preserved_risks)  # continue sequential IDs
new_risks = []

for i, gap in enumerate(new_gaps):
    cit = gap["citation"]
    obligation = ob_lookup.get(cit, {"citation": cit})
    mapping = mapping_lookup.get((cit, gap["apqc_hierarchy_id"]), {})

    result = loop.run_until_complete(risk_scorer.execute(
        obligation=obligation,
        coverage_status=gap.get("overall_coverage", "Not Covered"),
        gap_rationale=gap.get("semantic_rationale", ""),
        apqc_hierarchy_id=gap.get("apqc_hierarchy_id", ""),
        apqc_process_name=mapping.get("apqc_process_name", ""),
        risk_taxonomy=checkpoint.get("risk_taxonomy", {}),
        config=checkpoint.get("pipeline_config", {}),
        risk_counter=risk_counter,
    ))

    scored = result.get("risks", [])
    new_risks.extend(scored)
    risk_counter += len(scored)
    print(f"  [{i+1}/{len(new_gaps)}] {cit} → {len(scored)} risks")
```

### Step 7: Rebuild Final Outputs

```python
from collections import defaultdict, Counter

# Merge assessments and risks
all_assessments = preserved + new_assessments
all_risks = preserved_risks + new_risks
approved = checkpoint.get("classified_obligations", [])
mappings = checkpoint.get("obligation_mappings", [])

# Rebuild gap_report
coverage_summary = dict(Counter(a.get("overall_coverage", "Not Covered") for a in all_assessments))
gaps = [a for a in all_assessments if a.get("overall_coverage") in ("Not Covered", "Partially Covered")]
classified_counts = dict(Counter(ob.get("obligation_category", "Not Assigned") for ob in approved))

gap_report = {
    "regulation_name": checkpoint.get("regulation_name", ""),
    "total_obligations": len(approved),
    "classified_counts": classified_counts,
    "mapped_obligation_count": len(set(m.get("citation") for m in mappings)),
    "coverage_summary": coverage_summary,
    "gaps": gaps,
}

# Rebuild compliance_matrix
ob_lookup_full = {ob["citation"]: ob for ob in approved}
mapping_by_cit = defaultdict(list)
for m in mappings:
    mapping_by_cit[m["citation"]].append(m)
assessment_by_key = {(a["citation"], a["apqc_hierarchy_id"]): a for a in all_assessments}
risk_by_cit = defaultdict(list)
for r in all_risks:
    risk_by_cit[r["source_citation"]].append(r)

matrix_rows = []
for ob in approved:
    cit = ob["citation"]
    for m in mapping_by_cit.get(cit, [{}]):
        apqc_id = m.get("apqc_hierarchy_id", "")
        a = assessment_by_key.get((cit, apqc_id), {})
        matrix_rows.append({
            "citation": cit,
            "obligation_category": ob.get("obligation_category", ""),
            "criticality_tier": ob.get("criticality_tier", ""),
            "apqc_hierarchy_id": apqc_id,
            "apqc_process_name": m.get("apqc_process_name", ""),
            "control_id": a.get("control_id", ""),
            "overall_coverage": a.get("overall_coverage", ""),
            "risk_ids": [r["risk_id"] for r in risk_by_cit.get(cit, [])],
        })

compliance_matrix = {"rows": matrix_rows}

# Rebuild risk_register
risk_dist = dict(Counter(r.get("risk_category", "Unknown") for r in all_risks))
risk_register = {
    "scored_risks": all_risks,
    "total_risks": len(all_risks),
    "risk_distribution": risk_dist,
    "critical_count": sum(1 for r in all_risks if r.get("inherent_risk_rating") == "Critical"),
    "high_count": sum(1 for r in all_risks if r.get("inherent_risk_rating") == "High"),
}
```

### Step 8: Save Patched Checkpoint

```python
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
ts = now.strftime("%Y-%m-%d_%Hh%M_%S")

# Update checkpoint data
checkpoint["controls"] = existing_controls
checkpoint["coverage_assessments"] = all_assessments
checkpoint["scored_risks"] = all_risks
checkpoint["gap_report"] = gap_report
checkpoint["compliance_matrix"] = compliance_matrix
checkpoint["risk_register"] = risk_register

# Update metadata
checkpoint["_meta"]["patched"] = True
checkpoint["_meta"]["patch_timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
checkpoint["_meta"]["assessment_count"] = len(all_assessments)
checkpoint["_meta"]["original_file"] = Path(args.checkpoint).name

# Save
output_path = Path(args.checkpoint).parent / f"Patched_Full_Assessment_{ts}.json"
output_path.write_text(json.dumps(checkpoint, default=str, indent=2), encoding="utf-8")
print(f"\nPatched checkpoint saved: {output_path}")
print(f"  Assessments: {len(all_assessments)} ({len(new_assessments)} re-assessed)")
print(f"  Risks: {len(all_risks)} ({len(new_risks)} new)")
print(f"  Coverage: {coverage_summary}")
```

---

## 6. Generating the Section 11 Controls JSON

The new controls must be provided as a JSON file — an array of objects matching the 15-field `ControlRecord` schema. These should be generated by an LLM (ChatGPT, Claude, etc.) using a prompt like:

> You are a compliance control specialist at a large US bank. Generate a realistic set of internal controls mapped to APQC section 11 (Manage Enterprise Risk) processes. Each control must match this exact JSON schema:
>
> ```json
> {
>   "control_id": "CTRL-11-NNN",
>   "hierarchy_id": "11.X.Y",
>   "leaf_name": "...",
>   "full_description": "...",
>   "selected_level_1": "Preventive|Detective",
>   "selected_level_2": "...",
>   "who": "...",
>   "what": "...",
>   "when": "...",
>   "frequency": "...",
>   "where": "...",
>   "why": "...",
>   "evidence": "...",
>   "quality_rating": "Effective|Needs Improvement",
>   "business_unit_name": "..."
> }
> ```
>
> Cover these APQC hierarchy nodes (from the loaded APQC hierarchy):
> - 11.1.1 — Establish enterprise risk framework and policies
> - 11.1.2 — Manage credit risk
> - 11.1.3 — Manage liquidity risk
> - 11.1.4 — Manage market risk
> - 11.1.5 — Manage financial risk
> - 11.2.1 — Manage compliance risk
> - 11.2.2 — Manage regulatory compliance
> - 11.3.1 — Manage remediation
> - 11.3.2 — Manage business resiliency
>
> Generate 3–5 controls per APQC node. Return a JSON array only.

Save the output as `data/Control Dataset/section_11_controls.json`.

---

## 7. Usage After Patching

1. Run the patch script:
   ```bash
   python scripts/patch_checkpoint.py \
     --checkpoint "data/checkpoints/Full_Assessment_Enhanced_Prudential_Standards__71obs_llm_2026-04-13_15h22_57.json" \
     --controls "data/Control Dataset/section_11_controls.json"
   ```

2. Load the patched checkpoint in the UI:
   - Open the ControlNexus Streamlit app
   - Go to **Upload & Configure** tab
   - Click **Load Checkpoint** and select the `Patched_Full_Assessment_*.json` file
   - Navigate to **Results** tab — section 11 obligations should now show improved coverage

3. Expected outcome:
   - Total obligations: still 71
   - Total assessments: still 81
   - Coverage distribution: significantly improved (fewer "Not Covered" for section 11)
   - Risk count: likely reduced (some gaps now covered → fewer risks)
   - The APQC Section filter in the Results tab can be used to isolate section 11 results for verification

---

## 8. Environment Requirements

The script requires LLM access via environment variables:

**For OpenAI:**
```bash
export OPENAI_API_KEY="sk-..."
```

**For ICA (IBM Cloud AI):**
```bash
export ICA_API_KEY="..."
export ICA_BASE_URL="https://..."
```

The `build_client_from_env()` function in `src/regrisk/core/transport.py` auto-detects the provider from these env vars.

**Python dependencies:** All dependencies are already in `pyproject.toml`. The script uses only internal modules (`regrisk.*`).

---

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Non-destructive** — saves new file, never overwrites original | Safety; allows A/B comparison |
| **Full LLM re-assessment** (not deterministic) | Produces authentic rationale text for the demo |
| **Full risk re-scoring** for remaining gaps | Risks need to reflect new coverage reality |
| **Reusable** — not hardcoded to section 11 | Script auto-detects affected sections from new controls' hierarchy_ids |
| **Controls generated externally** | Keeps the script simple; user controls quality of synthetic data |
| **Sequential risk IDs** continuing from preserved risks | Avoids ID collisions in the merged risk register |
