# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One window's volume, spend, and tokens laid out day by day and event.

The rollup is already keyed on the day, so the bucket a chart plots is the
grouping key itself rather than a truncation computed at scan time. Spend and
tokens come back on the same cell as the count, which is what lets the volume,
spend, and token charts pivot one result instead of asking three times for the
same window.

Spend is the rollup's cost cohort (`cost_cohorts.ROLLUP_COST_COHORT_SQL`), so
a day's amount keeps its bases and its completeness apart rather than summing
`total_cost_usd`. Tokens are the runs' known non-overlapping totals with the
runs whose total is unknown beside them (`token_totals.ROLLUP_TOKEN_TOTAL_SQL`),
followed by the cache and output counters inside those known totals: a stack
of uncached input, output, and cache drawn off those three is as tall as the
known total, never a Codex run's cached input once in its input and again in
its cache. The raw counter sums are not read at all, since only the evidence
says which of them overlap.

Rows come back ascending by day and then by event, so a chart reads its series
left to right and stacks its bands in the same order on every redraw.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import (
    COST_COHORT_WIDTH,
    ROLLUP_COST_COHORT_SQL,
    cost_cohort,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.overview_models import TimeSeriesPoint
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.row_cells import day_value
from orchestrator.observability.analytics.query.token_totals import ROLLUP_TOKEN_TOTAL_SQL

# The day, event, and count lead a cell; the cohort follows them, then the
# known token total, its unknown runs, and the cache and output inside it.
_COHORT_START = 3

_TOKENS_START = _COHORT_START + COST_COHORT_WIDTH


def time_series_sql(where: str) -> str:
    """Build the per-`(day, event)` scan a series is read off."""
    return (
        "SELECT day, event, "
        "COALESCE(SUM(event_count), 0) AS c, "
        f"{ROLLUP_COST_COHORT_SQL}, "
        f"{ROLLUP_TOKEN_TOTAL_SQL}, "
        "COALESCE(SUM(cache_tokens_in_total), 0), "
        "COALESCE(SUM(output_tokens_in_total), 0) "
        f"FROM {DAILY_ROLLUP_VIEW}{where} "
        "GROUP BY day, event "
        "ORDER BY day ASC, event ASC"
    )


def time_series_from_row(row: Sequence[Any]) -> TimeSeriesPoint:
    """Project one `(day, event)` cell onto its result model."""
    total_tokens, unknown_runs, cache_tokens, output_tokens = row[_TOKENS_START:_TOKENS_START + 4]
    return TimeSeriesPoint(
        day=day_value(row[0]),
        event=row[1],
        count=int(row[2]),
        cost=cost_cohort(row, _COHORT_START),
        total_tokens=int(total_tokens or 0),
        unknown_token_runs=int(unknown_runs or 0),
        cache_tokens=int(cache_tokens or 0),
        output_tokens=int(output_tokens or 0),
    )


def time_series_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[TimeSeriesPoint]:
    """Return one cell per `(day, event)` pair in the selected window."""
    where, bindings = build_rollup_window_where(filters)
    rows = query.select(time_series_sql(where), bindings)
    return [time_series_from_row(row) for row in rows]
