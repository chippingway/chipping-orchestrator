# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one run is identified by on the page, in a tile, a row, and a label.

Three renderings of the same record, each for a different question. The
metadata grid answers "what was this run" once a run is open, and it omits a
field the record never carried rather than drawing an empty tile -- a blank
review round and a review round of zero are different facts. The overview table
answers "which run do I want" across a whole read, in the order the read handed
them over. The picker label is that same choice narrowed to one cohort, where
the repository and issue have already been chosen above it.

A fixture is marked in the two places an operator chooses from: a tagged,
dimmed table row and a prefixed label. The tell itself is the record's own, so
what is decided here is only how it reads.

A table row also says what the run used and cost, read off the run summary
alone: the non-overlapping token total, or ``unknown`` where the record's
evidence cannot settle it, and the run's own cost worded by ``cost_text`` with
its basis and any completeness qualifier, so a row never shows a bare amount
an operator could take for complete spend on an unnamed basis.

Every value that reaches the markup is escaped first: a page writes these with
``unsafe_allow_html=True``, and a repository name, a tool name, and a skill
name are all record text this viewer does not own.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from orchestrator.observability.trajectory_viewer import cost_text
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun

REPO_LABEL = "Repo"
FIXTURE_LABEL_PREFIX = "[fixture] "


def meta_html(run: TrajectoryRun) -> str:
    """Render the identity tiles a run carries, omitting the empty ones."""
    fields: list[tuple[str, str]] = [
        (REPO_LABEL, run.repo),
        ("Issue", f"#{run.issue}" if run.issue else ""),
        ("Stage", run.stage),
        ("Agent role", run.agent_role),
        ("Backend", run.backend),
        ("Review round", "" if run.review_round is None else str(run.review_round)),
        ("Retry count", "" if run.retry_count is None else str(run.retry_count)),
        ("Session", run.session_id),
        ("Recorded", run.ts),
    ]
    cells = [
        '<div class="orch-traj-meta-item">'
        f'<div class="k">{html.escape(label)}</div>'
        f'<div class="v">{html.escape(cell)}</div></div>'
        for label, cell in fields
        if cell
    ]
    return '<div class="orch-traj-meta">{}</div>'.format("".join(cells))


def labeled_chips_html(
    label: str,
    names: Sequence[str],
    empty_marker: str = "",
) -> str:
    """Render one labeled chip row, or nothing where there is no marker."""
    if names:
        chips = "".join(
            f'<span class="orch-traj-chip">{html.escape(name)}</span>'
            for name in names
        )
    elif empty_marker:
        chips = f'<span class="orch-traj-chip none">{html.escape(empty_marker)}</span>'
    else:
        return ""
    return (
        '<div class="orch-traj-chips">'
        f'<span class="lbl">{html.escape(label)}</span>{chips}</div>'
    )


def run_table_row_html(run: TrajectoryRun) -> str:
    """Render one overview row, flagged where the run is a fixture."""
    round_cell = "" if run.review_round is None else str(run.review_round)
    tokens_cell = "unknown" if run.total_tokens is None else f"{run.total_tokens:,}"
    row_class = ' class="fixture"' if run.is_fixture else ""
    fixture_tag = (
        '<span class="orch-traj-fixture-tag">fixture</span>'
        if run.is_fixture
        else ""
    )
    return (
        f"<tr{row_class}>"
        f'<td class="num">#{html.escape(str(run.issue))}</td>'
        f"<td>{html.escape(run.repo)}{fixture_tag}</td>"
        f"<td>{html.escape(run.stage)}</td>"
        f"<td>{html.escape(run.agent_role)}</td>"
        f"<td>{html.escape(run.backend)}</td>"
        f'<td class="num">{html.escape(round_cell)}</td>'
        f'<td class="num">{html.escape(str(run.step_count))}</td>'
        f'<td class="num">{html.escape(str(run.tool_calls))}</td>'
        f'<td class="num">{html.escape(tokens_cell)}</td>'
        f"<td>{html.escape(cost_text.cost_text(run.cost_evidence))}</td>"
        f"<td>{html.escape(run.ts)}</td></tr>"
    )


def runs_table_html(runs: Sequence[TrajectoryRun]) -> str:
    """Render the overview table, in the order the read handed the runs over."""
    headers = (
        "Issue",
        REPO_LABEL,
        "Stage",
        "Role",
        "Backend",
        "Round",
        "Steps",
        "Tool calls",
        "Tokens",
        "Cost",
        "Recorded",
    )
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    rows_html = "".join(run_table_row_html(run) for run in runs)
    return (
        '<table class="orch-traj-table"><thead><tr>'
        f"{head}</tr></thead><tbody>{rows_html}</tbody></table>"
    )


def run_picker_label(run: TrajectoryRun) -> str:
    """Label one run inside its cohort, prefixed where it is a fixture."""
    label = run.detail_label()
    return f"{FIXTURE_LABEL_PREFIX}{label}" if run.is_fixture else label
