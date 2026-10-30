# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The maxima a usage figure's two axes are scaled to and ruled by."""
from __future__ import annotations

import unittest
from datetime import date
from types import MappingProxyType

from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import (
    usage_axis,
    usage_bands,
    usage_series,
)

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_CLAUDE = "claude"

_CODEX = "codex"

_TOKEN_TYPE_MODE = "type"

_TOKEN_AXIS = "yaxis"

_COST_AXIS = "yaxis2"

_SHOW_GRID = "showgrid"

_INPUT_TOKENS = 1_000.0

_OUTPUT_TOKENS = 500.0

_CACHE_TOKENS = 400.0

_COST_USD = 1.5

# The two stacks the same day can be drawn as. The per-backend one is an order
# of magnitude taller than the bands beside it, so an axis scaled to the series
# that is not on the plot cannot round to the same maximum by chance.
_BACKEND_ROWS = usage_bands.BackendDailyTokens(
    MappingProxyType({_DAY: {_CLAUDE: 12_000.0, _CODEX: 6_000.0}}),
    MappingProxyType({_DAY: 0}),
)

_BACKEND_TOKEN_TOP = 25_000.0

_TOKEN_TYPE_TOKEN_TOP = 2_500.0

_COST_TOP = 2.5

# What a maximum is raised to for a five-step axis: 1, 2, 2.5, 5, or 10 times
# the decade under the step it would otherwise take.
_ROUNDING_CASES = (
    (900.0, 1_000.0),
    (1_234.0, 1_250.0),
    (4_600.0, 5_000.0),
    (0.9, 1.0),
)


def _usage() -> usage_series.UsageChartData:
    """One day's buckets, as the shaping would hand them over."""
    return usage_series.UsageChartData(
        daily={
            _DAY: {
                usage_bands.INPUT_BAND: _INPUT_TOKENS,
                usage_bands.OUTPUT_BAND: _OUTPUT_TOKENS,
                usage_bands.CACHE_BAND: _CACHE_TOKENS,
                usage_bands.COST_BAND: _COST_USD,
            },
        },
        days=[_DAY],
    )


def _token_type_layout(title: str | None = None) -> dict[str, object]:
    """The layout a token-type window is drawn under."""
    return usage_axis.usage_layout(_usage(), None, _TOKEN_TYPE_MODE, title)


class RoundedAxisMaximumTest(unittest.TestCase):
    """An axis ends on a number an operator can read off a ruler."""

    def test_a_maximum_is_raised_to_a_divisible_step(self) -> None:
        steps = usage_axis.USAGE_GRID_STEPS
        for data_max, expected in _ROUNDING_CASES:
            with self.subTest(data_max=data_max):
                axis_max = usage_axis.nice_axis_max(data_max, steps)
                self.assertEqual(axis_max, expected)
                self.assertGreaterEqual(axis_max, data_max)

    def test_an_empty_window_is_still_given_a_span(self) -> None:
        # A range of [0, 0] draws no gridlines at all, so a window with
        # nothing in it would come back as a chart with no scale rather than
        # an empty chart with one.
        steps = usage_axis.USAGE_GRID_STEPS
        for data_max in (float(0), -1.0):
            with self.subTest(data_max=data_max):
                self.assertEqual(
                    usage_axis.nice_axis_max(data_max, steps), float(steps),
                )
        self.assertEqual(usage_axis.nice_axis_max(_INPUT_TOKENS, 0), 1.0)


class AxisRangeTest(unittest.TestCase):
    """Each axis is scaled to the series that is drawn against it."""

    def test_the_token_axis_follows_the_stack(self) -> None:
        # The mode travels this far down because the two stacks are different
        # heights: scaling to the bands under a per-backend stack would leave
        # the tallest band drawn past the top of its own axis.
        backend = usage_axis.usage_axis_ranges(
            _usage(), _BACKEND_ROWS, usage_bands.BACKEND_MODE,
        )
        token_type = usage_axis.usage_axis_ranges(
            _usage(), None, _TOKEN_TYPE_MODE,
        )
        self.assertEqual(backend.token_top, _BACKEND_TOKEN_TOP)
        self.assertEqual(token_type.token_top, _TOKEN_TYPE_TOKEN_TOP)

    def test_the_cost_axis_follows_the_cost_band(self) -> None:
        # Cost keeps a range of its own whichever way the tokens are stacked,
        # so the dollar ticks say the same thing in both views.
        modes = (
            (_BACKEND_ROWS, usage_bands.BACKEND_MODE),
            (None, _TOKEN_TYPE_MODE),
        )
        for backend_rows, mode in modes:
            with self.subTest(mode=mode):
                ranges = usage_axis.usage_axis_ranges(
                    _usage(), backend_rows, mode,
                )
                self.assertEqual(ranges.cost_top, _COST_TOP)


class UsageLayoutTest(unittest.TestCase):
    """The layout the two scales are assembled into over one plot."""

    def test_both_axes_are_cut_into_the_same_steps(self) -> None:
        layout = _token_type_layout()
        steps = usage_axis.USAGE_GRID_STEPS
        tops = ((_TOKEN_AXIS, _TOKEN_TYPE_TOKEN_TOP), (_COST_AXIS, _COST_TOP))
        for axis_key, top in tops:
            with self.subTest(axis=axis_key):
                self.assertEqual(layout[axis_key]["range"], [0, top])
                self.assertEqual(layout[axis_key]["dtick"], top / steps)

    def test_only_the_token_axis_rules_the_plot(self) -> None:
        # Two grids over one plot would cross wherever the two roundings
        # disagree, so the dollar axis carries the ticks and the token axis
        # the lines both scales are read against.
        layout = _token_type_layout()
        self.assertTrue(layout[_TOKEN_AXIS][_SHOW_GRID])
        self.assertFalse(layout[_COST_AXIS][_SHOW_GRID])
        self.assertEqual(layout[_COST_AXIS]["overlaying"], "y")
        self.assertEqual(layout[_COST_AXIS]["side"], "right")
        self.assertEqual(layout[_COST_AXIS]["tickprefix"], "$")

    def test_the_shared_layout_is_merged(self) -> None:
        # The token axis is the page's own axis with a range added to it, so
        # the hero chart keeps the gridline color every panel beside it draws.
        layout = _token_type_layout(title="Spend")
        self.assertEqual(layout[_TOKEN_AXIS]["gridcolor"], palette.GRID)
        self.assertEqual(layout["title"]["text"], "Spend")
        self.assertEqual(layout["height"], usage_axis.USAGE_CHART_HEIGHT)


if __name__ == "__main__":
    unittest.main()
