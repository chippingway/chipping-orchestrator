# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One window's volume, spend, and tokens laid out day by day and event.

The rollup is already keyed on the day, so the bucket a chart plots is the
grouping key itself rather than a truncation computed at scan time. Cost and
the four token bands come back on the same cell as the count, which is what
lets the volume, spend, and token charts pivot one result instead of asking
three times for the same window.

Rows come back ascending by day and then by event, so a chart reads its series
left to right and stacks its bands in the same order on every redraw.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.overview_models import TimeSeriesPoint
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.row_cells import cost_cell, day_value


def time_series_from_row(row: Sequence[Any]) -> TimeSeriesPoint:
    """Project one `(day, event)` cell onto its result model."""
    return TimeSeriesPoint(
        day=day_value(row[0]),
        event=row[1],
        count=int(row[2]),
        cost_usd=cost_cell(row, 3),
        input_tokens=int(row[4] or 0),
        output_tokens=int(row[5] or 0),
        cache_read_tokens=int(row[6] or 0),
        cache_write_tokens=int(row[7] or 0),
    )


def time_series_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[TimeSeriesPoint]:
    """Return one cell per `(day, event)` pair in the selected window."""
    where, bindings = build_rollup_window_where(filters)
    rows = query.select(
        "SELECT day, event, "
        "COALESCE(SUM(event_count), 0) AS c, "
        "COALESCE(SUM(total_cost_usd), 0) AS day_cost_usd, "
        "COALESCE(SUM(total_input_tokens), 0) AS day_input_tokens, "
        "COALESCE(SUM(total_output_tokens), 0) AS day_output_tokens, "
        "COALESCE(SUM(total_cache_read_tokens), 0) "
        "  AS day_cache_read_tokens, "
        "COALESCE(SUM(total_cache_write_tokens), 0) "
        "  AS day_cache_write_tokens "
        f"FROM {DAILY_ROLLUP_VIEW}{where} "
        "GROUP BY day, event "
        "ORDER BY day ASC, event ASC",
        bindings,
    )
    return [time_series_from_row(row) for row in rows]
