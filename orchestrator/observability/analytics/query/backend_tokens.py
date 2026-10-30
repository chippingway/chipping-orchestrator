# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each backend spent in tokens, day by day across the window.

The series is aggregated off the agent-run view rather than assembled from the
newest-runs read a table elsewhere on the page is drawn from, so every run in
the window is counted instead of the capped subset that read returns -- a
backend busy early in a long window would otherwise flatten toward zero as the
cap trimmed its runs away. That keeps the per-day stack in lockstep with the
cost line and the window totals beside it.

Each band a chart stacks is one `(day, backend)` cell, and a run that recorded
no backend buckets under `unknown` rather than dropping out of the day's total.
A cell's volume is the runs' non-overlapping totals, so a Codex run's cached
input is not counted a second time beside the input that holds it, and the runs
whose total stays unknown are counted beside it rather than summed as zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.activity_models import (
    BackendDailyTokensRow,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_view_window_where
from orchestrator.observability.analytics.query.row_cells import day_value
from orchestrator.observability.analytics.query.token_totals import RUN_TOKEN_TOTAL_SQL


def backend_daily_tokens_from_row(
    row: Sequence[Any],
) -> BackendDailyTokensRow:
    """Project one per-day-and-backend token row onto its result model."""
    return BackendDailyTokensRow(
        day=day_value(row[0]),
        backend=str(row[1]),
        total_tokens=int(row[2] or 0),
        unknown_token_runs=int(row[3] or 0),
    )


def backend_daily_token_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[BackendDailyTokensRow]:
    """Return one token total per `(day, backend)` cell in the window."""
    daily_where, daily_bindings = build_view_window_where(filters)
    rows = query.select(
        "SELECT "
        "date_trunc('day', ts)::date AS day, "
        "COALESCE(backend, 'unknown') AS backend_label, "
        f"{RUN_TOKEN_TOTAL_SQL} "
        f"FROM analytics_agent_runs{daily_where} "
        "GROUP BY day, backend_label "
        "ORDER BY day ASC, backend_label ASC",
        daily_bindings,
    )
    return [backend_daily_tokens_from_row(row) for row in rows]
