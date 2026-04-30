# ControlNexus Architecture v3 — Mermaid Diagrams

> **Companion to** [Architecture-v3.md](../Architecture-v3.md).
> All diagrams reflect the implemented state after the BU → Process → Risk → Control pivot,
> two-tier risk taxonomy, DomainProfile packaging, and policy-first mode routing.

---

## 1. High-Level Pipeline

```mermaid
flowchart LR
    UI["UI Tab<br/>(modular_tab / control_builder)"]
    DC["DomainConfig<br/>(YAML / wizard)"]
    DP["DomainProfile<br/>(config + taxonomy + plugins)"]
    AM["Assignment Matrix<br/>(risk-weighted allocation)"]
    LG["LangGraph<br/>(10-node forge_modular_graph)"]
    FCR["FinalControlRecord[]"]
    AN["Analysis<br/>(5 scanners → GapReport)"]
    EX["Export<br/>(CSV / JSON / Excel)"]

    UI -->|"load / build"| DC
    DC -->|"+ risk_taxonomy.yaml"| DP
    DP -->|"target_count + risk weights"| AM
    AM -->|"assignments[]"| LG
    LG -->|"generated_records"| FCR
    FCR -->|"gap analysis"| AN
    FCR -->|"render + download"| EX
```

---

## 2. Entity Model (DomainConfig v3)

```mermaid
erDiagram
    DomainConfig ||--o{ ControlTypeConfig : control_types
    DomainConfig ||--o{ BusinessUnitConfig : business_units
    DomainConfig ||--o{ ProcessConfig : processes
    DomainConfig ||--o{ ProcessAreaConfig : "process_areas (legacy)"
    DomainConfig ||--o{ RiskLevel1Category : risk_level_1_categories
    DomainConfig ||--o{ RiskCatalogEntry : risk_catalog
    DomainConfig ||--o{ PlacementConfig : placements
    DomainConfig ||--o{ MethodConfig : methods
    DomainConfig ||--o{ FrequencyTier : frequency_tiers
    DomainConfig ||--|| NarrativeConstraints : narrative

    RiskLevel1Category ||--o{ RiskCatalogEntry : "parent (level_1)"
    RiskCatalogEntry ||--o{ MitigationLink : default_mitigating_links
    MitigationLink }o--|| ControlTypeConfig : "control_type (name ref)"

    ProcessConfig ||--o{ RiskInstance : risks
    ProcessConfig ||--|| RegistryConfig : registry
    ProcessConfig ||--o{ ExemplarConfig : exemplars
    ProcessConfig }o--o{ BusinessUnitConfig : "owner_bu_ids (back-ref)"
    RiskInstance }o--|| RiskCatalogEntry : "risk_id (ID ref)"
    RiskInstance ||--o{ MitigationLink : mitigating_links

    DomainConfig {
        string name
        string description
        list quality_ratings
    }
    RiskLevel1Category {
        string name
        string code
        string definition
        string grounding
        list sub_groups
    }
    RiskCatalogEntry {
        string id
        string name
        string level_1
        string level_1_code
        string sub_group
        int default_severity
        string description
        string grounding
    }
    MitigationLink {
        string control_type
        float effectiveness
        int line_of_defense
    }
    RiskInstance {
        string risk_id
        int severity
        float multiplier
        string rationale
        string source_policy_clause
    }
    ProcessConfig {
        string id
        string name
        string domain
        dict domain_metadata
        string hierarchy_id
        list owner_bu_ids
    }
    BusinessUnitConfig {
        string id
        string name
        string description
        list regulatory_exposure
    }
    ControlTypeConfig {
        string name
        string definition
        string code
        string min_frequency_tier
        list placement_categories
        list evidence_criteria
    }
    ResolvedRisk {
        string risk_id
        string risk_name
        string level_1
        string sub_group
        int severity
        float multiplier
        string selected_control_type
    }
```

---

## 3. ForgeState (Runtime — v3)

```mermaid
erDiagram
    ForgeState ||--|| DomainConfig_dict : domain_config
    ForgeState ||--o{ ControlAssignment_dict : assignments
    ForgeState ||--|| ControlAssignment_dict : current_assignment
    ForgeState ||--|| ResolvedRisk_dict : current_risk
    ForgeState ||--o{ FinalRecord_dict : "generated_records (reducer)"
    ForgeState ||--o{ ToolLog_dict : "tool_calls_log (reducer)"
    ForgeState ||--o{ PolicyRisk_dict : "policy_risks"
    ForgeState ||--o{ PolicyProcess_dict : "policy_processes"

    ForgeState {
        string config_path
        dict domain_config
        bool llm_enabled
        string provider
        bool ica_tool_calling
        string generation_mode
        dict distribution_config
        string section_filter
        string process_filter
        int target_count
        int current_idx
        dict current_risk
        dict current_spec
        dict current_narrative
        dict current_enriched
        int retry_count
        bool validation_passed
        list validation_failures
        string retry_appendix
        list policy_risks
        list policy_processes
        dict plan_payload
    }
```

