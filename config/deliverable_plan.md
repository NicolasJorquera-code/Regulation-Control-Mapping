# Deliverable Plan — Architectural Proposal (Delta Against SWE Blueprint)

## 1. Reading Guide

This is not a standalone proposal. It is a delta layered on top of the SWE blueprint (`Control Builder Architecture — As-Is Reference & Pivot Blueprint`). Read the SWE blueprint first; come here for what to accept, what to push back on, and what is missing.

Structure:

- §2 — what the SWE got right (accept with minor tweaks)
- §3 — seven substantive pushbacks with specific remedies
- §4 — three gaps where the blueprint is silent
- §5 — concrete schema proposals consolidated
- §6 — evaluation strategy for domain-agnosticism
- §7 — sequencing guidance for the migration

---

## 2. What to Accept From the SWE Blueprint

The following decisions are well-reasoned and should stand:

- **The pivot direction: BU → Process → Risk → Control.** This matches the user's stated intent and is the natural inversion of the current section-first model.
- **The hybrid catalog + instance model** (`RiskCatalogEntry` + `RiskInstance`). Standard risk management practice distinguishes between the *taxonomy* of risks the institution recognizes and the *instantiation* of risks within a specific process context with per-context severity and mitigation. The SWE's model captures this cleanly.
- **Inserting a new `RiskAgent` node** between `select_node` and `spec_node`. Risk context is genuinely distinct from spec context; giving it its own node preserves the locked-field contract and keeps the graph topology legible.
- **Retiring `RiskProfileConfig` and `AffinityConfig`.** Per-risk severity and per-risk `mitigated_by_types` subsume both cleanly.
- **Preserving `ControlTypeConfig`, `PlacementConfig`, `MethodConfig`, `FrequencyTier`, `NarrativeConstraints`, `RegistryConfig`, `ExemplarConfig`, and the validator.** These have earned their place and are domain-neutral already.
- **The assignment matrix pseudocode** in §11.3 of the blueprint. The shape is correct — weight by `severity × multiplier`, distribute across `mitigated_by_types`, cycle BUs from `owner_bu_ids`.
- **The migration table** in §11.2. The "survives / transforms / retires" framing is honest and enables a stepwise migration.
- **The wizard redesign** in §11.7, including inserting a Risks step between Processes and Review.
- **The open questions in §13**, especially the `memory_retrieval` filter axis (which the blueprint proposes be `process_id`; I agree).

This is roughly 70% of the SWE's blueprint. It is good work.

---

## 3. Seven Substantive Pushbacks

### 3.1 `RiskCatalogEntry` is too flat

**Problem.** The blueprint defines `RiskCatalogEntry` with `category: str = ""`. This is a freeform string, not a reference. The CTB Risk Universe is genuinely two-tier with nine Level 1 categories and, for Operational specifically, nine sub-groups. A string `category` field cannot enforce that risks belong to the declared taxonomy, cannot support sub-groupings, and cannot be navigated for reporting or affinity queries.

**Remedy.** Extend `RiskCatalogEntry` to first-class two-tier:

```python
class RiskLevel1Category(BaseModel):
    name: str
    code: str  # 3-letter
    definition: str
    grounding: str | None = None
    sub_groups: list[str] = Field(default_factory=list)  # ordered list for UI/report grouping

class RiskCatalogEntry(BaseModel):
    id: str
    name: str
    level_1: str            # must match a RiskLevel1Category.name
    level_1_code: str       # denormalized for convenience, cross-validated
    sub_group: str | None = None  # must match one of the parent's sub_groups if set
    default_severity: int = Field(default=3, ge=1, le=5)
    description: str
    default_mitigating_types: list[str] = Field(default_factory=list)
    grounding: str | None = None
```

Add `risk_level_1_categories: list[RiskLevel1Category]` to `DomainConfig` alongside `risk_catalog`. Add a cross-reference validator: every `RiskCatalogEntry.level_1` must match a declared Level 1 category; every `sub_group` must match one of that category's declared sub-groups; every `default_mitigating_types[i]` must match a `ControlTypeConfig.name`.

My `risk_taxonomy.yaml` is already structured to this schema.

### 3.2 `mitigated_by_types` should carry weights, not just names

**Problem.** Both the blueprint's `RiskInstance.mitigated_by_types: list[str]` and the catalog's `default_mitigating_types: list[str]` are unweighted. When `build_assignment_matrix` distributes controls across mitigating types for a risk, it implicitly uses uniform weights. But different control types provide different degrees of mitigation for a given risk. For `CYB-001 Digital Fraud and Account Takeover`, `Automated Rules` is first-line and `Surveillance` is supporting — they should not be treated as equivalent.

**Remedy.** Replace `list[str]` with `list[MitigationLink]`:

