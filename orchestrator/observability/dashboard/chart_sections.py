# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The five cards a window's figures are drawn on, in the order they stack.

Every panel here is its own owner; what this one decides is which of them the
second wave reaches first. That order is the page's argument rather than a
layout preference: the hero card answers whether a day's cost tracked the work
behind it, the lifecycle bars say where that cost went, the ranking beside them
says which issues and backends it went to, the repository pair asks whether the
runs it went to held up, and the activity grid is the only card that keeps the
clock instead of reducing the window to a reading -- so it closes the run.

The paired repository-spend and run-health section is the one handed a shape
rather than keyword rows, because it is the only card drawn from four reads at
once and a repo list and a throughput series passed positionally are two
arguments nothing would catch swapped.

Each panel is named on its own owner, so a test intercepting a section patches
the module that draws it. Streamlit, pandas, and the theme are the caller's,
carried in the modules shape, and every figure below reaches Plotly inside its
own call, so importing this owner costs neither dependency.
"""
from __future__ import annotations

from orchestrator.observability.dashboard import (
    activity_panel,
    issue_cost_panel,
    page_models,
    reliability_panel,
    stage_cost_panel,
    usage_panel,
)


def render_chart_widgets(
    modules: page_models.DashboardModules,
    page: page_models.DashboardPage,
    loaded: page_models.LoadedDashboard,
) -> None:
    """Draw the five figure-bearing cards in page order."""
    read_results = loaded.read_results
    usage_panel.render_hero_usage(
        st=modules.st,
        ts_points=read_results["ts_points"],
        backend_daily_rows=read_results["backend_daily_rows"],
    )
    stage_cost_panel.render_stage_review_bars(
        st=modules.st,
        stage_rows=read_results["stage_rows"],
        review_round_rows=read_results["review_round_rows"],
    )
    issue_cost_panel.render_issues_and_backends(
        st=modules.st,
        theme=modules.theme,
        issues_rows=read_results["issues_rows"],
        backend_rows=read_results["backend_rows"],
    )
    reliability_panel.render_repo_and_reliability(
        modules,
        page_models.ReliabilityPanelData(
            repos=read_results["repo_rows"],
            summary=read_results["summary"],
            throughput=read_results["throughput_rows"],
            window=page.controls.filters.window,
            resolved=loaded.kpis.resolved,
            rejected=loaded.kpis.rejected,
        ),
    )
    activity_panel.render_activity_heatmap(
        st=modules.st,
        heatmap_rows=read_results["heatmap_rows"],
        tz_offset_choice=page.controls.timezone_offset,
    )