---

## 4. Graph Topology (10-Node — v3)

```mermaid
flowchart TD
    INIT["init_node"]
    POLICY["policy_ingest_node"]
    SELECT["select_node"]
    RISK["risk_agent_node"]
    SPEC["spec_node"]
    NARR["narrative_node"]
    VAL["validate_node"]
    ENRICH["enrich_node"]
    MERGE["merge_node"]
    FINAL["finalize_node"]
    ENDNODE["END"]

    INIT -->|"synthetic mode"| SELECT
    INIT -->|"policy_first mode"| POLICY
    INIT -->|"no assignments"| FINAL
    POLICY --> SELECT
    SELECT --> RISK
    RISK --> SPEC
    SPEC --> NARR
    NARR --> VAL
    VAL -->|"passed"| ENRICH
    VAL -->|"failed (retry ≤ 3)"| NARR
    ENRICH --> MERGE
    MERGE -->|"has_more"| SELECT
    MERGE -->|"done"| FINAL
    FINAL --> ENDNODE

    style POLICY fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style RISK fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style INIT fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style FINAL fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style ENDNODE fill:#f5f5f5,stroke:#757575
```

---

## 5. Agent Sequence — One Control's Journey

```mermaid
sequenceDiagram
    participant SN as select_node
    participant RA as RiskAgent
    participant SA as SpecAgent
    participant NA as NarrativeAgent
    participant VN as validate_node
    participant EA as EnricherAgent
    participant MN as merge_node

    SN->>SN: Pick assignment[idx]
    SN->>RA: risk_id from assignment
    RA->>RA: Lookup catalog + instance<br/>→ ResolvedRisk dict
    RA->>SA: current_risk + assignment
    SA->>SA: Deterministic or LLM spec<br/>(placement, method, hierarchy_id)
    SA->>NA: locked_spec + risk context
    NA->>NA: Deterministic or LLM narrative<br/>(who, what, when, where, why)
    NA->>VN: current_narrative
    VN->>VN: 6-rule validation
    alt Validation passed
        VN->>EA: validated control
        EA->>EA: Deterministic or LLM enrichment<br/>(quality_rating, evidence, rationale)
        EA->>MN: enriched control
        MN->>MN: Merge → FinalControlRecord<br/>Append to generated_records
    else Validation failed (retry ≤ 3)
        VN-->>NA: retry_appendix with failures
    end
```

---

## 6. Two-Tier Risk Taxonomy

```mermaid
flowchart TD
    TAX["risk_taxonomy.yaml"]

    subgraph L1["Level 1 Categories (9)"]
        STR["Strategy<br/>(STR)"]
        MKT["Market Place<br/>(MKT)"]
        REP["Reputation<br/>(REP)"]
        RCO["Regulatory Compliance<br/>(RCO)"]
        CYB["Cyber<br/>(CYB)"]
        FMK["Financial Markets<br/>(FMK)"]
        CRD["Credit<br/>(CRD)"]
        TAL["Talent<br/>(TAL)"]
        OPS["Operational<br/>(OPS)"]
    end

    subgraph L2["Level 2 Entries (115)"]
        R1["STR-001 … STR-008"]
        R2["MKT-001 … MKT-004"]
        R3["REP-001 … REP-003"]
        R4["RCO-001 … RCO-008"]
        R5["CYB-001 … CYB-006"]
        R6["FMK-001 … FMK-007"]
        R7["CRD-001 … CRD-005"]
        R8["TAL-001 … TAL-005"]
        R9["OPS-001 … OPS-069"]
    end

    subgraph OPS_SUB["OPS Sub-Groups (9)"]
        SG1["Transaction Operations"]
        SG2["Fraud and Fiduciary"]
        SG3["Technology and Infrastructure"]
        SG4["Information and Data Mgmt"]
        SG5["Third Party"]
        SG6["Business Continuity"]
        SG7["Project and Change Mgmt"]
        SG8["Model"]
        SG9["Legal"]
    end

    TAX --> L1
    STR --> R1
    MKT --> R2
    REP --> R3
    RCO --> R4
    CYB --> R5
    FMK --> R6
    CRD --> R7
    TAL --> R8
    OPS --> R9
    OPS --> OPS_SUB
```

