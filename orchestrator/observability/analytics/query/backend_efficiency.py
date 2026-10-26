# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How each agent backend performed across one window's runs.

Only finished runs count, so `event = 'agent_exit'` is spliced into the clause
rather than left to the caller's event selection -- and the caller's own event
filter is dropped from the window first, because a selection naming other
events would otherwise contradict the pinned one and leave the scan nothing to
match.

A run whose backend was never recorded still happened, so a NULL buckets under
`"unknown"` rather than vanishing from the comparison. The row-weighted mean
duration is recovered from the rollup's duration sum and count, and stays NULL
when nothing in the window carried one, so a page can hide the column instead
of showing a zero it would read as "instant". Ties on run count break on the
backend label so redrawing the same window returns the same order.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    AGENT_EXIT_CONDITION,
    append_where_condition,
)
from orchestrator.observability.analytics.query.cost_models import BackendEfficiencyRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.raw_values import float_or_none
from orchestrator.observability.analytics.query.row_cells import cost_cell


def backend_efficiency_sql(clause: str) -> str:
    """Build the per-backend run, failure, duration, and spend scan."""
    return (
        "SELECT "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "COALESCE(SUM(event_count), 0) AS runs, "
        "COALESCE(SUM(failed_count), 0) AS failed_runs, "
        "SUM(duration_s_sum) / NULLIF(SUM(duration_s_count), 0) "
        "  AS avg_dur, "
        "COALESCE(SUM(total_cost_usd), 0) AS backend_cost_usd, "
        "COALESCE(SUM(total_input_tokens), 0) AS backend_input_tokens, "
        "COALESCE(SUM(total_output_tokens), 0) AS backend_output_tokens, "
        "COALESCE(SUM(total_cache_read_tokens), 0) "
        "  AS backend_cache_read_tokens, "
        "COALESCE(SUM(total_cache_write_tokens), 0) "
        "  AS backend_cache_write_tokens "
        f"FROM {DAILY_ROLLUP_VIEW}{clause} "
        "GROUP BY backend_label "
        "ORDER BY runs DESC, backend_label ASC"
    )


def backend_efficiency_from_row(
    row: Sequence[Any],
) -> BackendEfficiencyRow:
    """Project one per-backend aggregate row onto its result model."""
    return BackendEfficiencyRow(
        backend=str(row[0]),
        runs=int(row[1] or 0),
        failed=int(row[2] or 0),
        avg_duration_s=float_or_none(row[3]),
        total_cost_usd=cost_cell(row, 4),
        total_input_tokens=int(row[5] or 0),
        total_output_tokens=int(row[6] or 0),
        total_cache_read_tokens=int(row[7] or 0),
        total_cache_write_tokens=int(row[8] or 0),
    )


def backend_efficiency_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[BackendEfficiencyRow]:
    """Return one aggregate row per backend in the selected window."""
    where, bindings = build_rollup_window_where(filters.without_events())
    clause = append_where_condition(where, AGENT_EXIT_CONDITION)
    rows = query.select(backend_efficiency_sql(clause), bindings)
    return [backend_efficiency_from_row(row) for row in rows]
