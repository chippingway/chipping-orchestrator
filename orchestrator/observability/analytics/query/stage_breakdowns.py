# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one workflow stage cost, and how much of that spend was cached.

The rollup stores duration as a sum and a count rather than an average, because
averaging per-day averages would weight a quiet day the same as a busy one; the
row-weighted mean is recovered here as `SUM(sum) / SUM(count)`, and a stage no
row carried a duration for divides by a guarded zero so the answer stays NULL
rather than becoming a zero a panel would render as "instant".

Cost is reported three ways -- the total, and the cache / no-cache split
`cache_shares` weights each bucket by -- so a panel can stack the two bands and
still have them sum back to the total. The `runs` count beside them narrows to
`event = 'agent_exit'` under the same predicate as the totals, so the sub-line
a panel labels "runs" is scoped to the same rows as the cost above it.

Buckets with no stage are excluded, since a row a page has no stage to file
under would land in an unlabelled bar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cache_shares import (
    ROLLUP_CACHE_FRACTION_SQL,
)
from orchestrator.observability.analytics.query.conditions import append_where_condition
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.raw_values import float_or_none
from orchestrator.observability.analytics.query.row_cells import cost_cell
from orchestrator.observability.analytics.query.run_models import StageBreakdown


def stage_breakdown_sql(clause: str) -> str:
    """Build the per-stage activity, cost, and cache-split scan."""
    return (
        "SELECT stage, "
        "COALESCE(SUM(event_count), 0) AS c, "
        "SUM(duration_s_sum) / NULLIF(SUM(duration_s_count), 0) "
        "  AS avg_dur, "
        "COALESCE(SUM(total_cost_usd), 0) AS stage_cost_usd, "
        "COALESCE(SUM(total_input_tokens), 0) AS stage_input_tokens, "
        "COALESCE(SUM(total_output_tokens), 0) AS stage_output_tokens, "
        "COALESCE(SUM(CASE WHEN event = 'agent_exit' "
        "                  THEN event_count ELSE 0 END), 0) "
        "  AS stage_agent_runs, "
        "COALESCE(SUM(COALESCE(total_cost_usd, 0) "
        f"* ({ROLLUP_CACHE_FRACTION_SQL})), 0) AS stage_cache_cost_usd, "
        "COALESCE(SUM(COALESCE(total_cost_usd, 0) "
        f"* (1 - ({ROLLUP_CACHE_FRACTION_SQL}))), 0) "
        "AS stage_no_cache_cost_usd "
        f"FROM {DAILY_ROLLUP_VIEW}{clause} "
        "GROUP BY stage ORDER BY c DESC, stage ASC"
    )


def stage_breakdown_from_row(row: Sequence[Any]) -> StageBreakdown:
    """Project one per-stage aggregate row onto its result model."""
    return StageBreakdown(
        stage=row[0],
        count=int(row[1]),
        avg_duration_s=float_or_none(row[2]),
        total_cost_usd=cost_cell(row, 3),
        total_input_tokens=int(row[4] or 0),
        total_output_tokens=int(row[5] or 0),
        runs=int(row[6] or 0),
        cache_cost_usd=cost_cell(row, 7),
        no_cache_cost_usd=cost_cell(row, 8),
    )


def stage_breakdown_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[StageBreakdown]:
    """Return one aggregate row per stage in the selected window."""
    where, bindings = build_rollup_window_where(filters)
    clause = append_where_condition(where, "stage IS NOT NULL")
    rows = query.select(stage_breakdown_sql(clause), bindings)
    return [stage_breakdown_from_row(row) for row in rows]
