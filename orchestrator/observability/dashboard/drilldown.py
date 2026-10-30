# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's events, in the order they happened, at the foot of the page.

Every panel above this one reduces a window to a reading -- a total, a
ranking, a rate -- and the listing beside it reduces one to its rows. This
section is the last narrowing left: a single issue's trace, which is what an
operator opens once a run in that listing raised a question only the sequence
answers -- what ran before it, how long each step took, and where the cost
went.

It is the one read on the page issued outside the cached wrappers, because it
is scoped by more than a cache key carries: those keys are hashed per window
and filter set, and a trace is narrowed to one issue on top of them. It still
enters the shared connection scope, so it runs on the socket the waves above it
opened rather than dialing one of its own.

A repository has to be picked before a number narrows anything. GitHub issue
numbers repeat across repositories, so a trace opened while every repo is
selected would interleave runs that share nothing but a number -- which is why
the section names the control that answers it rather than drawing a trace
nobody can read. The subheading is written before that check, so a number typed
too early still tells the operator which issue the notice is about.

An `agent_exit` row's cost is worded the way the run listing words it -- its
stored amount with its basis and any shortfall, and the dates an estimate's
rates were verified on -- and every other event leaves both cells empty, since
it states no usage rather than a zero.

Streamlit and pandas are the caller's, handed in as parameters, so this owner
imports neither and the row projection stays readable without either installed.
"""
from __future__ import annotations

from typing import Any

from orchestrator.observability.analytics.query import connections, raw_reads
from orchestrator.observability.analytics.query.run_models import IssueEventRow
from orchestrator.observability.dashboard import (
    cost_text,
    filter_binding,
    page_models,
    scoped_reads,
)

MISSING_REPO_MESSAGE = (
    "Pick a specific repo in the sidebar before drilling "
    "into an issue number -- GitHub issue numbers repeat across repos."
)


def drilldown_event_row(event: IssueEventRow) -> dict[str, Any]:
    """The readings one traced event is listed under, in column order."""
    cost = event.cost
    return {
        "ts": event.ts,
        "event": event.event,
        "stage": event.stage,
        "duration (s)": event.duration_s,
        "result": event.result,
        "agent": event.agent_role,
        "backend": event.backend,
        "exit": event.exit_code,
        "cost": None if cost is None else cost_text.cost_text(cost),
        "rates": None if cost is None else cost_text.rates_text(cost),
    }


def read_issue_trace(
    filters: page_models.DashboardFilters,
) -> list[IssueEventRow]:
    """Read one issue's trace inside the scope the page's reads share."""
    return scoped_reads.scoped_read(
        raw_reads.get_issue_events,
        repo=filters.repo,
        issue=filters.issue_input,
        start=filters.window.start,
        end=filters.window.end,
        events=filter_binding.filter_list(filters.events),
        stages=filter_binding.filter_list(filters.stages),
    )


def render_drilldown_view(
    modules: page_models.DashboardModules,
    filters: page_models.DashboardFilters,
) -> None:
    """Render the per-issue event trace when an issue is selected."""
    if filters.issue_input is None:
        return
    modules.st.subheader(f"Issue #{filters.issue_input} drill-down")
    if filters.repo is None:
        modules.st.info(MISSING_REPO_MESSAGE)
        return
    try:
        trace = read_issue_trace(filters)
    except connections.AnalyticsReadError as error:
        modules.st.error(f"Issue drill-down failed: {error}")
        return
    if trace:
        modules.st.dataframe(
            modules.pd.DataFrame(
                [drilldown_event_row(event) for event in trace],
            ),
            use_container_width=True,
        )
    else:
        modules.st.info(
            "No analytics events recorded for "
            f"`{filters.repo}#{filters.issue_input}` under the current filters."
        )
