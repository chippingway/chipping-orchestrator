# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One aggregate row per issue in a window, and the two orders it comes in.

The two orderings are what the same table is read as: "what moved recently"
and "what cost the most". Ranking by cost has to happen in SQL, because
ordering in Python after a `last_seen`-bounded `LIMIT` would silently drop the
older high-cost issues the cost view exists to surface. Either ordering breaks
ties on `(last_seen, repo, issue)` -- the newest activity first, then the pair
naming the issue, the repository compared under the database's collation -- so
a redraw of the same window returns the same page. That order is the ranking:
a reader draws the rows as they come, since re-sorting them in Python would
compare repository names by code point and could reverse a tie the collation
broke the other way.

An issue's cost is the cohort its runs fold to (`EVENT_COST_COHORT_SQL`), read
back with each basis apart and its runs counted by the completeness each
states, and its tokens are the runs' known non-overlapping totals beside the
runs whose total is unknown (`EVENT_TOKEN_TOTAL_SQL`). The cost order ranks on
`stated_cost_usd`, every amount those runs state added across bases
(`EVENT_STATED_USD_SQL`): a blended issue at its whole stated total, an issue
holding unpriced usage at its known subtotal -- a lower bound on what it spent
-- and an amount whose basis nothing states at its stated figure. An issue whose
runs state no amount at all is NULL there and sorts after every issue that
states one, a complete zero included, because its spend cannot be placed: it is
neither free nor measured, and a reader words it as unpriced rather than as a
zero.

Aggregated off `analytics_events` rather than the daily rollup: the per-row
`ts` precision behind `first_seen` / `last_seen`, the latest non-null stage,
and the review-round and retry maxima are all detail the rollup does not carry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import (
    EVENT_COST_COHORT_SQL,
    EVENT_STATED_USD_SQL,
    cost_cohort,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.query_rows import issue_summary_row
from orchestrator.observability.analytics.query.raw_values import (
    float_or_none,
    int_or_none,
)
from orchestrator.observability.analytics.query.run_models import IssueSummaryRow
from orchestrator.observability.analytics.query.token_totals import EVENT_TOKEN_TOTAL_SQL

SORT_BY_LAST_SEEN = "last_seen"
SORT_BY_COST = "cost"
ISSUE_SORT_BY_OPTIONS: frozenset[str] = frozenset((SORT_BY_LAST_SEEN, SORT_BY_COST))


def issue_order_sql(sort_by: str) -> str:
    """Build the `ORDER BY` one of the two reading modes asks for."""
    if sort_by == SORT_BY_COST:
        return "ORDER BY stated_cost_usd DESC NULLS LAST, last_seen DESC, repo ASC, issue ASC"
    return "ORDER BY last_seen DESC, repo ASC, issue ASC"


def issues_sql(where: str, sort_by: str) -> str:
    """Build the per-issue aggregate scan, ordered and capped."""
    return (
        "SELECT "
        "repo, issue, "
        "COUNT(*) AS event_count, "
        "MIN(ts) AS first_seen, "
        "MAX(ts) AS last_seen, "
        "(array_agg(stage ORDER BY ts DESC) "
        "  FILTER (WHERE stage IS NOT NULL))[1] AS latest_stage, "
        "SUM(CASE WHEN event = 'agent_exit' THEN 1 ELSE 0 END) "
        "  AS agent_exits, "
        f"SUM({EVENT_STATED_USD_SQL}) AS stated_cost_usd, "
        f"{EVENT_TOKEN_TOTAL_SQL}, "
        "MAX(review_round) AS max_review_round, "
        "SUM(CASE WHEN event = 'agent_exit' AND exit_code <> 0 "
        "         THEN 1 ELSE 0 END) AS failed_agent_runs, "
        "MAX(retry_count) AS max_retry_count, "
        f"{EVENT_COST_COHORT_SQL} "
        f"FROM analytics_events{where} "
        "GROUP BY repo, issue "
        f"{issue_order_sql(sort_by)} "
        "LIMIT %s"
    )


def issue_summary_from_row(row: Sequence[Any]) -> IssueSummaryRow:
    """Project one per-issue aggregate row onto its result model."""
    query_row = issue_summary_row(row)
    return IssueSummaryRow(
        repo=query_row.repo,
        issue=int(query_row.issue),
        event_count=int(query_row.event_count or 0),
        first_seen=query_row.first_seen,
        last_seen=query_row.last_seen,
        latest_stage=query_row.latest_stage,
        agent_exits=int(query_row.agent_exits or 0),
        cost=cost_cohort(query_row.cost),
        stated_cost_usd=float_or_none(query_row.stated_cost_usd),
        total_tokens=int(query_row.total_tokens or 0),
        unknown_token_runs=int(query_row.unknown_token_runs or 0),
        max_review_round=int_or_none(query_row.max_review_round),
        failed_agent_runs=int(query_row.failed_agent_runs or 0),
        max_retry_count=int_or_none(query_row.max_retry_count),
    )


def issue_summary_rows(
    query: ReadQuery,
    filters: WindowFilters,
    limit: int,
    sort_by: str,
) -> list[IssueSummaryRow]:
    """Return one aggregate row per issue, ordered and capped."""
    where, bindings = build_window_where(filters)
    rows = query.select(
        issues_sql(where, sort_by),
        [*bindings, int(limit)],
    )
    return [issue_summary_from_row(row) for row in rows]
