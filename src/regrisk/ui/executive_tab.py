"""Tab: Executive View — final dashboard for executives.

Loads an Improved/Patched Full Assessment checkpoint JSON directly from disk
and renders:
  - Headline KPIs (obligation count, coverage %, residual risk profile)
  - Coverage / criticality / risk distribution panels
  - Top 5 gaps and Top 5 residual risks
  - Filter + sort bar
  - Scrollable list of expandable obligation cards with the most important
    information per obligation (text, APQC mapping, coverage, controls,
    residual risks, proposed improvements)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.ui.components import (
    CATEGORY_BG,
    coverage_indicator_html,
    format_citation,
    render_callout,
    render_metadata_strip,
    render_page_header,
    render_premium_table,
    render_section_header,
    risk_score_badge_html,
)

_log = logging.getLogger("regrisk.ui.tab.executive")

# ── Ordering helpers ──────────────────────────────────────────────────────────
_COVERAGE_RANK = {"Not Covered": 0, "Partially Covered": 1, "Covered": 2}
_COVERAGE_WORST = {0: "Not Covered", 1: "Partially Covered", 2: "Covered"}
_CRITICALITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
_RISK_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "": 4}
_CRITICALITY_COLOR = {"High": "#c62828", "Medium": "#f9a825", "Low": "#9e9e9e"}
_COVERAGE_COLOR = {"Covered": "#2e7d32", "Partially Covered": "#f9a825", "Not Covered": "#c62828"}
_CHANGE_TYPE_COLOR = {"new": "#1565c0", "enhancement": "#6a1b9a", "enhanced": "#6a1b9a"}


# ── Data loading ──────────────────────────────────────────────────────────────
def _checkpoint_dir() -> Path:
    """Resolve the data/checkpoints directory from this file location."""
    # src/regrisk/ui/executive_tab.py → ../../../../data/checkpoints
    return Path(__file__).resolve().parents[3] / "data" / "checkpoints"


def _list_assessment_checkpoints() -> list[Path]:
    """Return improved/patched full-assessment checkpoint files, newest first."""
    ck = _checkpoint_dir()
    if not ck.exists():
        return []
    patterns = [
        "Improved_Patched_Full_Assessment_*.json",
        "Patched_Full_Assessment_*.json",
        "Improved_Full_Assessment_*.json",
        "Full_Assessment_*.json",
    ]
    seen: dict[Path, float] = {}
    for pat in patterns:
        for p in ck.glob(pat):
            seen[p] = p.stat().st_mtime
    return sorted(seen, key=lambda p: seen[p], reverse=True)


@st.cache_data(show_spinner=False)
def _load_checkpoint(path: str, mtime: float) -> dict[str, Any]:
    """Load and parse a checkpoint JSON (cached by path + mtime)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def _index_data(path: str, mtime: float) -> dict[str, Any]:
    """Build per-citation indexes for fast access during rendering."""
    payload = _load_checkpoint(path, mtime)

    obligations = payload.get("classified_obligations", []) or []
    mappings = payload.get("obligation_mappings", []) or []
    assessments = payload.get("coverage_assessments", []) or []
    risks = payload.get("scored_risks", []) or []
    improvements = payload.get("proposed_improvements", []) or []
    controls = payload.get("controls", []) or []

    obligations_by_cit: dict[str, dict] = {}
    for ob in obligations:
        cit = ob.get("citation", "")
        if cit:
            obligations_by_cit[cit] = ob

    mappings_by_cit: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mappings_by_cit[m.get("citation", "")].append(m)

    assessments_by_cit: dict[str, list[dict]] = defaultdict(list)
    for a in assessments:
        assessments_by_cit[a.get("citation", "")].append(a)

    risks_by_cit: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risks_by_cit[r.get("source_citation", "")].append(r)

    improvements_by_cit: dict[str, list[dict]] = defaultdict(list)
    for imp in improvements:
        improvements_by_cit[imp.get("source_citation", "")].append(imp)

    controls_by_id: dict[str, dict] = {c.get("control_id", ""): c for c in controls if c.get("control_id")}

    # Per-obligation roll-ups
    coverage_by_cit: dict[str, str] = {}
    for cit, alist in assessments_by_cit.items():
        ranks = [_COVERAGE_RANK.get(a.get("overall_coverage", "Not Covered"), 0) for a in alist]
        coverage_by_cit[cit] = _COVERAGE_WORST[min(ranks)] if ranks else "Not Assessed"

    max_risk_by_cit: dict[str, str] = {}
    for cit, rlist in risks_by_cit.items():
        if rlist:
            best_rank = min(_RISK_RANK.get(r.get("inherent_risk_rating", ""), 4) for r in rlist)
            inv = {v: k for k, v in _RISK_RANK.items()}
            max_risk_by_cit[cit] = inv.get(best_rank, "")

    return {
        "payload": payload,
        "obligations_by_cit": obligations_by_cit,
        "mappings_by_cit": dict(mappings_by_cit),
        "assessments_by_cit": dict(assessments_by_cit),
        "risks_by_cit": dict(risks_by_cit),
        "improvements_by_cit": dict(improvements_by_cit),
        "controls_by_id": controls_by_id,
        "coverage_by_cit": coverage_by_cit,
        "max_risk_by_cit": max_risk_by_cit,
        "ordered_citations": [ob.get("citation", "") for ob in obligations if ob.get("citation")],
    }


