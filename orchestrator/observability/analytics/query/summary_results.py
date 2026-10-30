# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading the three tagged branches of one summary query back as a Summary.

The rows arrive interleaved and untyped -- a totals row, one row per event, one
row per stage -- so each branch is picked out by its `kind` tag rather than by
position, and a query that returned no totals row at all still answers with the
breakdowns it did return.

The two breakdowns are ranked here rather than in SQL: count descending with
the label breaking ties, so redrawing the same window cannot reshuffle a table,
and the insertion order of the returned mapping is the order a page iterates.

The totals row's counts are mapped column-by-column through a declared field
list rather than unpacked, so each lands on the field it names, with a NULL
aggregate reading as zero. The cost cohort and the token total follow them:
the cohort is read by `cost_cohorts.cost_cohort` from the cell after the
counts, and the known token total and its unknown runs close the row. The list,
the cohort, and the token pair are the width of the totals branch of the
SELECT, and a row of any other width raises rather than leaving a total it
never carried at its model default.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import COST_COHORT_WIDTH, cost_cohort
from orchestrator.observability.analytics.query.overview_models import Summary

SUMMARY_COUNT_FIELDS = (
    "total_events",
    "distinct_issues",
    "distinct_repos",
    "total_agent_runs",
    "failed_agent_runs",
    "timed_out_agent_runs",
)

# The kind and label cells lead the row; the counts follow them, then the
# cohort, then the known token total and the runs whose total is unknown.
_COHORT_START = 2 + len(SUMMARY_COUNT_FIELDS)

_TOKENS_START = _COHORT_START + COST_COHORT_WIDTH

_TOTALS_WIDTH = _TOKENS_START + 2


def summary_totals_row(rows: Sequence[tuple]) -> tuple | None:
    """Return the totals row emitted by the combined query, if present."""
    totals_row: tuple | None = None
    for row in rows:
        if row and row[0] == "t":
            totals_row = row
    return totals_row


def ordered_summary_counts(
    rows: Sequence[tuple],
    row_kind: str,
) -> dict[str, int]:
    """Convert one breakdown row kind to count-descending order."""
    counts = [
        (row[1], int(row[2] or 0))
        for row in rows
        if row and row[0] == row_kind and row[1] is not None
    ]
    counts.sort(key=summary_count_order)
    return dict(counts)


def summary_count_order(pair: tuple[str, int]) -> tuple[int, str]:
    """Rank one breakdown entry by count descending, then by label."""
    return -pair[1], pair[0]


def summary_total_values(totals_row: tuple) -> dict[str, Any]:
    """Map the totals columns to typed Summary field values."""
    if len(totals_row) != _TOTALS_WIDTH:
        raise ValueError(f"a summary totals row is {_TOTALS_WIDTH} cells; this one holds {len(totals_row)}")
    counts = zip(SUMMARY_COUNT_FIELDS, totals_row[2:_COHORT_START], strict=True)
    return {
        **{field_name: int(raw_count or 0) for field_name, raw_count in counts},
        "cost": cost_cohort(totals_row, _COHORT_START),
        "total_tokens": int(totals_row[_TOKENS_START] or 0),
        "unknown_token_runs": int(totals_row[_TOKENS_START + 1] or 0),
    }


def summary_from_rows(rows: Sequence[tuple]) -> Summary:
    """Convert combined-query rows into the public Summary model."""
    by_event = ordered_summary_counts(rows, "e")
    by_stage = ordered_summary_counts(rows, "s")
    totals_row = summary_totals_row(rows)
    if totals_row is None:
        return Summary(by_event=by_event, by_stage=by_stage)
    return Summary(
        by_event=by_event,
        by_stage=by_stage,
        **summary_total_values(totals_row),
    )
