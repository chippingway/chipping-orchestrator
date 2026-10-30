# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How one window's spend divides across the review rounds it took.

The bucket is a label rather than a number, because the axis a panel plots has
to hold two things a round count cannot. Every developer and reviewer run
records its round -- a fresh implementation as round zero -- so a missing one
reads as `unknown` rather than being folded into a round it never named. And
everything from the sixth round up collapses into one `6+` bucket, so a rare
twelve-round issue cannot stretch the axis for the rest.

The scan groups by round and role together, so each role's runs are reduced by
the same fragments every other cost read uses -- the cost cohort
(`cost_cohorts.RUN_COST_COHORT_SQL`), keeping each basis, its rate dates, and
the runs it leaves unpriced or states no evidence for apart, and the three
`cache_shares` bands its stated amount is allocated into by each run's token
share. The rows are then folded into one per round here, the developer and
reviewer halves side by side, so a panel can stack the two roles or the bands
inside one and have them add back up to what the round's runs state. The scan
narrows to those two roles, because a decomposer or question run has no review
round to file under and would land in a bucket the chart has no bar for.
Rounds come back busiest first, ties in bucket order.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from operator import attrgetter
from typing import Any

from orchestrator.observability.analytics.query.cache_shares import (
    NO_TOKEN_SHARE,
    RUN_TOKEN_SHARE_SQL,
    TokenShareBands,
    token_share_bands,
)
from orchestrator.observability.analytics.query.conditions import append_where_condition
from orchestrator.observability.analytics.query.cost_cohorts import (
    EMPTY_COST_COHORT,
    RUN_COST_COHORT_SQL,
    CostCohort,
    cost_cohort,
)
from orchestrator.observability.analytics.query.cost_models import ReviewRoundBucketRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_view_window_where
from orchestrator.observability.analytics.query.query_rows import ReviewRoundQueryRow, review_round_row

_DEVELOPER = "developer"

_REVIEWER = "reviewer"


def review_round_sql(where: str) -> str:
    """Build the per-round-and-role run, cost, and token-share scan."""
    return (
        "SELECT "
        "CASE "
        "WHEN review_round IS NULL THEN 'unknown' "
        "WHEN review_round <= 0 THEN '0' "
        "WHEN review_round >= 6 THEN '6+' "
        "ELSE review_round::text "
        "END AS bucket, "
        "agent_role, "
        "COUNT(*) AS runs, "
        "SUM(CASE WHEN failed THEN 1 ELSE 0 END) AS failed_runs, "
        f"{RUN_TOKEN_SHARE_SQL}, "
        f"{RUN_COST_COHORT_SQL} "
        f"FROM analytics_agent_runs{where} "
        "GROUP BY bucket, agent_role "
        "ORDER BY bucket ASC, agent_role ASC"
    )


def review_round_buckets(rows: Iterable[Sequence[Any]]) -> list[ReviewRoundBucketRow]:
    """Fold the per-role rows into one per round, busiest first and ties in the order the scan returned them."""
    by_bucket: dict[str, list[ReviewRoundQueryRow]] = {}
    for named in map(review_round_row, rows):
        by_bucket.setdefault(str(named.bucket), []).append(named)
    folded = (_bucket_row(*grouped) for grouped in by_bucket.items())
    return sorted(folded, key=attrgetter("runs"), reverse=True)


def review_round_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[ReviewRoundBucketRow]:
    """Return one aggregate row per review-round bucket in the window."""
    view_where, view_bindings = build_view_window_where(filters)
    view_where = append_where_condition(
        view_where,
        f"agent_role IN ('{_DEVELOPER}', '{_REVIEWER}')",
    )
    return review_round_buckets(query.select(review_round_sql(view_where), view_bindings))


def _bucket_row(bucket: str, roles: Sequence[ReviewRoundQueryRow]) -> ReviewRoundBucketRow:
    by_role = {str(role.agent_role): role for role in roles}
    developer_cost, developer_bands = _role_reading(by_role.get(_DEVELOPER))
    reviewer_cost, reviewer_bands = _role_reading(by_role.get(_REVIEWER))
    return ReviewRoundBucketRow(
        bucket=bucket,
        runs=sum(int(role.runs or 0) for role in roles),
        failed=sum(int(role.failed or 0) for role in roles),
        developer_cost=developer_cost,
        reviewer_cost=reviewer_cost,
        developer_bands=developer_bands,
        reviewer_bands=reviewer_bands,
    )


def _role_reading(role: ReviewRoundQueryRow | None) -> tuple[CostCohort, TokenShareBands]:
    """One role's cohort and bands in a round; a role with no run there is the empty cohort and no bands."""
    if role is None:
        return EMPTY_COST_COHORT, NO_TOKEN_SHARE
    return cost_cohort(role.cost), token_share_bands(role.token_share)
