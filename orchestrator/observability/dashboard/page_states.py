# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two states a page leaves through, and the line it ends on.

Every panel between them draws a reading. These three are what is drawn when
there is no reading to draw, or once the last one already has been: the startup
state a database nobody has ingested into is answered with, the notice a
filtered window matching no row gets, and the footer restating what the numbers
above it were measured over.

The two states are dead ends of different kinds. A database holding nothing at
all has no extent to pick a window from, so there is no filter bar to offer:
the banner is drawn with its counts zeroed and the script is stopped where it
stands. A window that merely matched nothing still has a page around it, so
that one keeps the chrome already rendered above it and hands the page on to
the trace at the foot of it -- an operator narrowing to one issue is exactly
who lands on an empty window, and that trace is scoped by the issue rather than
by the window's cache key, so it can still have something to show.

Emitting the load line is the other half of that hand-off. The dispatch owner
times a load off the line ``run_read_waves`` ends on, and a window that skips
the second wave never reaches it, so the notice that ended the load reports it
instead -- off the plan's own clock and the first wave alone, rather than the
full inventory nobody paid for.

The footer closes on the day before the window's end. Every read beneath the
page is issued under ``ts < end``, so restating ``end`` itself would name a day
none of the numbers above it covered.

Streamlit and the theme are the caller's, handed in as parameters, so this
owner imports neither and the markup it assembles stays readable without them.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from orchestrator.observability.analytics.query.overview_models import (
    DataExtent,
    Summary,
)
from orchestrator.observability.dashboard import (
    dispatch,
    drilldown,
    page_models,
    summary_html,
)

NO_DATA_MESSAGE = (
    "No analytics events have been recorded yet. Run "
    "`python -m orchestrator.observability.analytics.sync.cli` in the installed environment after some "
    "workflow activity to populate the dashboard."
)
EMPTY_WINDOW_MESSAGE = (
    "No analytics events match the current filters. Broaden the window "
    "or clear a filter to see activity."
)


def render_dashboard_footer(
    modules: page_models.DashboardModules,
    filters: page_models.DashboardFilters,
    summary: Summary,
) -> None:
    """Close the page on the span and the run count it was drawn over."""
    end_date = (filters.window.end - timedelta(days=1)).date()
    window_start = filters.window.start.date().isoformat()
    agent_runs = modules.theme.fmt_num(summary.total_agent_runs)
    modules.st.markdown(
        '<div class="orch-foot">'
        f"Real data · window {window_start} → {end_date.isoformat()} · "
        f"{agent_runs} agent runs</div>",
        unsafe_allow_html=True,
    )


def render_no_data(*, st: Any, extent: DataExtent, theme: Any) -> None:
    """Render the no-data startup state and stop."""
    st.markdown(
        summary_html.topbar_html(
            extent=extent,
            distinct_repos=0,
            total_events=0,
            spend_in_range=float(0),
            fmt_money_exact=theme.fmt_money_exact,
            fmt_num=theme.fmt_num,
        ),
        unsafe_allow_html=True,
    )
    st.info(NO_DATA_MESSAGE)
    st.stop()


def render_empty_window(
    modules: page_models.DashboardModules,
    page: page_models.DashboardPage,
) -> None:
    """Render an empty filtered window and skip the second read wave."""
    dispatch.log_dashboard_load(
        load_start=page.reads.started_at,
        reads=len(page.reads.first_wave),
        parallel=page.reads.parallel,
    )
    modules.st.info(EMPTY_WINDOW_MESSAGE)
    drilldown.render_drilldown_view(modules, page.controls.filters)
