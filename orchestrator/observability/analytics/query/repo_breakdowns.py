# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of one window's activity and spend each repository accounts for.

A bare `COUNT(DISTINCT issue)` is safe here only because the grouping is by
repository: issue numbers repeat across repositories, so the count is
per-repository already and cannot collapse two issues that merely share a
number. Agent runs are counted as the `event = 'agent_exit'` subset of the same
buckets, so the run column and the cost beside it describe the same rows. The
cost is the repository's cost cohort (`cost_cohorts.ROLLUP_COST_COHORT_SQL`),
so its bases and the runs it leaves unpriced or states no evidence for stay
apart rather than summing `total_cost_usd`. Ties on event volume break on the
repository name, so redrawing the same window returns the same order.
"""

from __future__ import annotations

from orchestrator.observability.analytics.query.cost_cohorts import ROLLUP_COST_COHORT_SQL, cost_cohort
from orchestrator.observability.analytics.query.cost_models import RepoBreakdownRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)

# The repository and its three counts lead a row, and the cohort closes it.
_COHORT_START = 4


def repo_breakdown_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[RepoBreakdownRow]:
    """Return one aggregate row per repository in the selected window."""
    where, bindings = build_rollup_window_where(filters)
    rows = query.select(
        "SELECT repo, "
        "COUNT(DISTINCT issue) AS repo_issues, "
        "COALESCE(SUM(event_count), 0) AS repo_events, "
        "COALESCE(SUM(CASE WHEN event = 'agent_exit' "
        "                  THEN event_count ELSE 0 END), 0) "
        "  AS repo_agent_exits, "
        f"{ROLLUP_COST_COHORT_SQL} "
        f"FROM {DAILY_ROLLUP_VIEW}{where} "
        "GROUP BY repo "
        "ORDER BY repo_events DESC, repo ASC",
        bindings,
    )
    return [
        RepoBreakdownRow(
            repo=row[0],
            issues=int(row[1] or 0),
            events=int(row[2] or 0),
            agent_exits=int(row[3] or 0),
            cost=cost_cohort(row, _COHORT_START),
        )
        for row in rows
    ]
