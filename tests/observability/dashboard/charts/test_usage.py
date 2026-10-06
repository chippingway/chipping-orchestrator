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
from orchestrator.observability.dashboard.charts import usage

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

_AGENT_EXIT = "agent_exit"

_COST_TRACE = "Cost"

# What the hero panel is pinned to (px): the slot above the KPI strip is laid
# out around it, as opposed to Plotly's own much taller default.
_HERO_HEIGHT = 330

_COST_USD = 1.2

_INPUT_TOKENS = 1_000

_OUTPUT_TOKENS = 500

_POINTS = tuple(
    TimeSeriesPoint(
        day=day,
        event=_AGENT_EXIT,
        count=1,
        cost_usd=_COST_USD,
        input_tokens=_INPUT_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
    )
    for day in (_DAY, _NEXT_DAY)
)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class UsageOverTimeTest(unittest.TestCase):
    """What the assembled figure carries, and what an empty window gets."""

    def test_the_stack_and_the_overlay_are_one_figure(self) -> None:
        # The cost line is added after the bands and rides the axis the layout
        # gave it, so a day's spend is read off the dollar scale over the same
        # x-axis its tokens are stacked on rather than a panel away.
        figure = usage.usage_over_time(_POINTS)
        names = [trace.name for trace in figure.data]
        self.assertEqual(names[-1], _COST_TRACE)
        self.assertGreater(len(names), 1)
        cost = next(
            trace for trace in figure.data if trace.name == _COST_TRACE
        )
        self.assertEqual(cost.yaxis, "y2")
        self.assertIsNotNone(figure.layout.yaxis2.range)

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
