# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the page draws between its two read waves, and the load it stages.

A window's panels are read in two waves so the page has something on screen
while the second one is still out. This owner is what fills that gap: the
banner and filter line written back into the slots the controls left, the
banners a window is worth interrupting the page for, and the four-tile strip
every section below is read against.

Which reads each wave is made of belongs to ``read_plan`` and driving the pair
belongs to ``dispatch``; what is decided here is what an operator sees in
between, and the one case where there is nothing more to see. A window whose
first wave reported no event at all has nothing for the panels beneath to draw,
so the chrome is drawn, the empty-window notice takes over, and reporting
nothing back is what ends the load before the second wave is paid for -- which
makes the return value a short circuit rather than only a result.

The banner's spend, the strip's money, and the unpriced-coverage banner are all
read off the window's one cost cohort, so the topbar, the tiles, and the notice
above them cannot disagree about a window's basis or about which of its runs
left the amount short.

Every sibling a pass here calls is named directly, so a test intercepting a
render patches the module that holds it and a page and a fix land on the same
object.

Streamlit and the theme are the caller's, carried in the modules shape, so this
owner imports neither and what it assembles stays testable without them.
"""
from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import Any

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import (
    card_html,
    dispatch,
    insights,
    kpi_strip,
    page_models,
    page_states,
    summary_html,
)


def render_topbar_and_meta(
    modules: page_models.DashboardModules,
    page: page_models.DashboardPage,
    summary: Summary,
) -> None:
    """Fill the two slots the controls left above the panels."""
    page.controls.topbar_slot.markdown(
        summary_html.topbar_html(
            extent=page.extent,
            distinct_repos=summary.distinct_repos,
            total_events=summary.total_events,
            spend_in_range=summary.cost,
            fmt_num=modules.theme.fmt_num,
        ),
        unsafe_allow_html=True,
    )
    filters = page.controls.filters
    page.controls.meta_slot.markdown(
        summary_html.filter_meta_html(
            from_d=filters.window.start.date(),
            to_d=(filters.window.end - timedelta(days=1)).date(),
            days=filters.days,
            runs=summary.total_agent_runs,
            fmt_num=modules.theme.fmt_num,
        ),
        unsafe_allow_html=True,
    )


def render_dashboard_insights(
    modules: page_models.DashboardModules,
    summary: Summary,
) -> None:
    """Raise the banners a window is worth interrupting the page for."""
    banners = insights.compute_insights(summary)
    if banners:
        modules.st.markdown(
            card_html.insights_html(banners),
            unsafe_allow_html=True,
        )


def render_first_wave(
    modules: page_models.DashboardModules,
    page: page_models.DashboardPage,
    read_results: dict[str, Any],
) -> page_models.DashboardKpis | None:
    """Draw the chrome and the strip, or leave through the empty window."""
    summary = read_results["summary"]
    render_topbar_and_meta(modules, page, summary)
    if summary.total_events == 0:
        page_states.render_empty_window(modules, page)
        return None
    render_dashboard_insights(modules, summary)
    kpi_values = kpi_strip.build_kpi_strip_data(
        kpi_strip.KpiInputs(
            theme=modules.theme,
            summary=summary,
            prev_summary=read_results["prev_summary"],
            ts_points=read_results["ts_points"],
            throughput_rows=read_results["throughput_rows"],
            review_round_rows=read_results["review_round_rows"],
            days_in_window=page.controls.filters.days,
        )
    )
    modules.st.markdown(
        summary_html.kpi_strip_html(kpi_values[0]),
        unsafe_allow_html=True,
    )
    return page_models.DashboardKpis(*kpi_values)


def load_dashboard_data(
    modules: page_models.DashboardModules,
    page: page_models.DashboardPage,
) -> page_models.LoadedDashboard | None:
    """Run the staged load, drawing the chrome between its two waves."""
    loaded = dispatch.run_read_waves(
        page.reads,
        st=modules.st,
        render_first_wave=partial(render_first_wave, modules, page),
    )
    if loaded is None:
        return None
    read_results, kpis = loaded
    return page_models.LoadedDashboard(read_results=read_results, kpis=kpis)
