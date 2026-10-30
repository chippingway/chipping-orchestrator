# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one workflow stage cost, and how that spend divides by token share.

The rollup stores duration as a sum and a count rather than an average, because
averaging per-day averages would weight a quiet day the same as a busy one; the
row-weighted mean is recovered here as `SUM(sum) / SUM(count)`, and a stage no
row carried a duration for divides by a guarded zero so the answer stays NULL
rather than becoming a zero a panel would render as "instant".

Spend is the stage's cost cohort (`cost_cohorts.ROLLUP_COST_COHORT_SQL`), so
its bases, its rate dates, and the runs it leaves unpriced or states no
evidence for stay apart rather than summing `total_cost_usd`. Tokens are the
runs' declared non-overlapping totals with the runs whose total is unknown
beside them (`token_totals.ROLLUP_TOKEN_TOTAL_SQL`). The stated amount is also
cut into the three `cache_shares` bands -- the cache tokens' share, the rest,
and what no declared total could split -- so a panel can stack them back to
the stage's stated amount without passing the allocation off as a cache
charge. The `runs` count narrows to `event = 'agent_exit'` under the same
predicate as the cohort, so the sub-line a panel labels "runs" is scoped to the
same rows as the cost beside it.

Buckets with no stage are excluded, since a row a page has no stage to file
under would land in an unlabelled bar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cache_shares import ROLLUP_TOKEN_SHARE_SQL, token_share_bands
from orchestrator.observability.analytics.query.conditions import append_where_condition
from orchestrator.observability.analytics.query.cost_cohorts import (
    COST_COHORT_WIDTH,
    ROLLUP_COST_COHORT_SQL,
    cost_cohort,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.raw_values import float_or_none
from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.analytics.query.token_totals import ROLLUP_TOKEN_TOTAL_SQL

# The stage, its event count, mean duration, and run count lead a row; the
# cohort follows them, then the known token total and its unknown runs, and
# the token-share bands close it.
_COHORT_START = 4

_TOKENS_START = _COHORT_START + COST_COHORT_WIDTH

_BANDS_START = _TOKENS_START + 2


def stage_breakdown_sql(clause: str) -> str:
    """Build the per-stage activity, cost, token, and token-share scan."""
    return (
        "SELECT stage, "
        "COALESCE(SUM(event_count), 0) AS c, "
        "SUM(duration_s_sum) / NULLIF(SUM(duration_s_count), 0) "
        "  AS avg_dur, "
        "COALESCE(SUM(CASE WHEN event = 'agent_exit' "
        "                  THEN event_count ELSE 0 END), 0) "
        "  AS stage_agent_runs, "
        f"{ROLLUP_COST_COHORT_SQL}, "
        f"{ROLLUP_TOKEN_TOTAL_SQL}, "
        f"{ROLLUP_TOKEN_SHARE_SQL} "
        f"FROM {DAILY_ROLLUP_VIEW}{clause} "
        "GROUP BY stage ORDER BY c DESC, stage ASC"
    )


def stage_breakdown_from_row(row: Sequence[Any]) -> StageBreakdown:
    """Project one per-stage aggregate row onto its result model."""
    known_tokens, unknown_runs = row[_TOKENS_START:_BANDS_START]
    return StageBreakdown(
        stage=row[0],
        count=int(row[1]),
        avg_duration_s=float_or_none(row[2]),
        runs=int(row[3] or 0),
        cost=cost_cohort(row, _COHORT_START),
        total_tokens=int(known_tokens or 0),
        unknown_token_runs=int(unknown_runs or 0),
        bands=token_share_bands(row, _BANDS_START),
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
