# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The previous window's scalars, read for the deltas a KPI strip shows.

A delta pill needs only what the current window is compared against -- spend,
tokens, and the finished-run count -- so this scan carries none of the distinct
counts or breakdown groupings the current window's summary does, and costs one
aggregate pass instead of three. Every unread field is left at its model
default, so a consumer reading the same `Summary` shape sees a zero rather than
a stale value from the window beside it.

Spend and tokens are read through the same rollup reductions the current
window's summary is, `cost_cohorts.ROLLUP_COST_COHORT_SQL` and
`token_totals.ROLLUP_TOKEN_TOTAL_SQL`, so the window a delta is measured
against carries its own basis, completeness, and unknown token runs: a
comparison can only say what both sides state. Agent runs are the
`event = 'agent_exit'` subset of the same buckets, matching how the current
window counts them, or the two windows would not be comparable. An empty window
returns no row at all, which is the same "nothing to compare against" answer as
an unconfigured database.
"""

from __future__ import annotations

from orchestrator.observability.analytics.query.cost_cohorts import (
    COST_COHORT_WIDTH,
    ROLLUP_COST_COHORT_SQL,
    cost_cohort,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.token_totals import ROLLUP_TOKEN_TOTAL_SQL

# The run count leads the row, the cohort follows it, and the token pair closes it.
_TOKENS_START = 1 + COST_COHORT_WIDTH


def kpi_prev_sql(where: str) -> str:
    """Build the trimmed scalar scan a KPI comparison reads back."""
    return (
        "SELECT "
        "COALESCE(SUM(CASE WHEN event = 'agent_exit' "
        "                  THEN event_count ELSE 0 END), 0) "
        "  AS total_agent_runs, "
        f"{ROLLUP_COST_COHORT_SQL}, "
        f"{ROLLUP_TOKEN_TOTAL_SQL} "
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
    known_tokens, unknown_runs = rows[0][_TOKENS_START:_TOKENS_START + 2]
    return Summary(
        total_agent_runs=int(rows[0][0] or 0),
        cost=cost_cohort(rows[0], 1),
        total_tokens=int(known_tokens or 0),
        unknown_token_runs=int(unknown_runs or 0),
    )
