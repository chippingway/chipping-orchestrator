# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The window a usage figure is shaped from and the traces stacked over it."""
from __future__ import annotations

import unittest
from datetime import date
from importlib.util import find_spec
from types import MappingProxyType

from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import usage_bands, usage_traces

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

_CLAUDE = "claude"

_CODEX = "codex"

_TOKEN_TYPE_MODE = "type"

_COST_TRACE = "Cost"

_CACHE_TRACE = "Cache"

# The three token bands, in the order they stack from the bottom of a day's
# column up.
_TOKEN_TRACES = ("Input", "Output", _CACHE_TRACE)

_AGENT_EXIT = "agent_exit"

_INPUT_TOKENS = 1_000

_OUTPUT_TOKENS = 500

_CACHE_READ_TOKENS = 400

_CACHE_WRITE_TOKENS = 200

_COST_USD = 1.5

_LATER_COST_USD = 2.5

_CLAUDE_TOKENS = 1_200.0

_CODEX_TOKENS = 600.0

_BACKEND_ROWS = MappingProxyType(
    {_DAY: {_CODEX: _CODEX_TOKENS, _CLAUDE: _CLAUDE_TOKENS}},
)

# One row per `(day, event)`, which is how the overview read hands a window
# over, with the cache counters arriving as the two columns of the single band
# the stack draws.
_POINTS = (
    TimeSeriesPoint(
        day=_DAY,
        event=_AGENT_EXIT,
        count=1,
        cost_usd=_COST_USD,
        input_tokens=_INPUT_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
        cache_read_tokens=_CACHE_READ_TOKENS,
        cache_write_tokens=_CACHE_WRITE_TOKENS,
    ),
    TimeSeriesPoint(
        day=_NEXT_DAY,
        event=_AGENT_EXIT,
        count=2,
        cost_usd=_LATER_COST_USD,
        input_tokens=_INPUT_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
    ),
)


def _figure():
    """A bare figure for a builder to add its traces to."""
    from plotly import graph_objects as go

    return go.Figure()


def _named(figure) -> dict:
    """The figure's traces, keyed by the name each is legended under."""
    return {trace.name: trace for trace in figure.data}


def _stacked(backend_rows, mode):
    """One day's window, stacked the way the mode given says."""
    figure = _figure()
    usage_traces.add_usage_stack_traces(
        figure,
        usage_traces.prepare_usage_data(_POINTS[:1], None, _TOKEN_TYPE_MODE),
        backend_rows,
        mode,
    )
    return figure


