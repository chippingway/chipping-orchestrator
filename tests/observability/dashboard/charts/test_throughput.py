# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-day strip: the calendar behind it, its bars, and its empty window."""
from __future__ import annotations

import unittest
from datetime import date
from importlib.util import find_spec

from orchestrator.observability.analytics.query.activity_models import (
    ThroughputDayRow,
)
from orchestrator.observability.dashboard.charts import throughput

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_DAY1 = date(_YEAR, 5, 1)

_DAY2 = date(_YEAR, 5, 2)

_DAY3 = date(_YEAR, 5, 3)

_DAY4 = date(_YEAR, 5, 4)

_DAY5 = date(_YEAR, 5, 5)

# Two resolved days three days apart, so the pair the read returns and the
# calendar a window fills between them cannot be the same list.
_ROWS = (
    ThroughputDayRow(day=_DAY1, resolved=2, rejected=0),
    ThroughputDayRow(day=_DAY4, resolved=3, rejected=1),
)

# What the strip is pinned to (px): the thin height the reliability column is
# laid out around, as opposed to Plotly's own much taller default.
_THROUGHPUT_HEIGHT = 150


def _resolved_bars(fig):
    """The single bar trace the strip is drawn as, keyed by day."""
    return fig.data[0]


class ThroughputSeriesTest(unittest.TestCase):
    """Which days a strip gets a bar for, and what each bar counts."""

    def test_bounds_are_a_calendar_and_both_included(self) -> None:
        self.assertEqual(
            throughput.calendar_days(_DAY1, _DAY3), [_DAY1, _DAY2, _DAY3],
        )
        # Both bounds are inclusive, so a one-day window is one bar rather
        # than an empty range the strip would answer with a placeholder.
        self.assertEqual(throughput.calendar_days(_DAY1, _DAY1), [_DAY1])

    def test_bounds_fill_the_days_no_row_named(self) -> None:
        # The read only returns days that carried a resolving row, so a day
        # nobody finished anything on is absent rather than zero. Filling the
        # window is what keeps three busy days from reading as a steady week.
        series = throughput.throughput_series(_ROWS, _DAY1, _DAY5)
        self.assertEqual(
            tuple(series.days), (_DAY1, _DAY2, _DAY3, _DAY4, _DAY5),
        )
        self.assertEqual(tuple(series.resolved), (2, 0, 0, 3, 0))

    def test_a_window_with_no_rows_is_a_calendar(self) -> None:
        series = throughput.throughput_series((), _DAY1, _DAY3)
        self.assertEqual(tuple(series.days), (_DAY1, _DAY2, _DAY3))
        self.assertEqual(tuple(series.resolved), (0, 0, 0))

    def test_without_bounds_the_rows_are_the_calendar(self) -> None:
        # A caller with no window to hand still gets a strip, in day order,
        # and one bound alone is not a range to fill between.
        for bounds in ((None, None), (_DAY1, None), (None, _DAY5)):
            with self.subTest(bounds=bounds):
                series = throughput.throughput_series(_ROWS, *bounds)
                self.assertEqual(tuple(series.days), (_DAY1, _DAY4))
                self.assertEqual(tuple(series.resolved), (2, 3))


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class ThroughputFigureTest(unittest.TestCase):
    """The figure that series is drawn as: its bars, height, and empty case."""

    def test_the_bars_are_drawn_from_the_series(self) -> None:
        fig = throughput.done_per_day_bars(
            _ROWS, window_start=_DAY1, window_end=_DAY5,
        )
        series = throughput.throughput_series(_ROWS, _DAY1, _DAY5)
        bars = _resolved_bars(fig)
        self.assertEqual(tuple(bars.x), tuple(series.days))
        self.assertEqual(tuple(bars.y), tuple(series.resolved))

    def test_the_resolved_column_is_what_a_bar_counts(self) -> None:
        # `rejected` rides along on the row; a bar sized off it, or off the
        # two summed, would report a throughput the operator never had.
        bars = _resolved_bars(throughput.done_per_day_bars(_ROWS))
        self.assertEqual(tuple(bars.x), (_DAY1, _DAY4))
        self.assertEqual(tuple(bars.y), (2, 3))

    def test_no_days_is_answered_with_the_placeholder(self) -> None:
        # Reachable only without bounds: a window always has days. The
        # placeholder carries the strip's height so an empty reliability card
        # cannot stand taller than the drawn one beside it.
        fig = throughput.done_per_day_bars(())
        self.assertGreaterEqual(len(fig.layout.annotations), 1)
        self.assertEqual(fig.layout.height, _THROUGHPUT_HEIGHT)

    def test_the_height_is_pinned_to_the_thin_strip(self) -> None:
        fig = throughput.done_per_day_bars(_ROWS)
        self.assertEqual(fig.layout.height, _THROUGHPUT_HEIGHT)
        self.assertEqual(fig.layout.yaxis.title.text, "resolved")


if __name__ == "__main__":
    unittest.main()
