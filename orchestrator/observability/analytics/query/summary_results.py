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

The totals row is mapped column-by-column through a declared cast list rather
than unpacked, so each total is cast to the type its field declares, with a
NULL aggregate reading as zero. The list and the totals branch of the SELECT
are the same width, and a row of any other width raises rather than leaving a
total it never carried at its model default.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.overview_models import Summary

SUMMARY_TOTAL_FIELD_CASTS = (
    ("total_events", int),
    ("distinct_issues", int),
    ("distinct_repos", int),
    ("total_cost_usd", float),
    ("total_input_tokens", int),
    ("total_output_tokens", int),
    ("total_agent_runs", int),
    ("failed_agent_runs", int),
    ("total_cache_read_tokens", int),
    ("total_cache_write_tokens", int),
    ("timed_out_agent_runs", int),
)


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
    return {
        field_name: field_cast(raw_value or 0)
        for (field_name, field_cast), raw_value in zip(
            SUMMARY_TOTAL_FIELD_CASTS,
            totals_row[2:],
            strict=True,
        )
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
