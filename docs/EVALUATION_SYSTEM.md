# Evaluation & Metrics System — Design Specification

> Extends the existing `TraceDB` SQLite tracing store into a full evaluation and
> metrics store that captures output quality alongside operational data — enabling
> run-over-run comparison, model A/B testing, and cost/quality tradeoff analysis.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Schema](#2-schema)
3. [Metric Capture Points](#3-metric-capture-points)
4. [Run Metrics Computation](#4-run-metrics-computation)
5. [Run Comparisons](#5-run-comparisons)
6. [Quality Score Formula](#6-quality-score-formula)
7. [Query Methods](#7-query-methods)
8. [UI Tab](#8-ui-tab)

---

## 1. Overview

### Existing State

The `TraceDB` (at `data/traces.db`) contains 4 tables:

| Table | Purpose |
|-------|---------|
| `runs` | One row per pipeline invocation |
| `events` | Every `PipelineEvent` emitted |
| `node_executions` | Timing and state summary per graph node |
| `llm_calls` | Full LLM request/response with token counts and latency |

These capture **operational** data: did the call work, how long, how many tokens.

### What We're Adding

1. **Quality columns on `llm_calls`** — validation pass/fail, failure codes, retry
   attempt number, output type, and the parsed structured output.
2. **`run_metrics` table** — pre-aggregated summary of every run for instant
   comparison (no re-aggregation needed).
3. **`run_comparisons` table** — pairwise run comparison including deltas and
   agreement metrics.
4. **Evaluation Tab (Tab 6)** — developer-facing UI for run history, detail
   drill-down, side-by-side comparison, and cost vs quality plotting.

---

## 2. Schema

### 2a. Extended `llm_calls` Columns

Added via `ALTER TABLE` migration (see §2d):

```sql
ALTER TABLE llm_calls ADD COLUMN validation_passed BOOLEAN;
ALTER TABLE llm_calls ADD COLUMN validation_failures TEXT;   -- JSON array of failure code strings
ALTER TABLE llm_calls ADD COLUMN retry_attempt INTEGER DEFAULT 0;
ALTER TABLE llm_calls ADD COLUMN output_type TEXT;            -- 'classify', 'map', 'assess', 'risk'
ALTER TABLE llm_calls ADD COLUMN parsed_output TEXT;          -- JSON of the structured agent output
```

All columns are nullable so existing rows remain valid.

### 2b. `run_metrics` Table

```sql
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id            TEXT PRIMARY KEY,
    regulation_name   TEXT,
    model             TEXT,
    provider          TEXT,
    scope_description TEXT,

    -- Cost metrics
    total_tokens          INTEGER DEFAULT 0,
    total_prompt_tokens   INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    estimated_cost_usd    REAL DEFAULT 0.0,
    total_latency_ms      REAL DEFAULT 0.0,
    avg_latency_per_call_ms REAL DEFAULT 0.0,
    total_llm_calls       INTEGER DEFAULT 0,

    -- Classification phase
    classify_total        INTEGER DEFAULT 0,
    classify_passed       INTEGER DEFAULT 0,
    classify_pass_rate    REAL DEFAULT 0.0,
    classify_retries      INTEGER DEFAULT 0,
    classify_category_distribution TEXT,

    -- Mapping phase
    map_total             INTEGER DEFAULT 0,
    map_passed            INTEGER DEFAULT 0,
    map_pass_rate         REAL DEFAULT 0.0,
    map_avg_confidence    REAL DEFAULT 0.0,
    map_retries           INTEGER DEFAULT 0,

    -- Assessment phase
    assess_total          INTEGER DEFAULT 0,
    assess_passed         INTEGER DEFAULT 0,
    assess_pass_rate      REAL DEFAULT 0.0,
    coverage_covered_count   INTEGER DEFAULT 0,
    coverage_partial_count   INTEGER DEFAULT 0,
    coverage_gap_count       INTEGER DEFAULT 0,
    coverage_covered_pct     REAL DEFAULT 0.0,
    coverage_partial_pct     REAL DEFAULT 0.0,
    coverage_gap_pct         REAL DEFAULT 0.0,

    -- Risk phase
    risk_total            INTEGER DEFAULT 0,
    risk_passed           INTEGER DEFAULT 0,
    risk_pass_rate        REAL DEFAULT 0.0,
    risk_avg_impact       REAL DEFAULT 0.0,
    risk_avg_frequency    REAL DEFAULT 0.0,
    risk_distribution     TEXT,

    -- Overall quality
    overall_pass_rate     REAL DEFAULT 0.0,
    overall_retry_rate    REAL DEFAULT 0.0,
    quality_score         REAL DEFAULT 0.0,

    computed_at           REAL
);
```

### 2c. `run_comparisons` Table

```sql
CREATE TABLE IF NOT EXISTS run_comparisons (
    comparison_id     TEXT PRIMARY KEY,
    run_id_a          TEXT NOT NULL,
    run_id_b          TEXT NOT NULL,

    model_a           TEXT,
    model_b           TEXT,
    regulation_a      TEXT,
    regulation_b      TEXT,

    -- Cost deltas (b − a)
    token_delta       INTEGER,
    cost_delta_usd    REAL,
    latency_delta_ms  REAL,

    -- Quality deltas (b − a)
    quality_delta     REAL,
    pass_rate_delta   REAL,

    -- Agreement metrics (same regulation only)
    classify_agreement_rate REAL,
    map_overlap_rate       REAL,
    coverage_agreement_rate REAL,

    notes             TEXT,
    computed_at        REAL,

    FOREIGN KEY (run_id_a) REFERENCES runs(run_id),
    FOREIGN KEY (run_id_b) REFERENCES runs(run_id)
);
```

### 2d. Migration Pattern

SQLite does not support `ALTER TABLE ADD COLUMN IF NOT EXISTS`. On
`TraceDB.__init__`, after `_ensure_schema()`, a new `_migrate_schema()` method:

1. Queries `PRAGMA table_info(llm_calls)`.
2. Collects existing column names.
3. For each new column not yet present, runs `ALTER TABLE llm_calls ADD COLUMN …`.

This is idempotent — safe to run on old or new databases.

---

## 3. Metric Capture Points

Quality data is **not** captured inside `TracingTransportClient` (which only
sees raw LLM responses). Instead, it's captured at the **graph-node level**
after validation, via `TraceDB.update_llm_call_quality()`.

| Graph | Node | Agent | `output_type` | Validation Function |
|-------|------|-------|---------------|---------------------|
| Graph 1 | `classify_group` | `ObligationClassifierAgent` | `"classify"` | `validate_classification()` |
| Graph 2 | `map_group` | `APQCMapperAgent` | `"map"` | `validate_mapping()` |
| Graph 2 | `assess_coverage` | `CoverageAssessorAgent` | `"assess"` | `validate_coverage()` |
| Graph 2 | `extract_and_score` | `RiskExtractorAndScorerAgent` | `"risk"` | `validate_risk()` |

Each node calls `update_llm_call_quality()` after running validation, passing:
- `validation_passed`: `True` if the validator returned no failures
- `validation_failures`: the list of failure code strings
- `retry_attempt`: 0 for first attempt (retry logic not yet implemented)
- `output_type`: one of `"classify"`, `"map"`, `"assess"`, `"risk"`
- `parsed_output`: the dict returned by the agent

### Row Matching

`update_llm_call_quality()` matches the `llm_calls` row by:

```sql
WHERE run_id = ? AND node_name = ? AND timestamp >= ?
ORDER BY timestamp DESC LIMIT 1
```

The timestamp window uses `time.time() - 60` to find the row inserted by
`TracingTransportClient` during the same node execution.

---

## 4. Run Metrics Computation

`compute_run_metrics(run_id)` queries `llm_calls` for the given run, grouped
by `output_type`, and aggregates:

### Cost Metrics

```sql
SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens),
       SUM(latency_ms), COUNT(*), model
FROM llm_calls WHERE run_id = ?
```

**Cost estimation** uses per-model pricing:

| Model | Prompt ($/1K) | Completion ($/1K) |
|-------|---------------|-------------------|
| `gpt-4o` | 0.0025 | 0.01 |
| `gpt-4o-mini` | 0.00015 | 0.0006 |
| `claude-sonnet-4-20250514` | 0.003 | 0.015 |
| `ica_default` | 0.003 | 0.015 |

### Per-Phase Aggregation

For each `output_type` in (`classify`, `map`, `assess`, `risk`):

```sql
SELECT COUNT(*) AS total,
       SUM(CASE WHEN validation_passed = 1 THEN 1 ELSE 0 END) AS passed,
       SUM(CASE WHEN retry_attempt > 0 THEN 1 ELSE 0 END) AS retries
FROM llm_calls WHERE run_id = ? AND output_type = ?
```

### Coverage Distribution

From `assess`-type calls, parsed output is examined for `overall_coverage`:

```python
for row in assess_calls:
    parsed = json.loads(row["parsed_output"] or "{}")
    status = parsed.get("overall_coverage", "")
    if status == "Covered": covered_count += 1
    elif status == "Partially Covered": partial_count += 1
    elif status == "Not Covered": gap_count += 1
```

### Mapping Confidence

Average of `confidence` field from `map`-type parsed outputs.

### Risk Distribution

From `risk`-type parsed outputs, counting `inherent_risk_rating` values.

### Insert or Replace

Uses `INSERT OR REPLACE INTO run_metrics …` so it's idempotent.

### Call Sites

1. `finalize_node` in Graph 2 (after all phases complete).
2. `_build_partial_results()` in the UI (for interrupted runs).

---

## 5. Run Comparisons

`compare_runs(run_id_a, run_id_b)` loads `run_metrics` for both runs (computing
them first if missing), then:

### Delta Metrics

Simple subtraction: `b.value - a.value` for tokens, cost, latency, quality
score, pass rate.

### Agreement Metrics (same regulation only)

Only computed when `regulation_a == regulation_b`. Otherwise set to `NULL`.

1. **Classification agreement:** Match `parsed_output` from `classify`-type calls
   by citation. Compare `obligation_category` values. Rate = matching / total.

2. **Mapping overlap:** For each citation, collect sets of `apqc_hierarchy_id`
   from `map`-type calls. Compute Jaccard similarity per citation, then average.

3. **Coverage agreement:** Match `assess`-type calls by citation. Compare
   `overall_coverage` values. Rate = matching / total.

### Storage

Each comparison gets a UUID `comparison_id` and is inserted into
`run_comparisons`.

---

## 6. Quality Score Formula

```python
quality_score = (
    0.30 * overall_pass_rate +
    0.25 * (1.0 - overall_retry_rate) +
    0.20 * map_avg_confidence +
    0.15 * coverage_covered_pct +
    0.10 * (1.0 - normalize(avg_latency_per_call_ms, 0, 60000))
)
```

Where `normalize(x, lo, hi)` clamps `x` to `[lo, hi]` and maps linearly to
`[0.0, 1.0]`.

### Weight Rationale

| Component | Weight | Rationale |
|-----------|--------|-----------|
| `overall_pass_rate` | 0.30 | Validation quality is the strongest signal. If outputs don't pass schema validation, nothing downstream is reliable. |
| `1 - overall_retry_rate` | 0.25 | Efficiency matters. Fewer retries = more predictable latency and cost. Also a proxy for prompt quality — good prompts don't need retries. |
| `map_avg_confidence` | 0.20 | The LLM's self-reported confidence on APQC mappings. Not ground truth, but a useful signal — especially for comparing models on the same regulation. |
| `coverage_covered_pct` | 0.15 | Higher coverage means more obligations are addressed by controls. Partially reflects data quality (control dataset completeness) but still a meaningful output metric. |
| `1 - normalized_latency` | 0.10 | Speed is a nice-to-have, not a primary concern. Normalized to 0–60s range so outliers don't dominate. |

The weights sum to 1.0, giving a final score in `[0.0, 1.0]`. The formula
intentionally overweights correctness (pass rate + efficiency = 0.55) and
underweights speed (0.10).

---

## 7. Query Methods

All read methods return Python dicts (not `sqlite3.Row`). They live in
`TraceDB` alongside existing query methods.

| Method | Returns | Purpose |
|--------|---------|---------|
| `list_run_metrics(limit=50)` | `list[dict]` | Recent run metrics, ordered by `computed_at DESC` |
| `get_run_metrics(run_id)` | `dict \| None` | Single run's metrics |
| `list_comparisons(limit=20)` | `list[dict]` | Recent comparisons |
| `get_comparison(comparison_id)` | `dict \| None` | Single comparison |
| `get_phase_breakdown(run_id)` | `dict` | Per-phase metrics with individual call details |
| `get_cost_history(limit=20)` | `list[dict]` | `(run_id, model, tokens, cost, quality)` for cost vs quality plots |

---

## 8. UI Tab

**Tab 6: Evaluation** — developer-facing, inserted after Results.

### Section 1 — Run History Table
Sortable `st.dataframe` from `list_run_metrics()`. Columns: timestamp,
regulation, model, tokens, cost, pass rate, quality score, coverage %.

### Section 2 — Selected Run Detail
Metric cards + per-phase bar chart + token pie chart + latency histogram.

### Section 3 — Run Comparison
Two dropdowns to select runs. Side-by-side metrics with delta indicators.
Agreement metrics when same regulation. Disagreement table.

### Section 4 — Cost vs Quality Scatter
Matplotlib scatter plot: x = cost, y = quality, colored by model.
