# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The banner and the five tiles a whole read is summarized in.

What a page draws above its filters: the brand bar naming how many runs the
file holds and how many the current narrowing left, and the KPI strip the
headline counts are rendered into. Both are built off the summary the read
model already totalled rather than off the runs, so the figures an operator
reads are the ones the filters produced.

Every caller-supplied string goes through ``html.escape`` before it reaches the
markup, because a page writes these with ``unsafe_allow_html=True`` and a
repository name, a stage, or a KPI label is record text this viewer does not
own.

The money tile is worded by ``cost_text``, the one owner every cost on the page
is spelled through, and it is named for what the total is: ``Total cost`` only
where every run's spend is covered, and ``Cost subtotal`` wherever a run's
usage went unpriced or its cost states no basis, with the foot naming the basis
-- each part's amount beside a blended one -- and how many runs the subtotal is
missing.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from orchestrator.observability.dashboard import formatting
from orchestrator.observability.trajectory_viewer import cost_text
from orchestrator.observability.trajectory_viewer.summaries import TrajectorySummary


@dataclass(frozen=True)
class _TrajectoryKpi:
    """One headline tile: its label, its figure, and the note under it."""

    label: str
    figure: str
    foot: str = ""


def card_header_html(title: str, sub: str) -> str:
    """Render the title and subtitle line a card opens with."""
    return (
        f'<p class="orch-card-title">{html.escape(title)}</p>'
        f'<p class="orch-card-sub">{html.escape(sub)}</p>'
    )


def topbar_html(total_runs: int, shown_runs: int) -> str:
    """Render the brand bar and the in-view count beside it."""
    return (
        '<div class="orch-topbar"><div class="orch-brand">'
        '<span class="orch-brand-mark">TR</span><div>'
        '<h1>Orchestrator Trajectories</h1>'
        '<p class="orch-sub">agent reasoning traces · '
        f"{formatting.fmt_num(total_runs)} recorded</p></div></div>"
        '<div class="orch-spend"><span class="label">In view</span>'
        f'<span class="value">{formatting.fmt_num(shown_runs)} / '
        f"{formatting.fmt_num(total_runs)}</span></div></div>"
    )


def cost_kpi(summary: TrajectorySummary) -> _TrajectoryKpi:
    """Build the money tile, named a subtotal wherever spend is not covered."""
    notes = [cost_text.basis_text(summary.total_cost)]
    for count, missing in (
        (summary.incomplete_cost_runs, "unpriced"),
        (summary.unknown_cost_runs, "without a cost basis"),
    ):
        if count:
            noun = "run" if count == 1 else "runs"
            notes.append(f"{formatting.fmt_num(count)} {noun} {missing}")
    complete = not cost_text.completeness_text(summary.total_cost)
    return _TrajectoryKpi(
        "Total cost" if complete else "Cost subtotal",
        cost_text.cost_figure(summary.total_cost),
        " · ".join(note for note in notes if note),
    )


def trajectory_kpis(summary: TrajectorySummary) -> tuple[_TrajectoryKpi, ...]:
    """Build the five tiles a summarized read is reported through."""
    if summary.truncated_runs:
        truncated_foot = f"{formatting.fmt_num(summary.truncated_runs)} truncated"
    else:
        truncated_foot = "none truncated"
    return (
        _TrajectoryKpi("Runs", formatting.fmt_num(summary.total_runs), truncated_foot),
        _TrajectoryKpi("Issues", formatting.fmt_num(summary.distinct_issues)),
        _TrajectoryKpi("Repos", formatting.fmt_num(summary.distinct_repos)),
        _TrajectoryKpi("Tool calls", formatting.fmt_num(summary.total_tool_calls)),
        cost_kpi(summary),
    )


def trajectory_kpi_html(kpi: _TrajectoryKpi) -> str:
    """Render one tile, keeping the foot slot even where there is no note."""
    if kpi.foot:
        foot_html = (
            f'<div class="kpi-foot"><span>{html.escape(kpi.foot)}</span></div>'
        )
    else:
        foot_html = '<div class="kpi-foot"></div>'
    return (
        '<div class="orch-kpi"><div class="kpi-top">'
        f'<span class="kpi-label">{html.escape(kpi.label)}</span></div>'
        f'<div class="kpi-value">{html.escape(kpi.figure)}</div>'
        f"{foot_html}</div>"
    )


def kpi_strip_html(summary: TrajectorySummary) -> str:
    """Render the five trajectory KPI tiles."""
    cells = (trajectory_kpi_html(kpi) for kpi in trajectory_kpis(summary))
    return '<div class="orch-kpis">{}</div>'.format("".join(cells))