class WindowShapingTest(unittest.TestCase):
    """What a window becomes before any of it is drawn."""

    def test_a_window_holding_nothing_has_no_chart(self) -> None:
        # There is no figure to draw rather than an empty one: the caller
        # answers this with the page's shared placeholder, so a chart whose
        # axes are labelled for data that is not behind them never appears.
        empty_windows = (
            ((), None, _TOKEN_TYPE_MODE),
            ((), {}, usage_bands.BACKEND_MODE),
            ((), _BACKEND_ROWS, _TOKEN_TYPE_MODE),
        )
        for points, backend_rows, mode in empty_windows:
            with self.subTest(mode=mode, backend_rows=backend_rows):
                self.assertIsNone(
                    usage_traces.prepare_usage_data(
                        points, backend_rows, mode,
                    ),
                )

    def test_the_series_is_rolled_up_into_days(self) -> None:
        usage = usage_traces.prepare_usage_data(
            _POINTS, None, _TOKEN_TYPE_MODE,
        )
        self.assertEqual(usage.days, [_DAY, _NEXT_DAY])
        self.assertEqual(
            usage.daily[_DAY][usage_bands.CACHE_BAND],
            _CACHE_READ_TOKENS + _CACHE_WRITE_TOKENS,
        )

    def test_the_backend_view_completes_its_day_span(self) -> None:
        # The two reads are windowed alike but grouped differently, so a day
        # only the per-backend one saw has to join the axis -- and a window
        # that is nothing but per-backend rows is still a chart.
        usage = usage_traces.prepare_usage_data(
            _POINTS[:1],
            {_NEXT_DAY: {_CLAUDE: _CLAUDE_TOKENS}},
            usage_bands.BACKEND_MODE,
        )
        self.assertEqual(usage.days, [_DAY, _NEXT_DAY])
        self.assertEqual(
            usage.daily[_NEXT_DAY], usage_bands.empty_token_bucket(),
        )
        backend_only = usage_traces.prepare_usage_data(
            (), _BACKEND_ROWS, usage_bands.BACKEND_MODE,
        )
        self.assertEqual(backend_only.days, [_DAY])


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class TokenStackTest(unittest.TestCase):
    """The bands a day's tokens are stacked as, in either mode."""

    def test_token_bands_stack_in_their_own_hues(self) -> None:
        figure = _figure()
        usage = usage_traces.prepare_usage_data(
            _POINTS, None, _TOKEN_TYPE_MODE,
        )
        usage_traces.add_token_type_usage_traces(figure, usage)
        self.assertEqual(
            tuple(trace.name for trace in figure.data), _TOKEN_TRACES,
        )
        for trace in figure.data:
            with self.subTest(band=trace.name):
                self.assertEqual(
                    trace.fillcolor, palette.TOKEN_TYPE_COLORS[trace.name],
                )
                self.assertEqual(trace.stackgroup, "tokens")
        cache = _named(figure)[_CACHE_TRACE]
        self.assertEqual(
            tuple(cache.y), (_CACHE_READ_TOKENS + _CACHE_WRITE_TOKENS, 0),
        )

    def test_backend_bands_stack_in_legend_order(self) -> None:
        # The color each backend is drawn in is picked off its position among
        # the sorted names, so the band an operator followed last week is the
        # same hue this week however the rows arrived.
        figure = _figure()
        usage = usage_traces.prepare_usage_data(
            _POINTS[:1], _BACKEND_ROWS, usage_bands.BACKEND_MODE,
        )
        usage_traces.add_backend_usage_traces(figure, usage, _BACKEND_ROWS)
        self.assertEqual(
            [trace.name for trace in figure.data], [_CLAUDE, _CODEX],
        )
        self.assertEqual(
            _named(figure)[_CLAUDE].fillcolor,
            palette.BACKEND_COLORS[_CLAUDE],
        )
        self.assertEqual(tuple(_named(figure)[_CODEX].y), (_CODEX_TOKENS,))

    def test_the_stack_is_the_one_the_mode_asked_for(self) -> None:
        # A window the per-backend read came back empty for still draws the
        # token-type stack, so the page's segmented control cannot leave the
        # hero chart with no bands on it at all.
        stacks = (
            (_BACKEND_ROWS, usage_bands.BACKEND_MODE, {_CLAUDE, _CODEX}),
            ({}, usage_bands.BACKEND_MODE, set(_TOKEN_TRACES)),
            (None, _TOKEN_TYPE_MODE, set(_TOKEN_TRACES)),
        )
        for backend_rows, mode, expected in stacks:
            with self.subTest(mode=mode, backend_rows=backend_rows):
                self.assertEqual(
                    set(_named(_stacked(backend_rows, mode))), expected,
                )


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class CostOverlayTest(unittest.TestCase):
    """The one trace that leaves the token axis."""

    def test_the_cost_line_rides_the_secondary_axis(self) -> None:
        figure = _figure()
        usage = usage_traces.prepare_usage_data(
            _POINTS, None, _TOKEN_TYPE_MODE,
        )
        usage_traces.add_usage_cost_trace(figure, usage)
        cost = _named(figure)[_COST_TRACE]
        self.assertEqual(cost.yaxis, "y2")
        self.assertEqual(tuple(cost.y), (_COST_USD, _LATER_COST_USD))
        self.assertEqual(tuple(cost.x), (_DAY, _NEXT_DAY))
        # A line over the stack rather than another layer of it: joining the
        # cost group would fold dollars into the token axis' height.
        self.assertIsNone(cost.stackgroup)


if __name__ == "__main__":
    unittest.main()
