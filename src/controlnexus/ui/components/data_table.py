"""Reusable data-table component with column visibility toggling.

Provides a single ``render_data_table`` function that standardises how
tabular data is displayed throughout the ControlNexus UI.  Features:

* Column-visibility multi-select (users pick which columns to show)
* Snake-case → Title Case header mapping
* Optional CSV download button
* Full text wrapping via native HTML ``<table>`` (not canvas-based)
* Click-and-drag column resizing (edge-of-header drag)
* Key-based widget isolation so multiple tables coexist on one page

Usage::

    from controlnexus.ui.components.data_table import render_data_table

    render_data_table(
        records=[ctrl.to_export_dict() for ctrl in controls],
        default_columns=["control_id", "who", "when"],
        key="preview_controls",
    )
"""

from __future__ import annotations

import csv
import html as html_mod
import io
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _humanise(col: str) -> str:
    """Convert a ``snake_case`` column name to ``Title Case``."""
    return col.replace("_", " ").title()


# Columns whose values are typically long prose — these get a wider min-width.
_LONG_TEXT_COLUMNS = frozenset({
    "full_description", "what", "why", "evidence", "detail",
    "rationale", "context", "issue",
})


# ---------------------------------------------------------------------------
# HTML / CSS / JS for the table rendered inside an iframe
# ---------------------------------------------------------------------------