```python
class MitigationLink(BaseModel):
    control_type: str       # ControlTypeConfig.name
    effectiveness: float = Field(default=1.0, ge=0.0, le=1.0)  # weight for allocation
    line_of_defense: int | None = Field(default=None, ge=1, le=3)  # optional 3LoD tag
```

`build_assignment_matrix` then distributes by `effectiveness × severity × multiplier` rather than by count.

My `risk_taxonomy.yaml` currently uses the simpler `list[str]` form because effectiveness is not extractable from the Risk Universe alone. Expect the ASI (or the user) to tune effectiveness values in a follow-on pass; a sensible default is `1.0` for the first type listed and `0.6` for subsequent ones, or uniform `1.0 / N`.

### 3.3 `severity` and `multiplier` are semantically overlapping

**Problem.** The blueprint keeps both `RiskInstance.severity` (1–5) and `RiskInstance.multiplier` (float) for backward-compat with `risk_profile.multiplier`. They end up multiplied together in the assignment matrix. This works but is confusing: two knobs control the same output dimension with no clear separation of concerns.

**Remedy.** Keep both, but document their distinct roles explicitly:

- `severity`: *inherent risk rating*, a 1–5 categorical expressing how bad this risk is if unmitigated. Drives reporting, heatmaps, and risk appetite conversations. Input from risk management stakeholders.
- `multiplier`: *allocation weight tuner*, a float expressing how much of the control budget should flow to this risk relative to others of the same severity. Defaults to `1.0`. Used to tilt generation without changing the risk rating. Input from the control generation operator.

Add a validator that warns (not errors) if `multiplier > 3.0` or `< 0.1` — these likely indicate the operator is using multiplier to express severity, which is a smell.

### 3.4 BU ↔ Process bidirectional reference is a normalization hazard

**Problem.** The blueprint has `BusinessUnitConfig.processes: list[str]` AND `ProcessConfig.owner_bu_ids: list[str]`. Both are writable fields in YAML. They can drift.

**Remedy.** Pick one as authoritative and derive the other. Recommendation: `ProcessConfig.owner_bu_ids` is authoritative (a process knows who owns it), and `BusinessUnitConfig.processes` is a computed property on the DomainConfig, not a YAML field. The `DomainConfig._validate_cross_references` validator builds and caches the reverse index at load time.

This also simplifies the wizard: Step 3 (Business Units) no longer needs to maintain a processes multiselect that depends on Step 4 (Processes).

### 3.5 APQC leakage on `ProcessConfig`

**Problem.** `ProcessConfig.apqc_section_id` is banking-specific. APQC is a process classification framework used heavily in banking and manufacturing; it has no meaning for, say, a pharmaceutical company's GxP processes. Its presence on the core `ProcessConfig` breaks domain-agnosticism before it begins.

**Remedy.** Replace with a generic `ProcessConfig.domain_metadata: dict[str, Any] = {}` field. The banking domain writes `{"apqc_section_id": "4.0"}` into this dict; other domains write their own keys. The control ID scheme (currently `CTRL-{L1:02d}{L2:02d}-{TypeCode}-{Seq:03d}` parsed from `apqc_section_id`) moves to a per-`DomainProfile` `ControlIdBuilder` strategy rather than hard-coded parsing.

The existing `hierarchy_id` field on `ProcessConfig` can stay, but document it as a domain-neutral path identifier whose format is determined by the domain.

### 3.6 No `DomainProfile` packaging decision

