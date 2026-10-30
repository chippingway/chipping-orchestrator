# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of the window's spend the price tables could actually account for.

Runs are grouped by where their cost came from, and the buckets are the usage
parser's own verdicts. `unknown-price` -- a model the price tables carry no
entry for -- is the one this read exists to surface, so it is never folded into
the `unknown` bucket a run with no recorded source falls to: one says a price
is missing and the other says a run is, and only the first is a table to
extend.

Each bucket carries the token volume beside the run count, because a source
covering few runs but most of the tokens is the one worth pricing first. The
volume is the runs' non-overlapping totals, and the runs whose total stays
unknown are counted beside it: a bucket of runs whose totals nothing settles
would otherwise read as one that spent no tokens at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_models import CostCoverageRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_view_window_where
from orchestrator.observability.analytics.query.token_totals import RUN_TOKEN_TOTAL_SQL


def cost_coverage_from_row(row: Sequence[Any]) -> CostCoverageRow:
    """Project one per-source coverage row onto its result model."""
    return CostCoverageRow(
        cost_source=str(row[0]),
        runs=int(row[1] or 0),
        total_tokens=int(row[2] or 0),
        unknown_token_runs=int(row[3] or 0),
    )


def cost_coverage_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[CostCoverageRow]:
    """Return one aggregate row per cost source in the window."""
    coverage_where, coverage_bindings = build_view_window_where(filters)
    rows = query.select(
        "SELECT "
        "COALESCE(cost_source, 'unknown') AS source_label, "
        "COUNT(*) AS runs, "
        f"{RUN_TOKEN_TOTAL_SQL} "
        f"FROM analytics_agent_runs{coverage_where} "
        "GROUP BY source_label "
        "ORDER BY runs DESC, source_label ASC",
        coverage_bindings,
    )
    return [cost_coverage_from_row(row) for row in rows]
