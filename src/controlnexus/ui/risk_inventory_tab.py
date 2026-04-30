"""Risk Inventory Builder Streamlit tab."""

from __future__ import annotations

import html
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
import yaml  # type: ignore[import-untyped]

from controlnexus.analysis.ingest import ingest_excel
from controlnexus.risk_inventory.demo import default_demo_fixture_path, load_demo_risk_inventory
from controlnexus.risk_inventory.document_ingest import DocumentAnalysis, analyze_process_document
from controlnexus.risk_inventory.export import risk_inventory_excel_bytes
from controlnexus.risk_inventory.graph import build_risk_inventory_graph
from controlnexus.risk_inventory.models import RiskInventoryRecord, RiskInventoryRun


def render_risk_inventory_tab() -> None:
    """Render the full Risk Inventory Builder experience."""
    _inject_risk_inventory_css()
    header_left, header_right = st.columns([5, 1.35])
    with header_left:
        st.markdown(
            """
            <section class="ri-hero">
                <div class="ri-eyebrow">Risk Inventory Builder</div>
                <h1>Convert process evidence into a risk inventory</h1>
                <p>
                    Ingest policy and procedure documents, infer process context, create risk records,
                    map controls, calculate residual exposure, and export a review-ready workbook.
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with header_right:
        st.markdown('<div class="ri-toggle-panel">', unsafe_allow_html=True)
        demo_enabled = st.toggle(
            "Demo Mode",
            value=bool(st.session_state.get("demo_mode", False)),
            key="demo_mode",
            help="Use deterministic Payment Exception Handling sample data.",
        )
        st.caption("No LLM credentials required.")
        st.markdown("</div>", unsafe_allow_html=True)

    run: RiskInventoryRun | None
    if demo_enabled:
        if "risk_inventory_demo_run" not in st.session_state:
            st.session_state["risk_inventory_demo_run"] = load_demo_risk_inventory().model_dump()
        run = RiskInventoryRun.model_validate(st.session_state["risk_inventory_demo_run"])
        st.markdown(
            '<div class="ri-notice">Demo Mode: deterministic Payment Exception Handling sample data is loaded.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.session_state.pop("risk_inventory_demo_run", None)
        user_run = st.session_state.get("risk_inventory_user_run")
        run = RiskInventoryRun.model_validate(user_run) if user_run else None

    tabs = st.tabs(
        [
            "Overview",
            "Input / Upload",
            "Risk Inventory",
            "Inherent Risk",
            "Control Mapping",
            "Residual Risk",
            "Review & Challenge",
            "Executive Report",
            "Debug / Agent Trace",
        ]
    )

    with tabs[0]:
        _render_overview(run) if run else _render_empty_state()
    with tabs[1]:
        if demo_enabled and run:
            _render_inputs(run)
        else:
            _render_input_and_maybe_run()
    with tabs[2]:
        _render_risk_inventory(run) if run else _render_empty_panel("Risk records will appear after you run the workflow.")
    with tabs[3]:
        _render_inherent(run) if run else _render_empty_panel("Inherent risk scores will appear after inventory creation.")
    with tabs[4]:
        _render_control_mapping(run) if run else _render_empty_panel("Control mappings will appear after inventory creation.")
    with tabs[5]:
        _render_residual(run) if run else _render_empty_panel("Residual ratings will appear after inventory creation.")
    with tabs[6]:
        _render_review(run) if run else _render_empty_panel("Review and challenge prompts will appear here.")
    with tabs[7]:
        _render_executive(run) if run else _render_empty_panel("Executive summary will appear here.")
    with tabs[8]:
        _render_debug(run) if run else _render_empty_panel("Run manifest and validation details will appear here.")


def _render_input_and_maybe_run() -> RiskInventoryRun | None:
    st.markdown('<div class="ri-section-title">1. Ingest Policy / Procedure Evidence</div>', unsafe_allow_html=True)
    st.caption("Upload a PDF, TXT, or Markdown procedure. The builder extracts process context and analysis cues.")

    analysis = _document_upload()
    structured_context = _structured_context_upload()
    controls = _control_upload()
    defaults = _context_defaults(analysis, structured_context)

    st.markdown('<div class="ri-section-title">2. Review Extracted Context</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.1, 1, 1])
    with c1:
        process_name = st.text_input("Process Name", value=str(defaults["process_name"]), key="ri_process_name")
        process_id = st.text_input("Process ID", value=str(defaults["process_id"]), key="ri_process_id")
    with c2:
        product = st.text_input("Product / Service", value=str(defaults["product"]), key="ri_product")
        business_unit = st.text_input("Business Unit", value=str(defaults["business_unit"]), key="ri_bu")
    with c3:
        max_risks = st.slider("Risk categories to evaluate", min_value=3, max_value=12, value=8, step=1)

    systems_default = "\n".join(defaults["systems"]) if isinstance(defaults["systems"], list) else str(defaults["systems"])
    stakeholders_default = (
        "\n".join(defaults["stakeholders"]) if isinstance(defaults["stakeholders"], list) else str(defaults["stakeholders"])
    )
    s1, s2 = st.columns(2)
    with s1:
        systems = st.text_area("Systems / Applications", value=systems_default, height=110, key="ri_systems")
    with s2:
        stakeholders = st.text_area("Stakeholders / Reviewers", value=stakeholders_default, height=110, key="ri_stakeholders")

    description = st.text_area(
        "Process Narrative Used For Analysis",
        value=str(defaults["description"]),
        height=180,
        key="ri_description",
    )

    if analysis:
        _render_document_analysis(analysis)
    _render_control_preview(controls)

    st.markdown('<div class="ri-section-title">3. Run Deterministic Workflow</div>', unsafe_allow_html=True)
    run_cols = st.columns([2, 1])
    with run_cols[0]:
        st.write("The graph will apply taxonomy matching, draft risk records, map controls, and calculate scores.")
    with run_cols[1]:
        run_clicked = st.button("Run Risk Inventory Workflow", type="primary", width="stretch", key="ri_run")

    if run_clicked:
        process_context = {
            "process_id": process_id,
            "process_name": process_name,
            "product": product,
            "business_unit": business_unit,
            "description": description,
            "systems": [line.strip() for line in systems.splitlines() if line.strip()],
            "stakeholders": [line.strip() for line in stakeholders.splitlines() if line.strip()],
            "source_documents": [analysis.filename] if analysis else [],
        }
        with st.status("Building risk inventory...", expanded=True) as status:
            status.write("Loaded process context and control inventory.")
            graph = build_risk_inventory_graph().compile()
            result = graph.invoke(
                {
                    "run_id": f"RI-USER-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    "tenant_id": "user-workspace",
                    "process_context": process_context,
                    "control_inventory": controls,
                    "max_risks": max_risks,
                },
                config={"recursion_limit": 200},
            )
            status.write("Calculated inherent risk, control environment, and residual risk.")
            st.session_state["risk_inventory_user_run"] = result["final_report"]
            status.update(label="Risk inventory workflow complete.", state="complete")
        st.rerun()

    data = st.session_state.get("risk_inventory_user_run")
    return RiskInventoryRun.model_validate(data) if data else None


def _document_upload() -> DocumentAnalysis | None:
    upload_col, sample_col = st.columns([2, 1])
    with upload_col:
        uploaded = st.file_uploader(
            "Upload process policy/procedure",
            type=["pdf", "txt", "md", "markdown"],
            key="ri_process_document_upload",
            help="PDF, TXT, or Markdown files are parsed locally and used to prefill process context.",
        )
    with sample_col:
        st.write("")
        st.write("")
        use_sample = st.button("Load sample procedure", width="stretch", key="ri_load_sample_doc")

    if use_sample:
        sample_path = default_demo_fixture_path().with_name("payment_exception_policy.md")
        analysis = analyze_process_document(sample_path.name, sample_path.read_bytes())
        st.session_state["risk_inventory_document_analysis"] = analysis.model_dump()
        st.session_state["ri_loaded_doc_name"] = analysis.filename
        _apply_analysis_to_widgets(analysis)

    if uploaded is not None:
        try:
            analysis = analyze_process_document(uploaded.name, uploaded.getvalue())
        except Exception as exc:  # noqa: BLE001 - user-facing upload parse error
            st.error(f"Could not parse document: {exc}")
            return None
        st.session_state["risk_inventory_document_analysis"] = analysis.model_dump()
        if st.session_state.get("ri_loaded_doc_name") != analysis.filename:
            st.session_state["ri_loaded_doc_name"] = analysis.filename
            _apply_analysis_to_widgets(analysis)

    raw = st.session_state.get("risk_inventory_document_analysis")
    return DocumentAnalysis.model_validate(raw) if raw else None


def _apply_analysis_to_widgets(analysis: DocumentAnalysis) -> None:
    context = analysis.process_context()
    st.session_state["ri_process_name"] = context["process_name"]
    st.session_state["ri_process_id"] = context["process_id"]
    st.session_state["ri_product"] = context["product"]
    st.session_state["ri_bu"] = context["business_unit"]
    st.session_state["ri_systems"] = "\n".join(context["systems"])
    st.session_state["ri_stakeholders"] = "\n".join(context["stakeholders"])
    st.session_state["ri_description"] = context["description"]


def _structured_context_upload() -> dict[str, Any]:
    with st.expander("Optional structured context upload (JSON/YAML)", expanded=False):
        uploaded = st.file_uploader(
            "Upload structured process context",
            type=["json", "yaml", "yml"],
            key="ri_process_context_upload",
        )
    if uploaded is None:
        return {}
    suffix = Path(uploaded.name).suffix.lower()
    raw_text = uploaded.getvalue().decode("utf-8")
    payload = json.loads(raw_text) if suffix == ".json" else yaml.safe_load(raw_text)
    return payload if isinstance(payload, dict) else {}


def _context_defaults(analysis: DocumentAnalysis | None, structured_context: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "process_id": "PROC-PAY-EXCEPTION",
        "process_name": "Payment Exception Handling",
        "product": "High-value payment processing",
        "business_unit": "Payment Operations",
        "description": (
            "Daily high-value payment exception workflow for investigation, approval, resolution, "
            "reconciliation, escalation, and incident reporting."
        ),
        "systems": ["Payment Exception Workflow", "Wire Transfer Platform"],
        "stakeholders": ["Payment Operations Manager", "Compliance Officer"],
    }
    if analysis:
        defaults.update(analysis.process_context())
    defaults.update({key: value for key, value in structured_context.items() if value})
    return defaults


def _control_upload() -> list[dict[str, Any]]:
    st.markdown('<div class="ri-section-title">Control Data</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    with c1:
        uploaded = st.file_uploader(
            "Upload existing controls",
            type=["xlsx", "xls", "json", "yaml", "yml"],
            key="ri_control_upload",
            help="Control register uploads can be Excel, JSON, or YAML.",
        )
    with c2:
        use_starter_controls = st.checkbox(
            "Use starter payment controls",
            value=uploaded is None,
            help="Use realistic sample controls when no control register is available.",
        )

    if uploaded is None:
        return _starter_controls() if use_starter_controls else []

    suffix = Path(uploaded.name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)
        try:
            return [
                {
                    "control_id": record.control_id,
                    "control_name": record.leaf_name or record.control_id,
                    "control_type": record.selected_level_2 or record.control_type,
                    "description": record.full_description,
                    "design_rating": "Satisfactory",
                    "operating_rating": "Satisfactory",
                }
                for record in ingest_excel(tmp_path)
            ]
        finally:
            tmp_path.unlink(missing_ok=True)

    raw_text = uploaded.getvalue().decode("utf-8")
    payload = json.loads(raw_text) if suffix == ".json" else yaml.safe_load(raw_text)
    if isinstance(payload, dict):
        payload = payload.get("controls", [])
    return list(payload or [])


def _starter_controls() -> list[dict[str, Any]]:
    payload = yaml.safe_load(default_demo_fixture_path().read_text(encoding="utf-8")) or {}
    return list(payload.get("controls", []))


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="ri-empty">
            <h3>Start with evidence, not a blank form</h3>
            <p>
                Go to Input / Upload and add a policy or procedure PDF. The app will extract process context,
                likely risk categories, control cues, obligations, and exposure signals before it runs the graph.
            </p>
            <div class="ri-flow">
                <span>Upload document</span><span>Analyze context</span><span>Create inventory</span>
                <span>Map controls</span><span>Review residual exposure</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_panel(message: str) -> None:
    st.markdown(f'<div class="ri-empty-small">{html.escape(message)}</div>', unsafe_allow_html=True)


def _render_overview(run: RiskInventoryRun) -> None:
    _render_summary_metrics(run)
    st.markdown('<div class="ri-flow">', unsafe_allow_html=True)
    for stage in [
        "Understand Process",
        "Identify Applicable Risks",
        "Assess Inherent Risk",
        "Map Controls",
        "Evaluate Controls",
        "Determine Residual Risk",
    ]:
        st.markdown(f"<span>{html.escape(stage)}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="ri-section-title">Executive Takeaway</div>', unsafe_allow_html=True)
        st.write(run.executive_summary.headline)
        for message in run.executive_summary.key_messages:
            st.markdown(f"- {message}")
    with right:
        st.markdown('<div class="ri-section-title">Residual Risk Distribution</div>', unsafe_allow_html=True)
        distribution = Counter(record.residual_risk.residual_rating.value for record in run.records)
        st.dataframe(
            [{"Rating": rating, "Count": distribution.get(rating, 0)} for rating in ["Low", "Medium", "High", "Critical"]],
            hide_index=True,
            width="stretch",
        )
        _download_export(run, "overview")

    st.markdown('<div class="ri-section-title">Top Risk Records</div>', unsafe_allow_html=True)
    for record in sorted(run.records, key=lambda r: r.residual_risk.residual_score, reverse=True)[:4]:
        _render_compact_risk_card(record)


def _render_inputs(run: RiskInventoryRun) -> None:
    st.markdown('<div class="ri-section-title">Process Context</div>', unsafe_allow_html=True)
    context = run.input_context
    st.markdown(
        f"""
        <div class="ri-detail-panel">
            <b>{html.escape(context.process_name)}</b><br>
            {html.escape(context.product)} · {html.escape(context.business_unit)}
            <p>{html.escape(context.description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(
        [
            {"Field": "Systems", "Value": "\n".join(context.systems)},
            {"Field": "Stakeholders", "Value": "\n".join(context.stakeholders)},
            {"Field": "Source Documents", "Value": "\n".join(context.source_documents)},
        ],
        hide_index=True,
        width="stretch",
    )


def _render_risk_inventory(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_inventory_select")
    _render_risk_header(record)
    cols = st.columns([1, 1])
    with cols[0]:
        st.markdown('<div class="ri-section-title">Applicability</div>', unsafe_allow_html=True)
        _render_fact_block(
            {
                "Materializes": "Yes" if record.applicability.materializes else "No",
                "Type": record.applicability.materialization_type.value,
                "Confidence": f"{record.applicability.confidence:.0%}",
            }
        )
        st.write(record.applicability.rationale)
    with cols[1]:
        st.markdown('<div class="ri-section-title">Risk Statement</div>', unsafe_allow_html=True)
        st.write(record.risk_statement.risk_description)
        _render_chip_group("Root causes", record.risk_statement.causes)
        _render_chip_group("Consequences", record.risk_statement.consequences)

    with st.expander("Exposure metrics", expanded=True):
        st.dataframe(
            [
                {
                    "Metric": metric.metric_name,
                    "Value": metric.metric_value,
                    "Source": metric.source,
                    "Supports": ", ".join(metric.supports),
                }
                for metric in record.exposure_metrics
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("All risk records", expanded=False):
        st.dataframe(_risk_rows(run), hide_index=True, width="stretch")


def _render_inherent(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_inherent_select")
    _render_risk_header(record)
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall Impact", int(record.impact_assessment.overall_impact_score))
    c2.metric("Likelihood", int(record.likelihood_assessment.likelihood_score))
    c3.markdown(_rating_html(record.inherent_risk.inherent_label), unsafe_allow_html=True)

    st.markdown('<div class="ri-section-title">Impact Dimensions</div>', unsafe_allow_html=True)
    st.dataframe(
        [
            {
                "Dimension": item.dimension.value.replace("_", " ").title(),
                "Score": int(item.score),
                "Rationale": item.rationale,
            }
            for item in record.impact_assessment.dimensions
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown('<div class="ri-section-title">Likelihood Rationale</div>', unsafe_allow_html=True)
    st.write(record.likelihood_assessment.rationale)
    st.caption("Inherent risk is always calculated by the configured matrix, not invented by the model.")


def _render_control_mapping(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_mapping_select")
    _render_risk_header(record)
    if not record.control_mappings:
        st.warning("No controls are mapped to this risk. This is a coverage gap.")
        return
    for mapping in record.control_mappings:
        st.markdown(
            f"""
            <div class="ri-control-card">
                <div>
                    <b>{html.escape(mapping.control_name)}</b>
                    <span class="ri-muted"> · {html.escape(mapping.control_type)}</span>
                </div>
                <p>{html.escape(mapping.mitigation_rationale)}</p>
                <div>
                    {_badge("Coverage", mapping.coverage_assessment.title(), "neutral")}
                    {_badge("Design", mapping.design_effectiveness.rating.value if mapping.design_effectiveness else "Not Rated", "blue")}
                    {_badge("Operating", mapping.operating_effectiveness.rating.value if mapping.operating_effectiveness else "Not Rated", "teal")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with st.expander("All mapped controls", expanded=False):
        st.dataframe(_mapping_rows(run), hide_index=True, width="stretch")


def _render_residual(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_residual_select")
    _render_risk_header(record)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_rating_html(record.inherent_risk.inherent_label, "Inherent"), unsafe_allow_html=True)
    c2.markdown(
        _rating_html(record.control_environment.control_environment_rating.value, "Control Environment"),
        unsafe_allow_html=True,
    )
    c3.markdown(_rating_html(record.residual_risk.residual_label, "Residual"), unsafe_allow_html=True)
    c4.markdown(
        _rating_html(record.residual_risk.management_response.response_type.value.title(), "Response"),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ri-section-title">Residual Rationale</div>', unsafe_allow_html=True)
    st.write(record.residual_risk.rationale)
    st.markdown('<div class="ri-section-title">Recommended Action</div>', unsafe_allow_html=True)
    st.write(record.residual_risk.management_response.recommended_action)
    st.caption("Residual risk is calculated from inherent risk and control environment using the configured matrix.")


def _render_review(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_review_select")
    _render_risk_header(record)
    review = record.review_challenges[0] if record.review_challenges else None
    status_options = ["Not Started", "Pending Review", "Challenged", "Approved"]
    current_status = review.review_status.value if review else "Pending Review"
    st.selectbox(
        "Review Status",
        status_options,
        index=status_options.index(current_status) if current_status in status_options else 1,
        key=f"ri_review_status_{record.risk_id}",
    )
    st.text_area(
        "Challenge Comments",
        value=review.challenge_comments if review else "",
        height=120,
        key=f"ri_review_comments_{record.risk_id}",
        help="Capture business challenge comments before final approval.",
    )
    if review:
        _render_chip_group("Fields requiring review", review.challenged_fields)
    st.markdown('<div class="ri-section-title">Validation Findings</div>', unsafe_allow_html=True)
    findings = [finding for finding in run.validation_findings if finding.record_id == record.risk_id]
    if findings:
        st.dataframe([finding.model_dump() for finding in findings], hide_index=True, width="stretch")
    else:
        st.success("No validation findings for this record.")


def _render_executive(run: RiskInventoryRun) -> None:
    _render_summary_metrics(run)
    st.markdown('<div class="ri-section-title">Executive Summary</div>', unsafe_allow_html=True)
    st.write(run.executive_summary.headline)
    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("**Key Messages**")
        for message in run.executive_summary.key_messages:
            st.markdown(f"- {message}")
    with e2:
        st.markdown("**Top Residual Risks**")
        for risk in run.executive_summary.top_residual_risks or ["No Medium+ residual risks identified."]:
            st.markdown(f"- {risk}")
    with e3:
        st.markdown("**Recommended Actions**")
        for action in run.executive_summary.recommended_actions:
            st.markdown(f"- {action}")
    st.markdown('<div class="ri-section-title">Executive Risk Table</div>', unsafe_allow_html=True)
    st.dataframe(_risk_rows(run), hide_index=True, width="stretch")
    _download_export(run, "executive")


def _render_debug(run: RiskInventoryRun) -> None:
    st.markdown('<div class="ri-section-title">Agent Trace / Raw Output</div>', unsafe_allow_html=True)
    st.caption("Advanced view for validation, raw JSON, configuration snapshot, and run manifest.")
    st.json(run.run_manifest)
    st.json(run.model_dump())


def _render_document_analysis(analysis: DocumentAnalysis) -> None:
    st.markdown('<div class="ri-section-title">Document Analysis</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Words", analysis.document_stats.get("words", 0))
    m2.metric("Risk Cues", len(analysis.detected_risk_categories))
    m3.metric("Control Cues", len(analysis.detected_controls))
    m4.metric("Obligations", len(analysis.obligations))
    _render_chip_group("Detected risk categories", analysis.detected_risk_categories)
    _render_chip_group("Detected control cues", analysis.detected_controls)
    _render_chip_group("Exposure cues", analysis.exposure_cues)
    with st.expander("Detected obligations and extracted text", expanded=False):
        for obligation in analysis.obligations:
            st.markdown(f"- {obligation}")
        st.text_area("Extracted text preview", value=analysis.text[:5000], height=220, disabled=True)


def _render_control_preview(controls: list[dict[str, Any]]) -> None:
    st.caption(f"{len(controls)} controls will be available for mapping.")
    if controls:
        st.dataframe(
            [
                {
                    "Control ID": control.get("control_id", ""),
                    "Name": control.get("control_name", control.get("name", "")),
                    "Type": control.get("control_type", ""),
                    "Design": control.get("design_rating", "Satisfactory"),
                    "Operating": control.get("operating_rating", "Satisfactory"),
                }
                for control in controls
            ],
            hide_index=True,
            width="stretch",
        )


def _render_summary_metrics(run: RiskInventoryRun) -> None:
    high_plus = sum(record.residual_risk.residual_rating.value in {"High", "Critical"} for record in run.records)
    controls = sum(len(record.control_mappings) for record in run.records)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(_metric_card("Risks", str(len(run.records)), "blue"), unsafe_allow_html=True)
    m2.markdown(_metric_card("Materialized", str(len(run.materialized_records)), "green"), unsafe_allow_html=True)
    m3.markdown(_metric_card("Controls Linked", str(controls), "teal"), unsafe_allow_html=True)
    m4.markdown(_metric_card("High+ Residual", str(high_plus), "red" if high_plus else "green"), unsafe_allow_html=True)
    m5.markdown(_metric_card("Validation Flags", str(len(run.validation_findings)), "yellow"), unsafe_allow_html=True)


def _risk_selector(run: RiskInventoryRun, key: str) -> RiskInventoryRecord:
    options = [
        f"{record.risk_id} · {record.taxonomy_node.level_2_category} · {record.residual_risk.residual_label}"
        for record in run.records
    ]
    selected = st.selectbox("Select risk record", options, key=key)
    index = options.index(selected)
    return run.records[index]


def _render_risk_header(record: RiskInventoryRecord) -> None:
    st.markdown(
        f"""
        <div class="ri-risk-card">
            <div class="ri-risk-title">{html.escape(record.risk_id)} · {html.escape(record.taxonomy_node.level_2_category)}</div>
            <div class="ri-risk-desc">{html.escape(record.risk_statement.risk_description)}</div>
            <div>
                {_badge("Inherent", record.inherent_risk.inherent_label, _rating_class(record.inherent_risk.inherent_rating.value))}
                {_badge("Residual", record.residual_risk.residual_label, _rating_class(record.residual_risk.residual_rating.value))}
                {_badge("Response", record.residual_risk.management_response.response_type.value.title(), "neutral")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_compact_risk_card(record: RiskInventoryRecord) -> None:
    st.markdown(
        f"""
        <div class="ri-compact-risk">
            <div><b>{html.escape(record.taxonomy_node.level_2_category)}</b><br>
            <span class="ri-muted">{html.escape(record.risk_statement.risk_description[:180])}</span></div>
            <div>{_badge("Residual", record.residual_risk.residual_label, _rating_class(record.residual_risk.residual_rating.value))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_fact_block(values: dict[str, str]) -> None:
    st.markdown(
        '<div class="ri-fact-grid">'
        + "".join(
            f'<div><span>{html.escape(key)}</span><b>{html.escape(value)}</b></div>' for key, value in values.items()
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_chip_group(label: str, values: list[str]) -> None:
    if not values:
        return
    st.markdown(f"**{label}**")
    chips = " ".join(f'<span class="ri-chip">{html.escape(value)}</span>' for value in values[:12])
    st.markdown(chips, unsafe_allow_html=True)


def _download_export(run: RiskInventoryRun, location: str) -> None:
    st.download_button(
        "Download Excel Workbook",
        data=risk_inventory_excel_bytes(run),
        file_name=f"{run.run_id}_risk_inventory.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"ri_xlsx_{location}_{run.run_id}",
        width="stretch",
    )


def _risk_rows(run: RiskInventoryRun) -> list[dict[str, Any]]:
    return [
        {
            "Risk ID": record.risk_id,
            "Category": record.taxonomy_node.level_2_category,
            "Risk Description": record.risk_statement.risk_description,
            "Inherent": record.inherent_risk.inherent_label,
            "Control Environment": record.control_environment.control_environment_rating.value,
            "Residual": record.residual_risk.residual_label,
            "Management Response": record.residual_risk.management_response.response_type.value,
            "Linked Controls": len(record.control_mappings),
            "Demo": record.demo_record,
        }
        for record in run.records
    ]


def _mapping_rows(run: RiskInventoryRun) -> list[dict[str, Any]]:
    rows = []
    for record in run.records:
        for mapping in record.control_mappings:
            rows.append(
                {
                    "Risk ID": record.risk_id,
                    "Risk": record.taxonomy_node.level_2_category,
                    "Control": mapping.control_name,
                    "Type": mapping.control_type,
                    "Coverage": mapping.coverage_assessment,
                    "Rationale": mapping.mitigation_rationale,
                }
            )
    return rows


def _metric_card(label: str, value: str, tone: str) -> str:
    return (
        f'<div class="ri-metric ri-tone-{tone}"><span>{html.escape(label)}</span>'
        f"<b>{html.escape(value)}</b></div>"
    )


def _rating_html(label: str, title: str = "Rating") -> str:
    tone = _rating_class(label)
    return (
        f'<div class="ri-rating-tile ri-{tone}">'
        f"<span>{html.escape(title)}</span><b>{html.escape(label)}</b></div>"
    )


def _badge(label: str, value: str, tone: str) -> str:
    return f'<span class="ri-badge ri-{tone}">{html.escape(label)}: {html.escape(value)}</span>'


def _rating_class(value: str) -> str:
    lowered = value.lower()
    if "critical" in lowered or "inadequate" in lowered or "escalate" in lowered:
        return "critical"
    if "high" in lowered or "improvement" in lowered or "mitigate" in lowered:
        return "high"
    if "medium" in lowered or "satisfactory" in lowered or "monitor" in lowered:
        return "medium"
    if "low" in lowered or "strong" in lowered or "accept" in lowered:
        return "low"
    return "neutral"


def _inject_risk_inventory_css() -> None:
    st.markdown(
        """
        <style>
        .ri-hero {
            background: #f4f4f4;
            border-left: 4px solid #0f62fe;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
        }
        .ri-hero h1 {
            font-size: 1.85rem;
            margin: 0.15rem 0 0.35rem 0;
            line-height: 1.2;
        }
        .ri-hero p {
            color: #525252;
            margin: 0;
            max-width: 920px;
        }
        .ri-eyebrow, .ri-section-title {
            color: #0f62fe;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            text-transform: uppercase;
            margin: 1rem 0 0.35rem 0;
        }
        .ri-toggle-panel {
            background: #ffffff;
            border: 1px solid #c6c6c6;
            padding: 0.85rem;
            min-height: 112px;
        }
        .ri-notice {
            background: #e5f6ff;
            border-left: 4px solid #0072c3;
            padding: 0.7rem 0.9rem;
            margin-bottom: 0.8rem;
        }
        .ri-empty, .ri-empty-small {
            background: #f4f4f4;
            border: 1px solid #c6c6c6;
            padding: 1.1rem;
            margin-top: 0.75rem;
        }
        .ri-flow {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin: 0.7rem 0 1rem 0;
        }
        .ri-flow span {
            background: #edf5ff;
            border: 1px solid #78a9ff;
            color: #001d6c;
            padding: 0.45rem 0.65rem;
            font-size: 0.82rem;
        }
        .ri-metric {
            border: 1px solid #c6c6c6;
            background: #ffffff;
            padding: 0.85rem;
            min-height: 92px;
            border-top: 4px solid #0f62fe;
        }
        .ri-metric span, .ri-rating-tile span, .ri-fact-grid span {
            display: block;
            color: #525252;
            font-size: 0.75rem;
            text-transform: uppercase;
            font-weight: 600;
        }
        .ri-metric b {
            display: block;
            font-size: 1.8rem;
            margin-top: 0.2rem;
        }
        .ri-tone-green { border-top-color: #24a148; }
        .ri-tone-teal { border-top-color: #009d9a; }
        .ri-tone-red { border-top-color: #da1e28; }
        .ri-tone-yellow { border-top-color: #f1c21b; }
        .ri-risk-card, .ri-control-card, .ri-detail-panel, .ri-compact-risk {
            background: #ffffff;
            border: 1px solid #c6c6c6;
            padding: 0.9rem;
            margin: 0.55rem 0;
        }
        .ri-risk-card {
            border-left: 4px solid #0f62fe;
        }
        .ri-risk-title {
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .ri-risk-desc {
            color: #393939;
            margin-bottom: 0.65rem;
        }
        .ri-compact-risk {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
        }
        .ri-badge, .ri-chip {
            display: inline-block;
            padding: 0.22rem 0.48rem;
            margin: 0.12rem 0.18rem 0.12rem 0;
            font-size: 0.76rem;
            font-weight: 700;
            border-radius: 2px;
        }
        .ri-chip {
            background: #f4f4f4;
            border: 1px solid #c6c6c6;
            color: #393939;
            font-weight: 600;
        }
        .ri-low { background: #defbe6; color: #044317; }
        .ri-medium { background: #fff1c7; color: #684e00; }
        .ri-high { background: #ffd7d9; color: #750e13; }
        .ri-critical { background: #da1e28; color: #ffffff; }
        .ri-neutral { background: #e0e0e0; color: #161616; }
        .ri-blue { background: #d0e2ff; color: #001d6c; }
        .ri-teal { background: #9ef0f0; color: #003a3a; }
        .ri-muted {
            color: #6f6f6f;
        }
        .ri-rating-tile {
            border: 1px solid #c6c6c6;
            padding: 0.8rem;
            min-height: 92px;
        }
        .ri-rating-tile b {
            display: block;
            font-size: 1.25rem;
            margin-top: 0.35rem;
        }
        .ri-fact-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.5rem;
            margin-bottom: 0.75rem;
        }
        .ri-fact-grid div {
            background: #f4f4f4;
            border: 1px solid #e0e0e0;
            padding: 0.65rem;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid #c6c6c6;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
