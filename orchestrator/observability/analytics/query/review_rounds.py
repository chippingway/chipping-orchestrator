# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How one window's spend divides across the review rounds it took.

The bucket is a label rather than a number, because the axis a panel plots has
to hold two things a round count cannot. Every developer and reviewer run
records its round -- a fresh implementation as round zero -- so a missing one
reads as `unknown` rather than being folded into a round it never named. And
everything from the sixth round up collapses into one `6+` bucket, so a rare
twelve-round issue cannot stretch the axis for the rest.

Each bucket reports its runs and cost three ways -- the total, and the
developer and reviewer halves -- with each half split into the cache and
no-cache bands `cache_shares` weights it by, so a panel can stack the two roles
or the two bands and have either pair sum back to the total. The scan narrows
to those two roles, because a decomposer or question run has no review round to
file under and would land in a bucket the chart has no bar for.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cache_shares import (
    AGENT_CACHE_FRACTION_SQL,
)
from orchestrator.observability.analytics.query.conditions import append_where_condition
from orchestrator.observability.analytics.query.cost_models import ReviewRoundBucketRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_view_window_where
from orchestrator.observability.analytics.query.query_rows import review_round_row


def review_round_sql(where: str) -> str:
    """Build the per-round run, cost, role, and cache-split scan."""
    return (
        "SELECT "
        "CASE "
        "WHEN review_round IS NULL THEN 'unknown' "
        "WHEN review_round <= 0 THEN '0' "
        "WHEN review_round >= 6 THEN '6+' "
        "ELSE review_round::text "
        "END AS bucket, "
        "COUNT(*) AS runs, "
        "SUM(CASE WHEN failed THEN 1 ELSE 0 END) AS failed_runs, "
        "COALESCE(SUM(cost_usd), 0) AS bucket_cost_usd, "
        "SUM(CASE WHEN agent_role = 'developer' THEN 1 ELSE 0 END) "
        "AS developer_runs, "
        "SUM(CASE WHEN agent_role = 'reviewer' THEN 1 ELSE 0 END) "
        "AS reviewer_runs, "
        "COALESCE(SUM(CASE WHEN agent_role = 'developer' "
        "THEN cost_usd ELSE 0 END), 0) AS developer_cost_usd, "
        "COALESCE(SUM(CASE WHEN agent_role = 'reviewer' "
        "THEN cost_usd ELSE 0 END), 0) AS reviewer_cost_usd, "
        "COALESCE(SUM(CASE WHEN agent_role = 'developer' "
        f"THEN COALESCE(cost_usd, 0) * ({AGENT_CACHE_FRACTION_SQL}) "
        "ELSE 0 END), 0) AS developer_cache_cost_usd, "
        "COALESCE(SUM(CASE WHEN agent_role = 'developer' "
        f"THEN COALESCE(cost_usd, 0) * (1 - ({AGENT_CACHE_FRACTION_SQL})) "
        "ELSE 0 END), 0) AS developer_no_cache_cost_usd, "
        "COALESCE(SUM(CASE WHEN agent_role = 'reviewer' "
        f"THEN COALESCE(cost_usd, 0) * ({AGENT_CACHE_FRACTION_SQL}) "
        "ELSE 0 END), 0) AS reviewer_cache_cost_usd, "
        "COALESCE(SUM(CASE WHEN agent_role = 'reviewer' "
        f"THEN COALESCE(cost_usd, 0) * (1 - ({AGENT_CACHE_FRACTION_SQL})) "
        "ELSE 0 END), 0) AS reviewer_no_cache_cost_usd "
        f"FROM analytics_agent_runs{where} "
        "GROUP BY bucket "
        "ORDER BY runs DESC, bucket ASC"
    )


def review_round_from_row(row: Sequence[Any]) -> ReviewRoundBucketRow:
    """Project one per-round aggregate row onto its result model."""
    query_row = review_round_row(row)
    return ReviewRoundBucketRow(
        bucket=str(query_row.bucket),
        runs=int(query_row.runs or 0),
        failed=int(query_row.failed or 0),
        total_cost_usd=float(query_row.total_cost_usd or 0),
        developer_runs=int(query_row.developer_runs or 0),
        reviewer_runs=int(query_row.reviewer_runs or 0),
        developer_cost_usd=float(query_row.developer_cost_usd or 0),
        reviewer_cost_usd=float(query_row.reviewer_cost_usd or 0),
        developer_cache_cost_usd=float(
            query_row.developer_cache_cost_usd or 0,
        ),
        developer_no_cache_cost_usd=float(
            query_row.developer_no_cache_cost_usd or 0,
        ),
        reviewer_cache_cost_usd=float(
            query_row.reviewer_cache_cost_usd or 0,
        ),
        reviewer_no_cache_cost_usd=float(
            query_row.reviewer_no_cache_cost_usd or 0,
        ),
    )


def review_round_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[ReviewRoundBucketRow]:
    """Return one aggregate row per review-round bucket in the window."""
    view_where, view_bindings = build_view_window_where(filters)
    view_where = append_where_condition(
        view_where,
        "agent_role IN ('developer', 'reviewer')",
    )
    rows = query.select(review_round_sql(view_where), view_bindings)
    return [review_round_from_row(row) for row in rows]
