# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The previous window's scalars, read for the deltas a KPI strip shows.

A delta pill needs only what the current window is compared against -- spend,
the four token bands, and the finished-run count -- so this scan carries none
of the distinct counts or breakdown groupings the current window's summary
does, and costs one aggregate pass instead of three. Every unread field is left
at its model default, so a consumer reading the same `Summary` shape sees a
zero rather than a stale value from the window beside it.

Agent runs are the `event = 'agent_exit'` subset of the same buckets, matching
how the current window counts them, or the two windows would not be comparable.
An empty window returns no row at all, which is the same "nothing to compare
against" answer as an unconfigured database.
"""

from __future__ import annotations

from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.row_cells import cost_cell


def kpi_prev_sql(where: str) -> str:
    """Build the trimmed scalar scan a KPI comparison reads back."""
    return (
        "SELECT "
        "COALESCE(SUM(total_cost_usd), 0) AS total_cost_usd, "
        "COALESCE(SUM(total_input_tokens), 0) AS total_input_tokens, "
        "COALESCE(SUM(total_output_tokens), 0) AS total_output_tokens, "
        "COALESCE(SUM(total_cache_read_tokens), 0) "
        "  AS total_cache_read_tokens, "
        "COALESCE(SUM(total_cache_write_tokens), 0) "
        "  AS total_cache_write_tokens, "
        "COALESCE(SUM(CASE WHEN event = 'agent_exit' "
        "                  THEN event_count ELSE 0 END), 0) "
        "  AS total_agent_runs "
        f"FROM {DAILY_ROLLUP_VIEW}{where}"
    )


def kpi_prev_summary(
    query: ReadQuery,
    filters: WindowFilters,
) -> Summary:
    """Return the previous window's scalars in the shared Summary shape."""
    where, bindings = build_rollup_window_where(filters)
    rows = query.select(kpi_prev_sql(where), bindings)
    if not rows:
        return Summary()
    row = rows[0]
    return Summary(
        total_cost_usd=cost_cell(row, 0),
        total_input_tokens=int(row[1] or 0),
        total_output_tokens=int(row[2] or 0),
        total_cache_read_tokens=int(row[3] or 0),
        total_cache_write_tokens=int(row[4] or 0),
        total_agent_runs=int(row[5] or 0),
    )
