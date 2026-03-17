"""File upload widget for controls Excel files."""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from controlnexus.analysis.ingest import ingest_excel

logger = logging.getLogger(__name__)


def render_upload_widget() -> None:
    """Render the file upload section and store ingested controls in session state."""
    st.markdown("### Upload Controls")
    st.info(
        "Upload an Excel file containing your control population. "
        "Sheets should be named `section_*` with 19-column headers."
    )

    uploaded_file = st.file_uploader(
        "Select Excel file",
        type=["xlsx", "xls"],
        key="controls_upload",
        help="Upload an .xlsx file with one sheet per section.",
    )

    if uploaded_file is not None:
        # Write to temp file so openpyxl can read it
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)

        try:
            controls = ingest_excel(tmp_path)
            st.session_state["controls"] = controls
            st.success(f"Ingested **{len(controls)}** control records from *{uploaded_file.name}*")

            # Preview
            with st.expander("Preview ingested controls", expanded=False):
                for ctrl in controls[:5]:
                    st.markdown(
                        f"- **{ctrl.control_id}** | {ctrl.selected_level_2} | {ctrl.who} | {ctrl.when}"
                    )
                if len(controls) > 5:
                    st.caption(f"... and {len(controls) - 5} more")
        except Exception as e:
            st.error(f"Failed to parse Excel file: {e}")
            logger.exception("Ingest error")
        finally:
            tmp_path.unlink(missing_ok=True)
