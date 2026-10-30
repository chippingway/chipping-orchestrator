# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hero figure the usage owners are assembled into."""
from __future__ import annotations

import unittest
from datetime import date
from importlib.util import find_spec

from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard.charts import usage, usage_bands
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

_AGENT_EXIT = "agent_exit"

_COST_TRACE = "Cost"

_UNKNOWN_TRACE = "Token total unknown"

_CLAUDE = "claude"

# What the hero panel is pinned to (px): the slot above the KPI strip is laid
# out around it, as opposed to Plotly's own much taller default.
_HERO_HEIGHT = 330

_KNOWN_TOKENS = 1_500

_OUTPUT_TOKENS = 500

# Two reported days, the second holding a run whose token total is unknown.
_POINTS = tuple(
    TimeSeriesPoint(
        day=day,
        event=_AGENT_EXIT,
        count=2,
        cost=cohort_cases.cohort(cases.REPORTED, cases.REPORTED),
        total_tokens=_KNOWN_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
        unknown_token_runs=unknown,
    )
    for day, unknown in ((_DAY, 0), (_NEXT_DAY, 1))
)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class UsageOverTimeTest(unittest.TestCase):
    """What the assembled figure carries, and what an empty window gets."""

    def test_the_stack_and_the_overlay_are_one_figure(self) -> None:
        # The cost line is added after the bands and rides the axis the layout
        # gave it, so a day's spend is read off the dollar scale over the same
        # x-axis its tokens are stacked on rather than a panel away.
        # The marker naming a day's stack a subtotal sits between them, on top
        # of the stack it qualifies.
        figure = usage.usage_over_time(_POINTS)
        names = [trace.name for trace in figure.data]
        self.assertEqual(names, ["Uncached input", "Output", "Cache", _UNKNOWN_TRACE, _COST_TRACE])
        cost = next(
            trace for trace in figure.data if trace.name == _COST_TRACE
        )
        self.assertEqual(cost.yaxis, "y2")
        self.assertIsNotNone(figure.layout.yaxis2.range)

    def test_a_backend_subtotal_is_marked(self) -> None:
        # The per-backend read lands a wave after the series, so a run of
        # unknown total the series never counted still marks the backend stack
        # drawn from that read, at the stack's own height.
        day_tokens = {_DAY: {_CLAUDE: float(_KNOWN_TOKENS)}}
        backend_rows = usage_bands.BackendDailyTokens(day_tokens, {_DAY: 1})
        figure = usage.usage_over_time(
            _POINTS[:1],
            backend_rows_by_day=backend_rows,
            mode=usage_bands.BACKEND_MODE,
        )
        names = [trace.name for trace in figure.data]
        self.assertEqual(names, [_CLAUDE, _UNKNOWN_TRACE, _COST_TRACE])
        self.assertEqual(figure.data[1].y[0], _KNOWN_TOKENS)

    def test_an_unpriced_day_is_marked_apart(self) -> None:
        # The cost line leaves the unpriced day as a gap, and the marker that
        # keeps its reading hoverable is drawn beneath the line rather than
        # joined into it.
        unpriced = TimeSeriesPoint(
            day=_NEXT_DAY,
            event=_AGENT_EXIT,
            count=1,
            cost=cohort_cases.cohort(cases.UNPRICED),
            total_tokens=_KNOWN_TOKENS,
        )
        figure = usage.usage_over_time((_POINTS[0], unpriced))
        names = [trace.name for trace in figure.data]
        self.assertEqual(names, ["Uncached input", "Output", "Cache", "Cost not stated", _COST_TRACE])
        cost = figure.data[-1]
        self.assertIsNone(cost.y[-1])

    def test_a_window_with_no_rows_is_the_placeholder(self) -> None:
        figure = usage.usage_over_time(())
        self.assertEqual(len(figure.data), 0)
        self.assertGreaterEqual(len(figure.layout.annotations), 1)

    def test_the_hero_height_is_pinned_on_either_path(self) -> None:
        # The empty state has to answer at the drawn height too: a "no events"
        # card falling back to Plotly's default would dwarf the KPI strip the
        # panel above it is sized against.
        for points in (_POINTS, ()):
            with self.subTest(rows=len(points)):
                self.assertEqual(
                    usage.usage_over_time(points).layout.height, _HERO_HEIGHT,
                )


if __name__ == "__main__":
    unittest.main()