---

## 7. Assignment Matrix — Risk-Weighted Allocation

```mermaid
flowchart TD
    TC["target_count"]
    PROC["ProcessConfig[]"]
    RI["RiskInstance[]"]
    W["Weight = severity × multiplier"]
    ALLOC["Proportional allocation<br/>across (process, risk) pairs"]
    ML["MitigationLink[]"]
    EFF["Distribute by effectiveness<br/>across control types"]
    BU["Cycle owner_bu_ids"]
    ASN["ControlAssignment[]"]

    TC --> ALLOC
    PROC --> RI
    RI --> W
    W --> ALLOC
    ALLOC -->|"per (process, risk, count)"| ML
    ML -->|"weighted by effectiveness"| EFF
    EFF --> BU
    BU --> ASN

    style TC fill:#fff3e0,stroke:#e65100
    style ASN fill:#e8f5e9,stroke:#2e7d32
```

---

## 8. DomainProfile Packaging

```mermaid
flowchart TD
    subgraph DomainDir["domains/banking/"]
        CFG["domain_config.yaml"]
        TAX["risk_taxonomy.yaml"]
        KW["regulatory_keywords.yaml"]
        subgraph Prompts["prompts/"]
            P1["spec_context.txt"]
            P2["narrative_style.txt"]
        end
    end

    REG["DomainProfileRegistry"]
    DP["DomainProfile"]
    DCFG["DomainConfig"]
    BLD["ControlIdBuilder"]

    DomainDir -->|"_load_from_dir()"| REG
    REG -->|"get('banking')"| DP
    CFG -->|"load_domain_config()"| DCFG
    TAX -->|"auto-merged by loader"| DCFG
    DCFG --> DP
    KW --> DP
    Prompts --> DP
    BLD -.->|"get_builder('banking')"| REG

    style DP fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style REG fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
```

---

## 9. Generation Mode Routing

```mermaid
flowchart LR
    UI["UI: Mode Toggle"]
    INIT["init_node"]
    PI["policy_ingest_node<br/>(stub)"]
    SEL["select_node"]

    UI -->|"generation_mode"| INIT

    INIT -->|"synthetic"| SEL
    INIT -->|"policy_first"| PI
    PI -->|"augmented config"| SEL

    style PI fill:#fff3e0,stroke:#e65100,stroke-dasharray: 5 5
```

---

## 10. Analysis Pipeline — 5 Scanners → GapReport

```mermaid
flowchart TD
    FCR["FinalControlRecord[]"]
    CFG["DomainConfig"]
    SP["SectionProfile[]<br/>(built from processes)"]

    S1["regulatory_coverage_scan"]
    S2["ecosystem_balance_analysis"]
    S3["frequency_coherence_scan"]
    S4["evidence_sufficiency_scan"]
    S5["risk_coverage_scan"]

    GR["GapReport"]

    FCR --> S1
    FCR --> S2
    FCR --> S3
    FCR --> S4
    FCR --> S5
    SP --> S1
    SP --> S2
    SP --> S3
    SP --> S4
    CFG -->|"risk_catalog"| S5

    S1 -->|"RegulatoryGap[]"| GR
    S2 -->|"BalanceGap[]"| GR
    S3 -->|"FrequencyIssue[]"| GR
    S4 -->|"EvidenceIssue[]"| GR
    S5 -->|"RiskCoverageGap[]"| GR

    style S5 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style GR fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
```

---

## 11. Relationship Cheat Sheet (v3 — Complete)