**Problem.** The blueprint assumes `DomainConfig` YAML is the unit of domain specificity. But there is more to a domain than a DomainConfig: there is the control ID scheme, there may be domain-specific validators, domain-specific regulatory keyword dictionaries used by scanners, and domain-specific prompt scaffolding (the SWE blueprint's `build_spec_user_prompt` inlines banking-specific framings). Without packaging these, "new domain" still requires editing engine code.

**Remedy.** Introduce `DomainProfile` as a directory-plus-registry convention:

```
domains/
  banking/
    domain_config.yaml          # the existing banking_standard.yaml
    risk_taxonomy.yaml          # the attached risk_taxonomy.yaml
    control_id_builder.py       # subclass of ControlIdBuilder protocol
    regulatory_keywords.yaml    # seed dict for regulatory_coverage_scanner
    prompts/                    # domain-specific prompt fragments (optional)
      spec_context.txt
      narrative_style.txt
  _registry.py                  # DomainProfileRegistry
```

`src/controlnexus/core/domain_profile.py` defines:

```python
class DomainProfile(BaseModel):
    name: str
    config: DomainConfig
    risk_taxonomy: RiskTaxonomy   # new: parsed from risk_taxonomy.yaml
    control_id_builder: ControlIdBuilder
    regulatory_keywords: dict[str, list[str]] = {}
    prompt_fragments: dict[str, str] = {}
```

A `DomainProfileRegistry` loads profiles by name. The engine receives a `DomainProfile` at the graph entry point and passes it through state instead of the raw `DomainConfig`.

This is the highest-leverage change in this document. Without it, domain-agnosticism is a slogan.

### 3.7 `current_risk: dict` violates the Pydantic-everywhere convention

**Problem.** The blueprint adds `current_risk: dict` to `ForgeState`. The Architecture doc states "Pydantic everywhere: all data structures are Pydantic v2 models with `ConfigDict(frozen=True)` on immutable types." A dict slipping into runtime state between typed nodes is a future source of AttributeError.

**Remedy.** Define `ResolvedRisk` as a frozen Pydantic model and use it in the state:

```python
class ResolvedRisk(BaseModel):
    model_config = ConfigDict(frozen=True)
    risk_id: str
    risk_name: str
    level_1: str
    sub_group: str | None
    severity: int
    multiplier: float
    description: str
    mitigating_links: list[MitigationLink]
    selected_control_type: str  # which type from mitigating_links this control addresses
```

The selected control type belongs on the resolved risk because it closes the loop: a `FinalControlRecord` can carry `risk_id` and reviewers can trace *which mitigating link the control fulfills*.

---

## 4. Three Gaps the Blueprint Does Not Address

### 4.1 Policy/process as input root

The user's stated requirement — "policy or process lends itself to risks which lends itself to controls" — implies an ingestion path from a policy document. The SWE blueprint assumes processes are hand-authored YAML. The mechanism to go from a policy PDF or process narrative to a runtime `ProcessConfig` + `RiskInstance` set is never specified.

This is Deliverable B in the V2 prompt. I have intentionally not specified it here and am leaving it to the ASI. My preference if forced to choose: a `PolicyIngestionAgent` that runs as a preprocessing sub-graph, producing a transient in-memory `DomainConfig` augmentation that the main graph consumes. Persistence is an explicit user action, not automatic. Provenance is captured by adding `source_policy_clause: str | None` to `RiskInstance` and `source_process_step: str | None` to `FinalControlRecord`.

### 4.2 Synthetic-vs-policy mode routing

The user explicitly wants both modes. The blueprint implicitly assumes the policy/process-first mode by restructuring everything around processes. The routing affordance — how the user or the system decides which mode to run, what the UX looks like, and how the graph routes — is never discussed.

Recommended routing: a mode enum on `ForgeState` (`mode: Literal["policy_first", "synthetic"]`). A conditional edge after `init_node` routes to either `policy_ingest_node` or directly to `select_node`. If `policy_first` is selected but no policy is attached, warn and fall back to synthetic. The UI in `control_builder.py` / `modular_tab.py` gets a mode toggle at the top of the generation pane.

### 4.3 Risk-awareness in the analysis side

The blueprint focuses exclusively on the generation pipeline. The analysis pipeline (four scanners producing a `GapReport`) is scoped out by a footnote. But gap analysis with a risk taxonomy in hand is strictly more powerful: "you have 8 controls for risk RCO-001 AML but 0 for RCO-002 Privacy Breaches" is a more actionable finding than "your AffinityMatrix shows Privacy gaps." A follow-on workstream should make at least `regulatory_coverage_scan` and `ecosystem_balance_analysis` risk-aware. Not this task, but worth recognizing as the natural next step.

---

## 5. Consolidated Schema Proposal

Putting §3 together, the target `DomainConfig` shape is:

```python
class DomainConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    description: str
    # Taxonomies (new + changed)
    risk_level_1_categories: list[RiskLevel1Category] = Field(default_factory=list)  # NEW
    risk_catalog: list[RiskCatalogEntry] = Field(default_factory=list)               # NEW
    control_types: list[ControlTypeConfig] = Field(min_length=1)                     # unchanged
    # Organizational
    business_units: list[BusinessUnitConfig] = Field(default_factory=list)           # changed: no primary_sections, no key_control_types
    processes: list[ProcessConfig] = Field(default_factory=list)                     # renamed from process_areas
    # Controls scaffolding (unchanged)
    placements: list[PlacementConfig]
    methods: list[MethodConfig]
    frequency_tiers: list[FrequencyTier]
    narrative: NarrativeConstraints
    quality_ratings: list[str]
```

And `ProcessConfig`:

```python
class ProcessConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    domain: str = ""
    owner_bu_ids: list[str] = Field(default_factory=list)  # authoritative BU ownership
    domain_metadata: dict[str, Any] = Field(default_factory=dict)  # e.g., apqc_section_id for banking
    risks: list[RiskInstance] = Field(default_factory=list)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    exemplars: list[ExemplarConfig] = Field(default_factory=list)
    hierarchy_id: str = ""  # domain-specific path, format determined by DomainProfile
```

And `RiskInstance`:

```python
class RiskInstance(BaseModel):
    model_config = ConfigDict(frozen=True)
    risk_id: str                                    # → RiskCatalogEntry.id
    severity: int = Field(default=3, ge=1, le=5)    # overrides catalog default
    multiplier: float = Field(default=1.0)          # allocation tuner, distinct from severity
    mitigating_links: list[MitigationLink] = Field(default_factory=list)  # overrides catalog defaults
    rationale: str = ""
    source_policy_clause: str | None = None         # provenance when risk derived from policy
```

`BusinessUnitConfig` loses `primary_sections` and `key_control_types` entirely; it gains nothing; it keeps `id`, `name`, `description`, `regulatory_exposure`.

---

## 6. Evaluation Strategy for Domain-Agnosticism

Domain-agnosticism cannot be verified by reading code. It is verified by running the engine on two domains.

Recommended fixture: `tests/fixtures/domains/minimal_healthcare/` containing:

- `domain_config.yaml` with 3 control types, 2 business units, 2 processes, 6 risk catalog entries across 3 Level 1 categories.
- `risk_taxonomy.yaml` with 3 Level 1 categories (e.g., Patient Safety, Privacy, Operational).
- A `control_id_builder.py` with a different ID scheme from banking's (e.g., `HC-{process_id}-{seq:04d}`).

A new test `test_domain_agnostic.py` runs the full generation pipeline on both `domains/banking` and the minimal healthcare fixture, asserting:

- Both produce valid `FinalControlRecord`s.
- The banking run does not import anything from the healthcare fixture and vice versa.
- The control IDs follow their respective schemes.
- The generated controls reference the correct risk taxonomy.
- No code outside `domains/` contains the strings `APQC`, `banking`, or references banking-specific regulatory frameworks.

That last check is brittle but cheap and catches drift.

---

## 7. Migration Sequencing

The blueprint mentions migration at a high level. Here is the minimal reversible ordering:

1. Add new Pydantic classes alongside existing ones (`RiskCatalogEntry`, `RiskInstance`, `RiskLevel1Category`, `MitigationLink`, `ResolvedRisk`) with full test coverage. No behavior change yet. Green gate: existing 308 tests pass.
2. Add `risk_catalog` and `risk_level_1_categories` as optional fields on `DomainConfig`. Extend validator. Green gate: existing configs still load.
3. Load `risk_taxonomy.yaml` into `banking_standard.yaml` via a migration script. Commit the augmented `banking_standard.yaml`. Green gate: existing tests pass; new tests confirm `risk_catalog` is populated.
4. Introduce `ProcessConfig` alongside `ProcessAreaConfig`. Add a synthesis function that builds `ProcessConfig` from `ProcessAreaConfig` at load time. Green gate: new synthesized processes carry correct data.
5. Implement `RiskAgent` and its deterministic fallback. Unit test in isolation. Green gate: `RiskAgent` tests pass; existing graph unchanged.
6. Add `risk_agent_node` to a new parallel graph (`forge_modular_graph_v2`). Leave the v1 graph untouched. Green gate: v1 graph tests pass, v2 graph tests pass.
7. Port `build_assignment_matrix` to the risk-driven shape in the v2 graph only. Green gate: v2 generates controls grounded in risks; v1 unchanged.
8. Switch the Streamlit modular_tab to v2 behind a feature flag. Green gate: flag off → v1 behavior; flag on → v2 behavior.
9. Retire `ProcessAreaConfig`, `RiskProfileConfig`, `AffinityConfig`. Remove v1 graph. Green gate: all tests pass; config loader only supports new schema.
10. Extract banking-specific concerns into `domains/banking/`. Introduce `DomainProfile`. Green gate: domain-agnostic evaluation test suite passes on both banking and minimal healthcare fixtures.

Each step is independently deployable and reversible.

---

## 8. What This Plan Does Not Decide

- Policy ingestion mechanism (Deliverable B in the V2 prompt — left to the ASI).
- Synthetic-vs-policy mode routing UX (sketched in §4.2 but not finalized).
- Whether to extend risk-awareness to the analysis pipeline (flagged as follow-on).
- Specific effectiveness values for `MitigationLink.effectiveness`.
- Whether `DomainProfile` is loaded lazily or eagerly.
- Whether `RiskCatalogEntry` IDs should be content-addressed (hash) or human-assigned (the current choice). Human-assigned is simpler and readable; hash is tamper-evident and versionable. Defer to the ASI.

These are explicitly the ASI's calls to make.
