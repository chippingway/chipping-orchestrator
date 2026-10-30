# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the work happened, as a weekday-by-hour cell in the chosen zone.

The hour of day is the one thing the day-bucketed rollup rounded away, so these
cells are counted off the events table itself. The offset a caller picks is
bound as a parameter and never spliced into the text, and `ts` is normalized to
UTC before that offset is added: a database session whose own timezone is not
UTC would otherwise shift every bucket a second time and quietly re-label which
hours were busy.

Each cell carries the token volume beside the event count so a page can render
intensity by spend, which is what keeps the many cheap stage rows from
outweighing the few agent runs that actually cost the money. That volume is the
agent runs' non-overlapping totals, every other event stating none, and the
runs whose total stays unknown are counted beside it, so a cell holding one
reads as a subtotal rather than as the hour's whole volume.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.activity_models import (
    HourlyHeatmapPoint,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.token_totals import EVENT_TOKEN_TOTAL_SQL


def hourly_heatmap_from_row(row: Sequence[Any]) -> HourlyHeatmapPoint:
    """Project one weekday-by-hour cell onto its result model."""
    return HourlyHeatmapPoint(
        weekday=int(row[0]),
        hour=int(row[1]),
        count=int(row[2] or 0),
        total_tokens=int(row[3] or 0),
        unknown_token_runs=int(row[4] or 0),
    )


def hourly_heatmap_rows(
    query: ReadQuery,
    filters: WindowFilters,
    tz_offset_hours: int,
) -> list[HourlyHeatmapPoint]:
    """Return one activity cell per weekday and hour in the window."""
    heatmap_where, heatmap_bindings = build_window_where(filters)
    offset = int(tz_offset_hours)
    rows = query.select(
        "SELECT "
        "EXTRACT(DOW FROM ((ts AT TIME ZONE 'UTC') "
        "+ %s * INTERVAL '1 hour'))::int AS weekday, "
        "EXTRACT(HOUR FROM ((ts AT TIME ZONE 'UTC') "
        "+ %s * INTERVAL '1 hour'))::int AS hour, "
        "COUNT(*) AS c, "
        f"{EVENT_TOKEN_TOTAL_SQL} "
        f"FROM analytics_events{heatmap_where} "
        "GROUP BY weekday, hour "
        "ORDER BY weekday ASC, hour ASC",
        [offset, offset, *heatmap_bindings],
    )
    return [hourly_heatmap_from_row(row) for row in rows]