```mermaid
flowchart TB
    subgraph ConfigEntities["Config Entities (DomainConfig v3)"]
        DC["DomainConfig"]
        CT["ControlTypeConfig[]"]
        BU["BusinessUnitConfig[]"]
        PROC["ProcessConfig[]"]
        L1C["RiskLevel1Category[]"]
        RC["RiskCatalogEntry[]"]
        ML["MitigationLink[]"]
        RI["RiskInstance[]"]
        REG["RegistryConfig"]
        EX["ExemplarConfig[]"]
        PL["PlacementConfig[]"]
        MT["MethodConfig[]"]
        FT["FrequencyTier[]"]
        NC["NarrativeConstraints"]
    end

    subgraph DomainLayer["Domain Profile Layer"]
        DPR["DomainProfileRegistry"]
        DP["DomainProfile"]
        CIB["ControlIdBuilder"]
    end

    subgraph RuntimeState["Runtime State (ForgeState v3)"]
        FS["ForgeState"]
        ASN["assignments[]"]
        CA["current_assignment"]
        CR["current_risk"]
        CS["current_spec"]
        CN["current_narrative"]
        CE["current_enriched"]
        GR["generated_records[]"]
        PP["plan_payload"]
        GM["generation_mode"]
    end

    subgraph Agents["Agents (8)"]
        PIA["PolicyIngestionAgent"]
        RA["RiskAgent"]
        SA["SpecAgent"]
        NA["NarrativeAgent"]
        EA["EnricherAgent"]
        CPA["ConfigProposerAgent"]
        DA["DifferentiationAgent"]
        AR["AdversarialReviewer"]
    end

    subgraph Tools["Tool Belt (10)"]
        TV["taxonomy_validator"]
        RL["regulatory_lookup"]
        HS["hierarchy_search"]
        FL["frequency_lookup"]
        MR["memory_retrieval"]
        PLT["placement_lookup"]
        MLT["method_lookup"]
        ERL["evidence_rules_lookup"]
        EXL["exemplar_lookup"]
        RCL["risk_catalog_lookup"]
    end

    subgraph Analysis["Analysis (5 scanners)"]
        S1["regulatory_coverage"]
        S2["ecosystem_balance"]
        S3["frequency_coherence"]
        S4["evidence_sufficiency"]
        S5["risk_coverage"]
    end

    subgraph KBSources["KB Sources"]
        YAML["config YAML"]
        RTAX["risk_taxonomy.yaml"]
        CHROMA["ChromaDB"]
    end

    %% Config structure
    DC --> CT
    DC --> BU
    DC --> PROC
    DC --> L1C
    DC --> RC
    DC --> PL
    DC --> MT
    DC --> FT
    DC --> NC
    L1C -->|"parent"| RC
    RC --> ML
    ML -.->|"name ref"| CT
    PROC --> RI
    PROC --> REG
    PROC --> EX
    PROC -.->|"owner_bu_ids"| BU
    RI -.->|"risk_id"| RC
    RI --> ML

    %% Domain Profile layer
    YAML -->|"load_domain_config()"| DC
    RTAX -->|"auto-merged"| DC
    DPR -->|"get(name)"| DP
    DP --> DC
    DP --> CIB

    %% Config to Runtime
    DC -->|"init_node"| FS
    DC -->|"build_assignment_matrix()"| ASN

    %% Runtime flow
    GM -->|"after_init routing"| PIA
    ASN -->|"select_node"| CA
    CA -->|"risk_agent_node"| CR
    CR -->|"prompt context"| SA
    SA -->|"state write"| CS
    CS -->|"prompt context"| NA
    NA -->|"state write"| CN
    CN -->|"enrich_node"| CE
    CE -->|"reducer append"| GR
    GR -->|"finalize"| PP

    %% Agent to Tool calls
    RA --> RCL
    RA --> RL
    SA --> TV
    SA --> PLT
    SA --> MLT
    SA --> ERL
    SA --> HS
    NA --> FL
    NA --> EXL
    EA --> MR

    %% Tools read from Config
    RCL -.->|"reads"| RC
    TV -.->|"reads"| CT
    RL -.->|"reads"| REG
    FL -.->|"reads"| FT
    PLT -.->|"reads"| PL
    MLT -.->|"reads"| MT
    ERL -.->|"reads"| CT
    EXL -.->|"reads"| EX
    MR -.->|"reads"| CHROMA

    %% Analysis
    GR -->|"gap analysis"| S1
    GR --> S2
    GR --> S3
    GR --> S4
    GR --> S5
    RC -.->|"risk catalog"| S5

    %% Wizard
    CPA -->|"suggest_risks"| RI
    CPA -->|"suggest_processes"| PROC
    PIA -->|"policy extraction"| RI
```

---

## 12. FinalControlRecord Lineage

```mermaid
flowchart LR
    PROC["ProcessConfig"]
    RI["RiskInstance"]
    RC["RiskCatalogEntry"]
    ML["MitigationLink"]
    CT["ControlTypeConfig"]
    ASN["ControlAssignment"]
    RR["ResolvedRisk"]
    SPEC["Spec (locked fields)"]
    NARR["Narrative (5W)"]
    ENR["Enrichment (rating)"]
    FCR["FinalControlRecord"]

    PROC -->|"process_id, process_name"| ASN
    RI -->|"risk_id, severity"| ASN
    ML -->|"control_type"| ASN
    CT -->|"type definition"| ASN
    ASN --> RR
    RC -->|"name, level_1, description"| RR
    RR -->|"risk context"| SPEC
    SPEC -->|"placement, method, hierarchy"| NARR
    NARR -->|"who, what, when, where, why"| ENR
    ENR -->|"quality_rating, evidence"| FCR

    style FCR fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```
