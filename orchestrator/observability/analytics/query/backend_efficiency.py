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

Spend is the backend's cost cohort (`cost_cohorts.ROLLUP_COST_COHORT_SQL`), so
an Antigravity backend's Gemini API token estimate, a CLI-reported amount, and
the runs a backend left unpriced stay apart. The tokens a ratio divides by are the
runs' declared non-overlapping totals with the runs whose total is unknown
beside them (`token_totals.ROLLUP_TOKEN_TOTAL_SQL`), followed by the rollup's
cache and output counters inside those known totals: the input side a cache
share is taken of is the known total less its output, so a Codex run's cached
input is counted once, inside its input. The raw counter sums are not read,
since only the evidence says which of them overlap.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    AGENT_EXIT_CONDITION,
    append_where_condition,
)
from orchestrator.observability.analytics.query.cost_cohorts import (
    COST_COHORT_WIDTH,
    ROLLUP_COST_COHORT_SQL,
    cost_cohort,
)
from orchestrator.observability.analytics.query.cost_models import BackendEfficiencyRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import (
    DAILY_ROLLUP_VIEW,
    build_rollup_window_where,
)
from orchestrator.observability.analytics.query.raw_values import float_or_none
from orchestrator.observability.analytics.query.token_totals import ROLLUP_TOKEN_TOTAL_SQL

# The backend, its runs, failures, and mean duration lead a row; the cohort
# follows them, then the known token total, its unknown runs, and the cache
# and output inside it.
_COHORT_START = 4

_TOKENS_START = _COHORT_START + COST_COHORT_WIDTH


def backend_efficiency_sql(clause: str) -> str:
    """Build the per-backend run, failure, duration, spend, and token scan."""
    return (
        "SELECT "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "COALESCE(SUM(event_count), 0) AS runs, "
        "COALESCE(SUM(failed_count), 0) AS failed_runs, "
        "SUM(duration_s_sum) / NULLIF(SUM(duration_s_count), 0) "
        "  AS avg_dur, "
        f"{ROLLUP_COST_COHORT_SQL}, "
        f"{ROLLUP_TOKEN_TOTAL_SQL}, "
        "COALESCE(SUM(cache_tokens_in_total), 0), "
        "COALESCE(SUM(output_tokens_in_total), 0) "
        f"FROM {DAILY_ROLLUP_VIEW}{clause} "
        "GROUP BY backend_label "
        "ORDER BY runs DESC, backend_label ASC"
    )


def backend_efficiency_from_row(
    row: Sequence[Any],
) -> BackendEfficiencyRow:
    """Project one per-backend aggregate row onto its result model."""
    known_tokens, unknown_runs, cache_tokens, output_tokens = row[_TOKENS_START:_TOKENS_START + 4]
    return BackendEfficiencyRow(
        backend=str(row[0]),
        runs=int(row[1] or 0),
        failed=int(row[2] or 0),
        avg_duration_s=float_or_none(row[3]),
        cost=cost_cohort(row, _COHORT_START),
        total_tokens=int(known_tokens or 0),
        unknown_token_runs=int(unknown_runs or 0),
        cache_tokens=int(cache_tokens or 0),
        output_tokens=int(output_tokens or 0),
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
