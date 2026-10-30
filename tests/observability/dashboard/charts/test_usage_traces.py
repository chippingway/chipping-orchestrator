# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The window a usage figure is shaped from and the bands stacked over it."""
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
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

_CLAUDE = "claude"

_CODEX = "codex"

_TOKEN_TYPE_MODE = "type"

_CACHE_TRACE = "Cache"

# The three token bands, in the order they stack from the bottom of a day's
# column up, and the hue each is painted in: the input band holds the input no
# cache answered, and is named for it.
_TOKEN_HUES = MappingProxyType({
    "Uncached input": "Input",
    "Output": "Output",
    _CACHE_TRACE: "Cache",
})

_TOKEN_TRACES = tuple(_TOKEN_HUES)

_AGENT_EXIT = "agent_exit"

# A Codex day: 400 of its 1,000 input tokens were cached, so the cache band
# holds them and the input band only the 600 left.
_CACHE_TOKENS = cases.CODEX_CACHED

_OUTPUT_TOKENS = cases.CODEX_OUTPUT

_CLAUDE_TOKENS = 1_200.0

_CODEX_TOKENS = 600.0

_BACKEND_ROWS = usage_bands.BackendDailyTokens(
    MappingProxyType({_DAY: {_CODEX: _CODEX_TOKENS, _CLAUDE: _CLAUDE_TOKENS}}),
    MappingProxyType({_DAY: 0}),
)

_NO_BACKEND_ROWS = usage_bands.BackendDailyTokens({}, {})

# One row per `(day, event)`, which is how the overview read hands a window
# over, with the known total split into the cache and output inside it.
_POINTS = (
    TimeSeriesPoint(
        day=_DAY,
        event=_AGENT_EXIT,
        count=1,
        cost=cohort_cases.cohort(cases.OPENAI_ESTIMATE),
        total_tokens=cases.CODEX_TOTAL,
        cache_tokens=_CACHE_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
    ),
    TimeSeriesPoint(
        day=_NEXT_DAY,
        event=_AGENT_EXIT,
        count=2,
        cost=cohort_cases.cohort(cases.REPORTED, cases.REPORTED),
        total_tokens=cases.CLAUDE_TOTAL,
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
            ((), _NO_BACKEND_ROWS, usage_bands.BACKEND_MODE),
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
        # Each day carries its bands and the cost cohort its events fold to.
        usage = usage_traces.prepare_usage_data(
            _POINTS, None, _TOKEN_TYPE_MODE,
        )
        self.assertEqual(usage.days, [_DAY, _NEXT_DAY])
        self.assertEqual(usage.daily[_DAY][usage_bands.CACHE_BAND], _CACHE_TOKENS)
        self.assertEqual(usage.costs[_NEXT_DAY], _POINTS[1].cost)

    def test_the_backend_view_completes_its_day_span(self) -> None:
        # The two reads are windowed alike but grouped differently, so a day
        # only the per-backend one saw has to join the axis -- and a window
        # that is nothing but per-backend rows is still a chart.
        later_rows = usage_bands.BackendDailyTokens({_NEXT_DAY: {_CLAUDE: _CLAUDE_TOKENS}}, {_NEXT_DAY: 1})
        usage = usage_traces.prepare_usage_data(
            _POINTS[:1],
            later_rows,
            usage_bands.BACKEND_MODE,
        )
        self.assertEqual(usage.days, [_DAY, _NEXT_DAY])
        self.assertEqual(
            usage.daily[_NEXT_DAY], usage_bands.empty_token_bucket(),
        )
        # The per-backend stack is the one drawn, so the runs it leaves out are
        # that read's own count, and the day it alone saw has no cost cohort.
        self.assertEqual(usage.unknown_runs, later_rows.unknown_runs)
        self.assertNotIn(_NEXT_DAY, usage.costs)
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
                    trace.fillcolor, palette.TOKEN_TYPE_COLORS[_TOKEN_HUES[trace.name]],
                )
                self.assertEqual(trace.stackgroup, "tokens")
        # The Codex day's cached input is drawn once, in the cache band, so the
        # day's column is as tall as its known total.
        first_day = {band.name: band.y[0] for band in figure.data}
        cache = _named(figure)[_CACHE_TRACE]
        self.assertEqual(tuple(cache.y), (_CACHE_TOKENS, 0))
        self.assertEqual(first_day["Uncached input"], cases.CODEX_UNCACHED_INPUT)
        self.assertEqual(sum(first_day.values()), cases.CODEX_TOTAL)

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
            (_NO_BACKEND_ROWS, usage_bands.BACKEND_MODE, set(_TOKEN_TRACES)),
            (None, _TOKEN_TYPE_MODE, set(_TOKEN_TRACES)),
        )
        for backend_rows, mode, expected in stacks:
            with self.subTest(mode=mode, backend_rows=backend_rows):
                self.assertEqual(
                    set(_named(_stacked(backend_rows, mode))), expected,
                )


if __name__ == "__main__":
    unittest.main()
