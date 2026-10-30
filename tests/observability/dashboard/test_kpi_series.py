# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which rows a sparkline is plotted over, and what it counts on each.

A day's spend is the amount its runs state, every basis added, and a day's
tokens its runs' known non-overlapping totals -- the readings the tiles above
the lines report for the whole window, so a line can never sit below or above
its own headline.

The series cases are about the day axis rather than the arithmetic: a day the
activity series recorded twice is one point, a day it recorded with no
resolutions still holds its place in all three lines, and a resolution dated
outside those days is not a fourth point on three-point lines.
"""

from __future__ import annotations

import math
import unittest
from datetime import date

from orchestrator.observability.analytics.query.activity_models import (
    ThroughputDayRow,
)
from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard import kpi_series
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.dashboard_test_support import (
    MAY01,
    MAY02,
    MAY03,
)

_EVENT = "agent_exit"

_FIRST_TOKENS = 1_000

_SECOND_TOKENS = 20

_RESOLVED = 2

_REJECTED = 3


def _point(day: date, *costs, total_tokens: int = 0, unknown_token_runs: int = 0) -> TimeSeriesPoint:
    """One activity cell whose runs state `costs`, carrying the known tokens it is given."""
    return TimeSeriesPoint(
        day=day,
        event=_EVENT,
        count=len(costs),
        cost=cohort_cases.cohort(*costs),
        total_tokens=total_tokens,
        unknown_token_runs=unknown_token_runs,
    )


class DailyPointTotalsTest(unittest.TestCase):
    """What one day of the line counts."""

    def test_a_day_sums_its_event_rows(self) -> None:
        # The series carries a row per day and event, so the spend and tokens a
        # day is drawn at are filled in over all of them: every basis's amount
        # added, a subtotal's included, and the known tokens alone.
        totals = kpi_series.daily_point_totals((
            _point(MAY01, cases.REPORTED, cases.GEMINI_ESTIMATE, total_tokens=_FIRST_TOKENS),
            _point(MAY01, cases.INCOMPLETE_SUBTOTAL, total_tokens=_SECOND_TOKENS, unknown_token_runs=3),
        ))
        day_cost, day_tokens = totals[MAY01]
        stated = cases.REPORTED_USD + cases.GEMINI_USD + cases.SUBTOTAL_USD
        self.assertTrue(math.isclose(day_cost, stated))
        self.assertEqual(day_tokens, float(_FIRST_TOKENS + _SECOND_TOKENS))

    def test_a_day_stating_no_amount_adds_nothing(self) -> None:
        # An unpriced run, one with no usage, and a day of stage events state no
        # amount, so they add nothing rather than an amount nobody stated.
        totals = kpi_series.daily_point_totals((
            _point(MAY01, cases.UNPRICED),
            _point(MAY01, cases.NO_USAGE),
            _point(MAY01),
        ))
        self.assertEqual(totals, {MAY01: [float(0), float(0)]})


class ThroughputTotalsTest(unittest.TestCase):
    """The pair the reliability tiles beneath the strip are also reported by."""

    def test_both_counts_are_summed_over_the_window(self) -> None:
        rows = (
            ThroughputDayRow(day=MAY01, resolved=_RESOLVED, rejected=0),
            ThroughputDayRow(day=MAY02, resolved=0, rejected=_REJECTED),
        )
        self.assertEqual(
            kpi_series.throughput_totals(rows), (_RESOLVED, _REJECTED),
        )

    def test_a_window_with_no_days_is_zero(self) -> None:
        self.assertEqual(kpi_series.throughput_totals(()), (0, 0))


class DailyKpiSeriesTest(unittest.TestCase):
    """The three lines, and the days they are plotted over."""

    def test_the_days_come_off_the_series(self) -> None:
        # A day with runs but no resolutions keeps its place in all three
        # lines, and a resolution dated outside those days is not a fourth
        # point on three-point lines.
        series = kpi_series.daily_kpi_series(
            ts_points=(
                _point(MAY02, cases.GEMINI_ESTIMATE, total_tokens=_SECOND_TOKENS),
                _point(MAY01, cases.REPORTED, total_tokens=_FIRST_TOKENS),
            ),
            throughput_rows=(
                ThroughputDayRow(day=MAY01, resolved=_RESOLVED, rejected=0),
                ThroughputDayRow(day=MAY03, resolved=_RESOLVED, rejected=0),
            ),
        )
        self.assertEqual(series.cost, [cases.REPORTED_USD, cases.GEMINI_USD])
        self.assertEqual(series.tokens, [float(_FIRST_TOKENS), float(_SECOND_TOKENS)])
        self.assertEqual(series.done, [_RESOLVED, 0])

    def test_a_window_with_no_activity_is_empty(self) -> None:
        series = kpi_series.daily_kpi_series(ts_points=(), throughput_rows=())
        self.assertEqual(
            (series.cost, series.tokens, series.done), ([], [], []),
        )


if __name__ == "__main__":
    unittest.main()