_TABLE_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin:0; padding:0; background:transparent; }

  .cn-table-wrap {
      width: 100%;
      overflow-x: auto;          /* horizontal scroll when table grows */
      /* NO overflow-y / max-height — iframe handles vertical scroll */
  }

  .cn-table {
      min-width: 100%;           /* can grow wider than viewport */
      border-collapse: collapse;
      font-family: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif;
      font-size: 0.85rem;
      /* starts as table-layout:auto so columns size naturally;
         JS switches to fixed after snapshotting widths */
  }

  .cn-table thead {
      position: sticky;
      top: 0;
      z-index: 2;
  }

  .cn-table th {
      background-color: #161616;
      color: #ffffff;
      font-weight: 600;
      text-align: left;
      padding: 0.6rem 0.75rem;
      white-space: nowrap;
      border-bottom: 2px solid #393939;
      font-size: 0.8rem;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      position: relative;          /* anchor for resize handle */
  }

  /* Resize handle — 8px invisible strip on right edge of header */
  .cn-table th .cn-rh {
      position: absolute;
      right: 0; top: 0; bottom: 0;
      width: 8px;
      cursor: col-resize;
      background: transparent;
      z-index: 3;
  }
  .cn-table th .cn-rh:hover { background: rgba(15,98,254,0.5); }
  .cn-table th .cn-rh.active { background: #0f62fe; }

  .cn-table td {
      padding: 0.55rem 0.75rem;
      border-bottom: 1px solid #e0e0e0;
      color: #161616;
      vertical-align: top;
      white-space: normal;
      word-wrap: break-word;
      overflow-wrap: break-word;
      line-height: 1.45;
  }

  .cn-table tr:nth-child(even) { background-color: #f4f4f4; }
  .cn-table tr:hover           { background-color: #e5e5e5; }

  /* Applied during drag to block text selection */
  .no-select { user-select: none !important; -webkit-user-select: none !important; }
</style>
"""

_RESIZE_JS = """
<script>
(function() {
    var table = document.querySelector('.cn-table');
    if (!table) return;

    var ths = Array.from(table.querySelectorAll('thead th'));

    // --- Phase 1 : snapshot auto-layout widths, then lock them -----------
    //  table-layout:auto sized columns to content.  We read those widths,
    //  set an explicit total table width, then switch to fixed layout.
    //  This ensures resizing one column doesn't redistribute space among
    //  siblings (which caused the cursor-jump bug).
    var totalW = 0;
    ths.forEach(function(th) {
        var w = th.offsetWidth;
        th.style.width = w + 'px';
        totalW += w;
    });
    table.style.width = totalW + 'px';
    table.style.minWidth = totalW + 'px';
    table.style.tableLayout = 'fixed';

    // --- Phase 2 : wire up each resize handle ----------------------------
    ths.forEach(function(th) {
        var handle = th.querySelector('.cn-rh');
        if (!handle) return;

        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            e.stopPropagation();

            var startX      = e.clientX;
            var startW      = th.offsetWidth;
            var startTableW = table.offsetWidth;

            handle.classList.add('active');
            document.body.classList.add('no-select');

            // Full-page overlay captures mouse even if cursor leaves handle area
            var overlay = document.createElement('div');
            overlay.style.cssText =
                'position:fixed;top:0;left:0;width:100%;height:100%;' +
                'cursor:col-resize;z-index:9999;';
            document.body.appendChild(overlay);

            function onMove(ev) {
                var newW = startW + (ev.clientX - startX);
                if (newW < 50) newW = 50;      // min column width
                var actualDelta = newW - startW;
                th.style.width = newW + 'px';
                // Grow/shrink the table by the same delta so sibling
                // columns keep their width and the handle stays under
                // the cursor.
                var newTableW = startTableW + actualDelta;
                table.style.width = newTableW + 'px';
                table.style.minWidth = newTableW + 'px';
            }

            function onUp() {
                handle.classList.remove('active');
                document.body.classList.remove('no-select');
                if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                document.removeEventListener('mousemove', onMove, true);
                document.removeEventListener('mouseup', onUp, true);
            }

            // Use capture phase so overlay doesn't swallow events
            document.addEventListener('mousemove', onMove, true);
            document.addEventListener('mouseup', onUp, true);
        });
    });
})();
</script>
"""


def _build_html_document(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> str:
    """Build a full HTML document with a resizable, text-wrapping table.

    Rendered via ``st.components.v1.html()`` which executes ``<script>``
    tags (unlike ``st.markdown`` which strips them).

    Layout strategy:
    1. Table starts with ``table-layout: auto`` so the browser sizes
       columns naturally based on content.
    2. On load, JS snapshots those widths, switches to ``table-layout:
       fixed``, and applies the snapshot.  This locks widths so that
       drag-to-resize works predictably.
    """
    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        _TABLE_CSS,
        "</head><body>",
        '<div class="cn-table-wrap">',
        '<table class="cn-table">',
    ]

    # Header — each <th> gets a draggable resize handle
    parts.append("<thead><tr>")
    for col in columns:
        parts.append(
            f'<th>{html_mod.escape(_humanise(col))}'
            f'<span class="cn-rh"></span></th>'
        )
    parts.append("</tr></thead>")

    # Body
    parts.append("<tbody>")
    for row in rows:
        parts.append("<tr>")
        for col in columns:
            val = row.get(col, "")
            cell_text = html_mod.escape(str(val)) if val is not None else ""
            parts.append(f"<td>{cell_text}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")

    parts.append(_RESIZE_JS)
    parts.append("</body></html>")
    return "\n".join(parts)


def _to_csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    """Serialise *rows* (filtered to *columns*) as UTF-8 CSV bytes."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_data_table(
    records: list[dict[str, Any]],
    default_columns: list[str] | None = None,
    all_columns: list[str] | None = None,
    key: str = "data_table",
    title: str | None = None,
    page_size: int = 25,
    export_filename: str | None = None,
) -> None:
    """Render an interactive, column-togglable data table.

    Parameters
    ----------
    records:
        Row data as a list of dicts (e.g. from
        ``FinalControlRecord.to_export_dict()``).
    default_columns:
        Column keys shown by default.  If *None*, the first 6 keys of the
        first record are used.
    all_columns:
        Full set of available column keys.  If *None*, auto-detected from
        the union of all record keys (preserving insertion order).
    key:
        Unique Streamlit widget key prefix.  Required when rendering more
        than one table on the same page.
    title:
        Optional heading rendered above the table.
    page_size:
        Maximum rows shown before the container scrolls.
    export_filename:
        If provided, a **Download CSV** button is rendered below the table.
    """
    if not records:
        st.info("No records to display.")
        return

    # Resolve column lists ------------------------------------------------
    if all_columns is None:
        seen: dict[str, None] = {}
        for rec in records:
            for k in rec:
                seen.setdefault(k, None)
        all_columns = list(seen)

    if default_columns is None:
        default_columns = all_columns[:6]
    # Ensure defaults are valid subsets
    default_columns = [c for c in default_columns if c in all_columns]

    # Title ---------------------------------------------------------------
    if title:
        st.markdown(
            f'<div class="metric-label" style="margin-bottom:0.5rem;">{title}</div>',
            unsafe_allow_html=True,
        )

    # Column selector -----------------------------------------------------
    visible = st.multiselect(
        "Visible columns",
        options=all_columns,
        default=default_columns,
        key=f"{key}__col_select",
        format_func=_humanise,
        label_visibility="collapsed",
        placeholder="Select columns to display…",
    )

    if not visible:
        st.warning("Select at least one column.")
        return

    # Build filtered rows -------------------------------------------------
    filtered_rows = [
        {col: rec.get(col, "") for col in visible}
        for rec in records
    ]

    # Render HTML table ---------------------------------------------------
    # components.html() renders in an iframe that executes <script> tags.
    # The iframe handles vertical scrolling (no inner scroll container).
    table_html = _build_html_document(filtered_rows, visible)

    # Height: generous per-row estimate (wrapped text makes rows taller).
    # Capped at 620px — the iframe scrolls beyond that.
    row_px = 48  # accommodate 1-2 lines of wrapped text per row
    iframe_h = min(len(filtered_rows), page_size) * row_px + 55  # +55 for header
    iframe_h = max(iframe_h, 200)
    iframe_h = min(iframe_h, 620)
    components.html(table_html, height=iframe_h, scrolling=True)

    # Export button --------------------------------------------------------
    if export_filename:
        csv_bytes = _to_csv_bytes(records, visible)
        st.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name=export_filename,
            mime="text/csv",
            key=f"{key}__csv_dl",
        )
