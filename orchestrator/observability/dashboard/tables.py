# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The compact table the page's hand-rolled panels are drawn as.

Four panels -- the most expensive issues, the aggregate skill-trigger rates,
the per-session adoption matrix, and the invocation-level trigger matrix -- are
inline HTML rather than `st.dataframe`, because each carries an in-row bar, a
status pill, or a sortable header Streamlit's own table cannot draw. They read
as one page only while the type scale, the uppercase header row, the
right-aligned mono numerals, and the hairline row rule are decided once: a
panel restating them drifts from the ones beside it the first time a padding is
nudged. The class name is interpolated rather than fixed so each panel scopes
its own rules, and a caller's extra rules are appended inside the same `<style>`
tag the shared ones are written in, so a panel cannot end up styled by half of
what it asked for.

Beside the markup are the readings a cell is built from: the share of the
widest bar a row is drawn at, the repository name without the owner hosting it,
and the zero a missing count reports as. Money is not among them: an amount is
worded with its basis and completeness by the cost owners, since a run that
cost nothing and a run the parser could not price are different answers, and a
table spelling both `$0.00` would hide the gap the coverage banner is raised
for.

Producing a table costs neither Streamlit nor Plotly, so an importer that never
renders one still loads cleanly.
"""
from __future__ import annotations

import html
from collections.abc import Sequence


def table_css(table_class: str, *, extra_rules: str = "") -> str:
    """Return the shared inline CSS block for compact dashboard tables."""
    return f"""
<style>
  .{table_class} {{ width: 100%; border-collapse: collapse;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 12.5px; }}
  .{table_class} thead th {{ color: var(--orch-muted);
    font-size: 11px; font-weight: 500; letter-spacing: 0.05em;
    text-transform: uppercase; text-align: left;
    padding: 4px 6px 8px; border-bottom: 1px solid var(--orch-border); }}
  .{table_class} thead th.r {{ text-align: right; }}
  .{table_class} tbody td {{ padding: 8px 6px; vertical-align: middle;
    border-bottom: 1px solid var(--orch-grid); }}
  .{table_class} tbody tr:last-child td {{ border-bottom: 0; }}
  .{table_class} td.r {{ text-align: right; font-family:
    ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums; color: var(--orch-ink); }}
{extra_rules}
</style>
"""


def table_head_html(columns: Sequence[tuple[str, bool]]) -> str:
    """Render the header row, right-aligning the columns that asked for it."""
    cells = []
    for label, right_aligned in columns:
        css_class = ' class="r"' if right_aligned else ""
        cells.append(f"<th{css_class}>{html.escape(label)}</th>")
    return "<thead><tr>{}</tr></thead>".format("".join(cells))


def table_html(
    *,
    table_class: str,
    css: str,
    head: str,
    rows: Sequence[str],
) -> str:
    """Assemble one panel: its rules, its header, and its rendered rows."""
    return (
        css
        + f'<table class="{table_class}">'
        + head
        + "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def relative_width_pct(magnitude: float, maximum: float) -> float:
    """The width an in-row bar is drawn at, as a share of the widest one."""
    return magnitude / maximum * 100 if maximum > 0 else float(0)


def short_repo_name(repo: str) -> str:
    """The repository name a row is labelled by, without its owner."""
    return repo.split("/")[-1] if "/" in repo else repo


def int_or_zero(raw: object) -> int:
    """The count a cell reports, with a missing one read as zero."""
    if raw is None:
        return 0
    return int(raw)