# ── HTML helpers ──────────────────────────────────────────────────────────────
def _criticality_pill(tier: str) -> str:
    color = _CRITICALITY_COLOR.get(tier, "#9e9e9e")
    return (f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:0.78em;font-weight:600;">{escape(tier or "—")}</span>')


def _category_pill(cat: str) -> str:
    bg = CATEGORY_BG.get(cat, "#E2E3E5")
    return (f'<span style="background:{bg};color:#1a1a1a;padding:2px 8px;'
            f'border-radius:10px;font-size:0.78em;">{escape(cat or "—")}</span>')


def _change_pill(ct: str) -> str:
    color = _CHANGE_TYPE_COLOR.get((ct or "").lower(), "#455a64")
    return (f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:0.75em;font-weight:600;'
            f'text-transform:uppercase;">{escape(ct or "change")}</span>')


def _stacked_bar(counts: dict[str, int], colors: dict[str, str], order: list[str]) -> str:
    total = sum(counts.get(k, 0) for k in order) or 1
    segments = []
    for k in order:
        v = counts.get(k, 0)
        if v <= 0:
            continue
        pct = v / total * 100
        segments.append(
            f'<div style="background:{colors[k]};width:{pct:.2f}%;height:100%;'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-size:0.78em;font-weight:600;" title="{escape(k)}: {v}">'
            f'{v if pct > 6 else ""}</div>'
        )
    legend = " &nbsp; ".join(
        f'<span style="font-size:0.8em;"><span style="display:inline-block;width:10px;height:10px;'
        f'background:{colors[k]};border-radius:2px;vertical-align:middle;"></span> '
        f'{escape(k)} ({counts.get(k, 0)})</span>'
        for k in order
    )
    return (
        f'<div style="display:flex;height:24px;border-radius:6px;overflow:hidden;'
        f'border:1px solid #e0e0e0;">{"".join(segments)}</div>'
        f'<div style="margin-top:6px;">{legend}</div>'
    )


def _truncate(text: str, n: int = 280) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


# ── Helpers used by the summary section ───────────────────────────────────────
def _coverage_by_criticality(idx: dict[str, Any]) -> dict[str, dict[str, int]]:
    """For each criticality tier, count obligations by coverage status."""
    out: dict[str, dict[str, int]] = {
        t: {"Covered": 0, "Partially Covered": 0, "Not Covered": 0}
        for t in ("High", "Medium", "Low")
    }
    for cit, status in idx["coverage_by_cit"].items():
        if status not in out["High"]:
            continue
        tier = idx["obligations_by_cit"].get(cit, {}).get("criticality_tier", "Low")
        if tier in out:
            out[tier][status] += 1
    return out


def _list_item(left_html: str, right_html: str = "") -> str:
    return (
        f'<div style="display:flex;justify-content:space-between;'
        f'padding:4px 0;border-bottom:1px solid #f0f0f0;font-size:0.88em;">'
        f'<span>{left_html}</span><span style="color:#555;">{right_html}</span></div>'
    )


# ── Top banner (just title + KPI strip) ───────────────────────────────────────
def _render_top_banner(idx: dict[str, Any]) -> None:
    payload = idx["payload"]
    meta = payload.get("_meta", {})
    risk_register = payload.get("risk_register", {}) or {}

    total_obs = meta.get("obligation_count", len(idx["obligations_by_cit"]))
    cat_break = meta.get("category_breakdown", {}) or {}
    actionable = sum(cat_break.get(k, 0) for k in ("Controls", "Documentation", "Attestation"))

    cov_counts = {"Covered": 0, "Partially Covered": 0, "Not Covered": 0}
    for status in idx["coverage_by_cit"].values():
        if status in cov_counts:
            cov_counts[status] += 1
    assessed_total = sum(cov_counts.values()) or 1
    coverage_pct = (cov_counts["Covered"] + cov_counts["Partially Covered"]) / assessed_total * 100

    risk_summary = risk_register.get("summary", risk_register) or {}
    crit_count = risk_summary.get("critical_count", 0)
    high_count = risk_summary.get("high_count", 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total obligations", total_obs)
    c2.metric("Actionable", actionable, help="Controls + Documentation + Attestation")
    c3.metric("Coverage (any)", f"{coverage_pct:.0f}%",
              help=f"{cov_counts['Covered']} covered + {cov_counts['Partially Covered']} partial "
                   f"of {assessed_total} assessed")
    c4.metric("Critical + High risks", crit_count + high_count,
              help=f"Critical: {crit_count} · High: {high_count}")


# ── Executive Summary section (rendered at the END of the tab) ────────────────
def _render_summary(idx: dict[str, Any]) -> None:
    payload = idx["payload"]
    meta = payload.get("_meta", {})

    st.markdown("## Executive Summary")
    st.caption("End-of-page roll-up of obligations, processes, controls, risks, and proposed improvements.")

    # ── Row 1: distribution bars ────────────────────────────────────────────
    cov_counts = {"Covered": 0, "Partially Covered": 0, "Not Covered": 0}
    for status in idx["coverage_by_cit"].values():
        if status in cov_counts:
            cov_counts[status] += 1

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Coverage (per obligation)**")
        st.markdown(
            _stacked_bar(cov_counts, _COVERAGE_COLOR,
                         ["Covered", "Partially Covered", "Not Covered"]),
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown("**Criticality**")
        crit_break = meta.get("criticality_breakdown", {}) or {}
        st.markdown(
            _stacked_bar(crit_break, _CRITICALITY_COLOR, ["High", "Medium", "Low"]),
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown("**Inherent risk distribution**")
        risk_counts: dict[str, int] = defaultdict(int)
        for r in payload.get("scored_risks", []) or []:
            risk_counts[r.get("inherent_risk_rating", "Low")] += 1
        risk_colors = {"Critical": "#7b1fa2", "High": "#c62828",
                       "Medium": "#f9a825", "Low": "#9e9e9e"}
        st.markdown(
            _stacked_bar(dict(risk_counts), risk_colors,
                         ["Critical", "High", "Medium", "Low"]),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Row 2: Coverage specifics — by criticality + top covered/gap obligations ──
    st.markdown("### Coverage specifics")
    cov_by_crit = _coverage_by_criticality(idx)
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**Coverage by criticality tier**")
        for tier in ("High", "Medium", "Low"):
            row = cov_by_crit[tier]
            tier_total = sum(row.values()) or 1
            covered_pct = (row["Covered"] + row["Partially Covered"]) / tier_total * 100
            st.markdown(
                f'<div style="margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:0.88em;margin-bottom:3px;">'
                f'{_criticality_pill(tier)} '
                f'<span style="color:#555;">'
                f'{row["Covered"]} covered · {row["Partially Covered"]} partial · '
                f'{row["Not Covered"]} gap · ({covered_pct:.0f}% any)'
                f'</span></div>'
                f'{_stacked_bar(row, _COVERAGE_COLOR, ["Covered", "Partially Covered", "Not Covered"])}'
                f'</div>',
                unsafe_allow_html=True,
            )

    with cc2:
        st.markdown("**Top gaps (uncovered, by criticality + risk)**")
        gap_rows = []
        for cit, status in idx["coverage_by_cit"].items():
            if status == "Covered":
                continue
            ob = idx["obligations_by_cit"].get(cit, {})
            gap_rows.append({
                "cit": cit,
                "title": ob.get("section_title") or ob.get("title_level_3") or "",
                "criticality": ob.get("criticality_tier", "Low"),
                "coverage": status,
                "max_risk": idx["max_risk_by_cit"].get(cit, ""),
            })
        gap_rows.sort(key=lambda r: (
            _CRITICALITY_RANK.get(r["criticality"], 3),
            _COVERAGE_RANK.get(r["coverage"], 3),
            _RISK_RANK.get(r["max_risk"], 4),
        ))
        for row in gap_rows[:6]:
            st.markdown(
                f'<div style="padding:6px 10px;margin-bottom:4px;'
                f'background:#fafafa;border-left:3px solid {_COVERAGE_COLOR.get(row["coverage"], "#999")};'
                f'border-radius:4px;font-size:0.85em;">'
                f'<code style="font-size:0.95em;">{escape(format_citation(row["cit"]))}</code> '
                f'{_criticality_pill(row["criticality"])} '
                f'{coverage_indicator_html(row["coverage"])}<br>'
                f'<span style="color:#555;">{escape(_truncate(row["title"], 110))}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if not gap_rows:
            st.caption("No gaps — all assessed obligations are fully covered.")

    st.markdown("---")

    # ── Row 3: Process (APQC) + Controls + Improvements specifics ────────────
    pcol, ctrlcol, impcol = st.columns(3)

    # Process (APQC) specifics
    with pcol:
        st.markdown("### Process coverage")
        all_mappings = payload.get("obligation_mappings", []) or []
        proc_obligation_count: dict[tuple[str, str], set[str]] = defaultdict(set)
        for m in all_mappings:
            key = (m.get("apqc_hierarchy_id", ""), m.get("apqc_process_name", ""))
            proc_obligation_count[key].add(m.get("citation", ""))
        unique_processes = len(proc_obligation_count)
        rel_counter: dict[str, int] = defaultdict(int)
        for m in all_mappings:
            rel_counter[m.get("relationship_type", "")] += 1

        m1, m2 = st.columns(2)
        m1.metric("Unique APQC processes", unique_processes)
        m2.metric("Total mappings", len(all_mappings))

        st.markdown("**Most-targeted processes**")
        top_procs = sorted(proc_obligation_count.items(),
                           key=lambda kv: -len(kv[1]))[:5]
        for (apqc_id, name), cits in top_procs:
            st.markdown(
                _list_item(
                    f'<code>{escape(apqc_id)}</code> {escape(_truncate(name, 50))}',
                    f'{len(cits)} oblig.',
                ),
                unsafe_allow_html=True,
            )

        st.markdown("**Relationship types**")
        for rel, n in sorted(rel_counter.items(), key=lambda kv: -kv[1]):
            st.markdown(
                _list_item(escape(rel or "—"), f"{n}"),
                unsafe_allow_html=True,
            )

    # Controls specifics
    with ctrlcol:
        st.markdown("### Controls coverage")
        all_assessments = payload.get("coverage_assessments", []) or []
        used_control_ids = {a.get("control_id") for a in all_assessments if a.get("control_id")}
        controls_by_id = idx["controls_by_id"]

        # Coverage outcome counts at the (obligation × APQC × control) level
        outcome_counter: dict[str, int] = defaultdict(int)
        for a in all_assessments:
            outcome_counter[a.get("overall_coverage", "Not Covered")] += 1

        # Controls grouped by business unit
        bu_counter: dict[str, int] = defaultdict(int)
        for cid in used_control_ids:
            c = controls_by_id.get(cid)
            if c:
                bu_counter[c.get("business_unit_name", "—")] += 1

        m1, m2 = st.columns(2)
        m1.metric("Distinct linked controls", len(used_control_ids))
        m2.metric("Coverage decisions", len(all_assessments))

        st.markdown("**Assessment outcomes**")
        for status in ("Covered", "Partially Covered", "Not Covered"):
            st.markdown(
                _list_item(
                    coverage_indicator_html(status),
                    f"{outcome_counter.get(status, 0)}",
                ),
                unsafe_allow_html=True,
            )

        st.markdown("**Owning business units**")
        for bu, n in sorted(bu_counter.items(), key=lambda kv: -kv[1])[:5]:
            st.markdown(
                _list_item(escape(_truncate(bu, 40)), f"{n} ctrls"),
                unsafe_allow_html=True,
            )
        if not bu_counter:
            st.caption("No linked controls resolved.")

    # Proposed improvements specifics
    with impcol:
        st.markdown("### Proposed control suggestions")
        all_imp = payload.get("proposed_improvements", []) or []
        change_counter: dict[str, int] = defaultdict(int)
        owner_counter: dict[str, int] = defaultdict(int)
        type_counter: dict[str, int] = defaultdict(int)
        cits_with_imp = {imp.get("source_citation", "") for imp in all_imp}
        for imp in all_imp:
            ct = (imp.get("change_type") or "").lower() or "change"
            # Normalise 'enhanced' → 'enhancement'
            if ct == "enhanced":
                ct = "enhancement"
            change_counter[ct] += 1
            pc = imp.get("proposed_control", {}) or {}
            owner_counter[pc.get("who", "—")] += 1
            type_counter[pc.get("selected_level_1", "—")] += 1

        m1, m2 = st.columns(2)
        m1.metric("Total suggestions", len(all_imp))
        m2.metric("Obligations addressed", len(cits_with_imp))

        st.markdown("**Change type**")
        for ct, n in sorted(change_counter.items(), key=lambda kv: -kv[1]):
            st.markdown(
                _list_item(_change_pill(ct), f"{n}"),
                unsafe_allow_html=True,
            )

        st.markdown("**Control type**")
        for tp, n in sorted(type_counter.items(), key=lambda kv: -kv[1])[:4]:
            st.markdown(
                _list_item(escape(tp), f"{n}"),
                unsafe_allow_html=True,
            )

        st.markdown("**Most-proposed owners**")
        for owner, n in sorted(owner_counter.items(), key=lambda kv: -kv[1])[:5]:
            st.markdown(
                _list_item(escape(_truncate(owner, 40)), f"{n}"),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Row 4: Top residual risks (kept from previous design) ────────────────
    st.markdown("### Top residual risks")
    all_risks = list(payload.get("scored_risks", []) or [])
    all_risks.sort(key=lambda r: (
        _RISK_RANK.get(r.get("inherent_risk_rating", ""), 4),
        -int(r.get("impact_rating", 0) or 0),
        -int(r.get("frequency_rating", 0) or 0),
    ))
    if not all_risks:
        st.caption("No scored risks found in this checkpoint.")
    else:
        rcols = st.columns(2)
        for i, r in enumerate(all_risks[:6]):
            with rcols[i % 2]:
                st.markdown(
                    f'<div style="padding:6px 10px;margin-bottom:4px;background:#fafafa;'
                    f'border-left:3px solid #c62828;border-radius:4px;font-size:0.85em;">'
                    f'<code style="font-size:0.95em;">{escape(format_citation(r.get("source_citation", "")))}</code> '
                    f'{risk_score_badge_html(r.get("inherent_risk_rating", "Low"))} '
                    f'<span style="color:#666;font-size:0.9em;">'
                    f'I{r.get("impact_rating", "?")}·F{r.get("frequency_rating", "?")} · '
                    f'{escape(r.get("risk_category", ""))}</span><br>'
                    f'<span style="color:#555;">{escape(_truncate(r.get("risk_description", ""), 160))}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ── Per-obligation card ───────────────────────────────────────────────────────
_RISK_CAT_COLOR = {
    "Compliance Risk": "#c62828",
    "Strategic Risk": "#6a1b9a",
    "Operational Risk": "#1565c0",
    "Reputational Risk": "#ef6c00",
    "Liquidity Risk": "#00695c",
    "Credit Risk": "#4e342e",
    "Market Risk": "#283593",
}


def _scroll_box(html: str, max_h: int = 200) -> str:
    return (f'<div style="max-height:{max_h}px;overflow-y:auto;'
            f'background:#fafbfc;border:1px solid #e7eaee;border-radius:6px;'
            f'padding:10px 14px;font-size:0.9em;line-height:1.5;color:#222;">{html}</div>')


def _render_obligation_card(cit: str, idx: dict[str, Any]) -> None:
    ob = idx["obligations_by_cit"].get(cit, {})
    title = ob.get("section_title") or ob.get("title_level_3") or "(untitled)"
    criticality = ob.get("criticality_tier", "Low")
    category = ob.get("obligation_category", "")
    coverage = idx["coverage_by_cit"].get(cit, "Not Assessed")
    max_risk = idx["max_risk_by_cit"].get(cit, "")

    mappings = idx["mappings_by_cit"].get(cit, [])
    assessments = idx["assessments_by_cit"].get(cit, [])
    risks = idx["risks_by_cit"].get(cit, [])
    improvements = idx["improvements_by_cit"].get(cit, [])

    # Header for the expander label (plain text — Streamlit expander labels don't render HTML)
    cov_emoji = {"Covered": "✅", "Partially Covered": "⚠️", "Not Covered": "❌"}.get(coverage, "·")
    crit_emoji = {"High": "🔴", "Medium": "🟡", "Low": "⚪"}.get(criticality, "·")
    risk_text = f" · {max_risk} risk" if max_risk else ""
    header = (f"{crit_emoji} {format_citation(cit)} — {title}  "
              f"({criticality} · {cov_emoji} {coverage}{risk_text})")

    with st.expander(header, expanded=False):
        # ── Top metadata bar: badges + per-obligation mini stats ─────────────
        badges = [
            _category_pill(category),
            _criticality_pill(criticality),
            coverage_indicator_html(coverage),
        ]
        if max_risk:
            badges.append(risk_score_badge_html(max_risk))

        breadcrumb_parts = [
            ob.get("subpart", ""),
            ob.get("title_level_2", ""),
            ob.get("title_level_3", ""),
            ob.get("title_level_4", ""),
        ]
        breadcrumb = " › ".join(escape(p) for p in breadcrumb_parts if p)

        st.markdown(
            '<div style="display:flex;justify-content:space-between;align-items:center;'
            'flex-wrap:wrap;gap:10px;margin-bottom:8px;">'
            f'<div style="display:flex;gap:6px;flex-wrap:wrap;">{" ".join(badges)}</div>'
            f'<div style="font-size:0.78em;color:#777;">'
            f'📋 {len(mappings)} mappings · 🔧 {len(assessments)} assessments · '
            f'⚠️ {len(risks)} risks · 💡 {len(improvements)} improvements'
            f'</div></div>'
            f'<div style="font-size:0.78em;color:#777;margin-bottom:10px;">{breadcrumb}</div>',
            unsafe_allow_html=True,
        )

        # ── Obligation text (full, scrollable) ───────────────────────────────
        render_section_header("Regulatory text")
        text = ob.get("text", "")
        st.markdown(_scroll_box(escape(text), max_h=220), unsafe_allow_html=True)

        # Classification rationale + meta
        rationale = ob.get("classification_rationale", "")
        link = ob.get("link", "")
        applicability = ob.get("applicability", "") or "—"
        status_text = ob.get("status", "—")
        meta_chips = (
            f'<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:0.82em;'
            f'color:#555;margin-top:8px;">'
            f'<span><b>Status:</b> {escape(str(status_text))}</span>'
            f'<span><b>Applies to:</b> {escape(str(applicability))}</span>'
        )
        if link:
            meta_chips += f'<span><a href="{escape(link)}" target="_blank">eCFR source ↗</a></span>'
        meta_chips += '</div>'
        st.markdown(meta_chips, unsafe_allow_html=True)

        if rationale:
            st.markdown(
                f'<div style="margin-top:10px;padding:8px 12px;background:#fffbea;'
                f'border-left:3px solid #f9a825;border-radius:4px;font-size:0.85em;color:#5d4d10;">'
                f'<b>Why this {escape(criticality)} {escape(category)}?</b> '
                f'{escape(rationale)}</div>',
                unsafe_allow_html=True,
            )

        # ── Two-column: process+controls (left), risks+improvements (right) ──
        col_left, col_right = st.columns([3, 2], gap="large")

        with col_left:
            # APQC mappings
            render_section_header("APQC process mapping",
                                  len(mappings) or None, accent="#1565c0")
            if mappings:
                rows = []
                for m in mappings:
                    rows.append({
                        "APQC ID": m.get("apqc_hierarchy_id", ""),
                        "Process": m.get("apqc_process_name", ""),
                        "Relationship": m.get("relationship_type", ""),
                        "Detail": _truncate(m.get("relationship_detail", ""), 140),
                        "Conf.": f"{float(m.get('confidence', 0)) * 100:.0f}%",
                    })
                render_premium_table(
                    pd.DataFrame(rows),
                    code_cols=["APQC ID"],
                    numeric_cols=["Conf."],
                    truncate_cols=["Detail"],
                    height=300,
                )
            else:
                st.caption("No APQC mappings (informational obligation).")

            # Coverage assessments
            render_section_header("Control coverage",
                                  len(assessments) or None, accent="#2e7d32")
            if assessments:
                control_ids_seen: list[str] = []
                seen_set: set[str] = set()
                for a in assessments:
                    status = a.get("overall_coverage", "Not Covered")
                    cid = a.get("control_id") or "—"
                    apqc_id = a.get("apqc_hierarchy_id", "")
                    sem = a.get("semantic_rationale") or ""
                    rel = a.get("relationship_rationale") or ""
                    sem_match = a.get("semantic_match", "")
                    rel_match = a.get("relationship_match", "")

                    st.markdown(
                        f'<div style="border:1px solid #e0e0e0;border-radius:6px;'
                        f'padding:10px 14px;margin-bottom:8px;background:#fff;">'
                        f'<div style="display:flex;gap:10px;align-items:center;'
                        f'flex-wrap:wrap;font-size:0.85em;margin-bottom:6px;">'
                        f'<code style="background:#eef;padding:1px 6px;border-radius:3px;">{escape(apqc_id)}</code>'
                        f'<span style="color:#888;">→</span>'
                        f'<code style="background:#efe;padding:1px 6px;border-radius:3px;">{escape(cid)}</code>'
                        f'{coverage_indicator_html(status)}'
                        f'</div>'
                        f'<div style="font-size:0.82em;color:#444;">'
                        f'<b>Semantic match ({escape(sem_match)}):</b> {escape(sem)}'
                        f'</div>'
                        f'<div style="font-size:0.82em;color:#444;margin-top:4px;">'
                        f'<b>Relationship match ({escape(rel_match)}):</b> {escape(rel)}'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if a.get("control_id") and a["control_id"] not in seen_set:
                        seen_set.add(a["control_id"])
                        control_ids_seen.append(a["control_id"])

                # Linked controls (full detail)
                controls_by_id = idx["controls_by_id"]
                resolved = [controls_by_id[c] for c in control_ids_seen if c in controls_by_id]
                if resolved:
                    render_section_header("Linked controls (detail)", len(resolved),
                                          accent="#00695c")
                    for c in resolved:
                        ctype = c.get("selected_level_1", "—")
                        cmethod = c.get("selected_level_2", "")
                        st.markdown(
                            f'<div style="border-left:3px solid #00695c;background:#f5fbf9;'
                            f'padding:8px 12px;margin-bottom:6px;border-radius:4px;font-size:0.85em;">'
                            f'<div style="font-weight:600;color:#1a3d35;">'
                            f'<code>{escape(c.get("control_id", ""))}</code> '
                            f'· {escape(c.get("leaf_name", ""))}</div>'
                            f'<div style="color:#444;margin-top:3px;">'
                            f'<b>Owner:</b> {escape(c.get("who", "—"))} · '
                            f'<b>BU:</b> {escape(c.get("business_unit_name", "—"))} · '
                            f'<b>Type:</b> {escape(ctype)} / {escape(cmethod)} · '
                            f'<b>Frequency:</b> {escape(c.get("frequency", "—"))} · '
                            f'<b>Quality:</b> {escape(c.get("quality_rating", "—"))}'
                            f'</div>'
                            f'<div style="color:#333;margin-top:4px;">'
                            f'{escape(_truncate(c.get("full_description", ""), 320))}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.caption("Not assessed.")

        with col_right:
            # Risks grouped by category
            render_section_header("Residual risks",
                                  len(risks) or None, accent="#c62828")
            if risks:
                grouped: dict[str, list[dict]] = defaultdict(list)
                for r in risks:
                    grouped[r.get("risk_category", "Other")].append(r)
                # Sort categories by worst rating first
                cat_order = sorted(
                    grouped.keys(),
                    key=lambda k: min(_RISK_RANK.get(r.get("inherent_risk_rating", ""), 4)
                                      for r in grouped[k]),
                )
                for cat in cat_order:
                    cat_color = _RISK_CAT_COLOR.get(cat, "#555")
                    st.markdown(
                        f'<div style="font-size:0.78em;color:{cat_color};font-weight:600;'
                        f'text-transform:uppercase;letter-spacing:0.03em;'
                        f'margin:8px 0 4px 0;">{escape(cat)} ({len(grouped[cat])})</div>',
                        unsafe_allow_html=True,
                    )
                    for r in grouped[cat]:
                        impact = r.get("impact_rating", "?")
                        freq = r.get("frequency_rating", "?")
                        impact_rat = r.get("impact_rationale", "")
                        freq_rat = r.get("frequency_rationale", "")
                        sub_cat = r.get("sub_risk_category", "")
                        st.markdown(
                            f'<div style="border-left:3px solid {cat_color};background:#fff7f7;'
                            f'padding:8px 12px;margin-bottom:6px;border-radius:4px;font-size:0.83em;">'
                            f'<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">'
                            f'{risk_score_badge_html(r.get("inherent_risk_rating", "Low"))} '
                            f'<span style="color:#555;">'
                            f'I{impact}·F{freq}'
                            f'{" · " + escape(sub_cat) if sub_cat else ""}</span></div>'
                            f'<div style="margin-top:5px;color:#222;">'
                            f'{escape(r.get("risk_description", ""))}</div>'
                            f'<div style="margin-top:5px;color:#555;font-size:0.92em;">'
                            f'<b>Impact ({impact}):</b> {escape(_truncate(impact_rat, 220))}</div>'
                            f'<div style="margin-top:3px;color:#555;font-size:0.92em;">'
                            f'<b>Frequency ({freq}):</b> {escape(_truncate(freq_rat, 220))}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.caption("No scored risks.")

            # Improvements (full detail)
            render_section_header("Proposed improvements",
                                  len(improvements) or None, accent="#1565c0")
            if improvements:
                for imp in improvements:
                    pc = imp.get("proposed_control", {}) or {}
                    st.markdown(
                        f'<div style="border:1px solid #d0e0f0;background:#f0f7ff;'
                        f'padding:10px 14px;margin-bottom:8px;border-radius:6px;font-size:0.85em;">'
                        f'<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
                        f'margin-bottom:5px;">'
                        f'{_change_pill(imp.get("change_type", ""))}'
                        f'<code style="background:#dde7f3;padding:1px 5px;border-radius:3px;">'
                        f'{escape(pc.get("control_id", ""))}</code>'
                        f'<b style="color:#0d3b66;">{escape(pc.get("leaf_name", ""))}</b></div>'
                        f'<div style="color:#444;margin-bottom:6px;">'
                        f'<b>Owner:</b> {escape(pc.get("who", "—"))} · '
                        f'<b>BU:</b> {escape(pc.get("business_unit_name", "—"))} · '
                        f'<b>Type:</b> {escape(pc.get("selected_level_1", "—"))} / '
                        f'{escape(pc.get("selected_level_2", ""))}'
                        f'</div>'
                        f'<div style="color:#444;margin-bottom:4px;">'
                        f'<b>When:</b> {escape(pc.get("when", "—"))} · '
                        f'<b>Frequency:</b> {escape(pc.get("frequency", "—"))}</div>'
                        f'<div style="color:#222;margin-top:6px;">'
                        f'<b>Description.</b> {escape(pc.get("full_description", ""))}</div>'
                        f'<div style="color:#333;margin-top:6px;">'
                        f'<b>Evidence.</b> {escape(pc.get("evidence", ""))}</div>'
                        f'<div style="color:#333;margin-top:6px;background:#e8f0fa;'
                        f'padding:6px 10px;border-radius:4px;">'
                        f'<b>Gap addressed.</b> {escape(imp.get("gap_addressed", ""))}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No proposed improvements.")


# ── Main render entry point ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _checkpoint_meta(path: str, mtime: float) -> dict[str, Any]:
    """Read just the `_meta` block from a checkpoint quickly."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("_meta", {}) or {}
    except Exception:
        return {}


def render_executive_tab() -> None:
    """Render the Executive View tab."""
    render_page_header(
        "Executive Dashboard",
        caption=("Final, executive-facing view of all assessed obligations across the loaded "
                 "regulation. Browse, filter and drill into each obligation, then read the "
                 "roll-up summary at the bottom."),
        icon="👔",
    )

    files = _list_assessment_checkpoints()
    if not files:
        st.warning(
            "No Improved/Patched Full Assessment checkpoint found in `data/checkpoints/`. "
            "Run the pipeline (Tabs 1–3) and apply the patch script first."
        )
        return

    # ── Data source picker ───────────────────────────────────────────────────
    render_section_header("Data source", accent="#1f4e79", icon="📂")

    def _fmt(i: int) -> str:
        p = files[i]
        m = _checkpoint_meta(str(p), p.stat().st_mtime)
        reg = m.get("regulation_name", "—")
        n = m.get("obligation_count", "?")
        ts = m.get("improvement_timestamp") or m.get("timestamp") or "—"
        return f"{reg} · {n} obligations · {ts}  ·  {p.name}"

    pick = st.selectbox(
        "Assessment checkpoint",
        options=list(range(len(files))),
        format_func=_fmt,
        index=0,
        key="exec_checkpoint_pick",
        label_visibility="collapsed",
    )
    chosen = files[pick]

    try:
        idx = _index_data(str(chosen), chosen.stat().st_mtime)
    except Exception as e:
        st.error(f"Failed to load checkpoint: {e}")
        _log.exception("Failed to load %s", chosen)
        return
    idx["_source_path"] = str(chosen)

    meta = idx["payload"].get("_meta", {})
    size_mb = chosen.stat().st_size / (1024 * 1024)
    render_metadata_strip([
        ("Regulation", meta.get("regulation_name", "—")),
        ("Pipeline", meta.get("stage_label", meta.get("stage", "—"))),
        ("LLM mode", meta.get("llm_mode", "—")),
        ("Patched", meta.get("patched", False)),
        ("Improvements", meta.get("improvements_count", 0)),
        ("Pipeline run", meta.get("timestamp", "—")),
        ("Improvements applied", meta.get("improvement_timestamp", "—")),
        ("File", f"{chosen.name} ({size_mb:.1f} MB)"),
    ])

    st.markdown("")
    _render_top_banner(idx)
    st.markdown("---")

    # ── Filter / sort bar ────────────────────────────────────────────────────
    citations = idx["ordered_citations"]
    obligations_by_cit = idx["obligations_by_cit"]

    all_criticalities = ["High", "Medium", "Low"]
    all_categories = sorted({obligations_by_cit[c].get("obligation_category", "")
                             for c in citations if c in obligations_by_cit})

    f1, f2, f3 = st.columns([2, 2, 2])
    sel_crit = f1.multiselect("Criticality", all_criticalities,
                              default=all_criticalities, key="exec_filter_crit")
    sel_cat = f2.multiselect("Category", all_categories,
                             default=all_categories, key="exec_filter_cat")
    sort_mode = f3.selectbox(
        "Sort by",
        ["Risk (highest first)", "Criticality (highest first)", "Citation (A–Z)"],
        key="exec_sort_mode",
    )

    # Apply filters
    visible = [
        c for c in citations
        if obligations_by_cit.get(c, {}).get("criticality_tier", "Low") in sel_crit
        and obligations_by_cit.get(c, {}).get("obligation_category", "") in sel_cat
    ]

    # Apply sort
    if sort_mode.startswith("Risk"):
        visible.sort(key=lambda c: (
            _RISK_RANK.get(idx["max_risk_by_cit"].get(c, ""), 4),
            _COVERAGE_RANK.get(idx["coverage_by_cit"].get(c, "Covered"), 3),
            _CRITICALITY_RANK.get(obligations_by_cit.get(c, {}).get("criticality_tier", "Low"), 3),
        ))
    elif sort_mode.startswith("Criticality"):
        visible.sort(key=lambda c: (
            _CRITICALITY_RANK.get(obligations_by_cit.get(c, {}).get("criticality_tier", "Low"), 3),
            _RISK_RANK.get(idx["max_risk_by_cit"].get(c, ""), 4),
        ))
    # else: keep natural citation order

    st.markdown(f"**Showing {len(visible)} of {len(citations)} obligations**")

    if not visible:
        st.info("No obligations match the current filters.")
        return

    for cit in visible:
        _render_obligation_card(cit, idx)

    st.markdown("---")
    _render_summary(idx)
