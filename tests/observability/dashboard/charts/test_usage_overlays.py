# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a usage figure draws over its stack: the subtotal marker and the cost line.

A day whose stack leaves out a run of unknown token total is marked on top of whichever stack is drawn, and a day's
cost reads on hover as the headline words it -- its basis, a blended total's parts, and why it falls short of complete
spend -- with a subtotal drawn open and an unpriced day left as a gap rather than plotted as free work.
"""
from __future__ import annotations

import unittest
from datetime import date
from importlib.util import find_spec
from types import MappingProxyType

from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard import spend_text
from orchestrator.observability.dashboard.charts import usage_bands, usage_overlays, usage_traces
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_YEAR = 2026

_MAY = 5

_DAY_NUMBERS = (1, 2, 3, 4)

_DAYS = tuple(date(_YEAR, _MAY, day) for day in _DAY_NUMBERS)

_LATER_DAY = date(_YEAR, _MAY, 9)

_AGENT_EXIT = "agent_exit"

_TOKEN_TYPE_MODE = "type"

_UNKNOWN_TRACE = "Token total unknown"

_COST_TRACE = "Cost"

_UNSTATED_TRACE = "Cost not stated"

# What the unpriced fourth day's cost reads as wherever it is hovered.
_UNPRICED_LINE = "unpriced (1 of 1 runs unpriced or partly priced)"

_KNOWN_TOKENS = 1_000

_CLAUDE_TOKENS = 700.0

_CODEX_TOKENS = 500.0

# Four days: a reported day, a blended day, a day with a subtotal and two runs
# of unknown token total, and a day whose only run went unpriced.
_COSTS_BY_DAY = (
    (cases.REPORTED,),
    (cases.REPORTED, cases.GEMINI_ESTIMATE),
    (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL),
    (cases.UNPRICED,),
)

_UNKNOWN_BY_DAY = (0, 0, 2, 0)

_POINTS = tuple(
    TimeSeriesPoint(
        day=day,
        event=_AGENT_EXIT,
        count=len(costs),
        cost=cohort_cases.cohort(*costs),
        total_tokens=_KNOWN_TOKENS,
        unknown_token_runs=unknown,
    )
    for day, costs, unknown in zip(_DAYS, _COSTS_BY_DAY, _UNKNOWN_BY_DAY, strict=True)
)

# The per-backend read is issued in a later wave than the series, so a sync
# between them can leave the two counting a day's runs of unknown total apart:
# here the series counts two on the third day and the per-backend read one on
# the second.
_BACKEND_UNKNOWN_BY_DAY = (0, 1, 0, 0)

_BACKEND_ROWS = usage_bands.BackendDailyTokens(
    MappingProxyType({day: {"claude": _CLAUDE_TOKENS, "codex": _CODEX_TOKENS} for day in _DAYS}),
    MappingProxyType(dict(zip(_DAYS, _BACKEND_UNKNOWN_BY_DAY, strict=True))),
)

_BACKEND_HEIGHT = _CLAUDE_TOKENS + _CODEX_TOKENS

# Each stack's marker: the stack's mode and rows, the height the marker sits at
# on each day, and what each day's hover says it leaves out -- counted off the
# read the stack was drawn from.
_MARKED_STACKS = (
    (
        _TOKEN_TYPE_MODE,
        None,
        (None, None, _KNOWN_TOKENS, None),
        ("", "", spend_text.token_note(2), ""),
    ),
    (
        usage_bands.BACKEND_MODE,
        _BACKEND_ROWS,
        (None, _BACKEND_HEIGHT, None, None),
        ("", spend_text.token_note(1), "", ""),
    ),
)


def _overlaid(points=_POINTS, backend_rows=None, mode=_TOKEN_TYPE_MODE) -> dict:
    """The overlay traces drawn over a window, keyed by the name each is legended under."""
    from plotly import graph_objects as go

    figure = go.Figure()
    usage = usage_traces.prepare_usage_data(points, backend_rows, mode)
    usage_overlays.add_unknown_totals_trace(figure, usage, backend_rows, mode)
    usage_overlays.add_unstated_cost_trace(figure, usage)
    usage_overlays.add_usage_cost_trace(figure, usage)
    return {trace.name: trace for trace in figure.data}


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class UnknownTotalsMarkerTest(unittest.TestCase):
    """The marker on a day whose stack is a subtotal."""

    def test_a_short_day_is_marked_on_its_stack(self) -> None:
        # The marker sits on whichever stack is drawn -- the token bands, or the
        # backends, whose day is as tall as their known totals add up to -- and
        # counts the runs that stack's own read left out, so a per-backend
        # subtotal the series never saw is still marked and a day the
        # per-backend read counted in full is not.
        for mode, backend_rows, heights, notes in _MARKED_STACKS:
            marker = _overlaid(backend_rows=backend_rows, mode=mode)[_UNKNOWN_TRACE]
            with self.subTest(mode=mode):
                self.assertEqual(tuple(marker.y), heights)
                self.assertEqual(tuple(marker.customdata), notes)
                self.assertIsNone(marker.stackgroup)

    def test_every_total_known_draws_no_marker(self) -> None:
        known = tuple(
            TimeSeriesPoint(day=point.day, event=point.event, count=point.count, total_tokens=_KNOWN_TOKENS)
            for point in _POINTS
        )
        self.assertNotIn(_UNKNOWN_TRACE, _overlaid(known))


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class CostLineTest(unittest.TestCase):
    """The one trace that leaves the token axis."""

    def test_the_cost_line_rides_the_secondary_axis(self) -> None:
        cost = _overlaid()[_COST_TRACE]
        self.assertEqual(cost.yaxis, "y2")
        self.assertEqual(tuple(cost.x), _DAYS)
        # A line over the stack rather than another layer of it: joining the
        # cost group would fold dollars into the token axis' height.
        self.assertIsNone(cost.stackgroup)

    def test_each_day_reads_as_the_headline_words_it(self) -> None:
        # The blended day lists its parts, the subtotal day says so and is drawn
        # open, and the unpriced day is a gap rather than a zero.
        cost = _overlaid()[_COST_TRACE]
        lines = [spend_text.spend_line(cohort_cases.cohort(*costs)) for costs in _COSTS_BY_DAY]
        self.assertEqual(list(cost.customdata), lines)
        self.assertIn("blended: CLI-reported $0.42 + Gemini API token estimate $0.12", cost.customdata[1])
        self.assertIn("incomplete subtotal", cost.customdata[2])
        self.assertEqual(cost.customdata[3], _UNPRICED_LINE)
        self.assertEqual(
            tuple(cost.y),
            (cases.REPORTED_USD, cases.REPORTED_USD + cases.GEMINI_USD, cases.ANTHROPIC_USD + cases.SUBTOTAL_USD, None),
        )
        self.assertEqual(tuple(cost.marker.symbol), ("circle", "circle", "circle-open", "circle-open"))

    def test_an_unread_day_is_a_gap(self) -> None:
        # A day only the per-backend read saw has no cost reading -- the series
        # never reached it -- so the line leaves a gap and the baseline marker
        # says so, never the zero and "no agent runs" of a day with no run.
        backend_rows = usage_bands.BackendDailyTokens({_LATER_DAY: {"claude": _CLAUDE_TOKENS}}, {_LATER_DAY: 0})
        overlaid = _overlaid(_POINTS[:1], backend_rows, usage_bands.BACKEND_MODE)
        cost = overlaid[_COST_TRACE]
        self.assertEqual(list(cost.x), [_DAYS[0], _LATER_DAY])
        self.assertIsNone(cost.y[-1])
        unstated = overlaid[_UNSTATED_TRACE]
        self.assertEqual(tuple(unstated.y), (None, 0))
        self.assertEqual(unstated.customdata[-1], usage_overlays.UNREAD_COST)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class UnstatedCostMarkerTest(unittest.TestCase):
    """The marker that keeps a day whose cost states no amount readable."""

    def test_an_unpriced_day_stays_hoverable(self) -> None:
        # Plotly neither draws nor hovers a point whose value is None, so the
        # line's gap alone would leave an unpriced day with no cost reading in
        # the rendered hover. The marker sits at a real value on the cost axis'
        # baseline, unclipped and hoverable, carrying the day's reading.
        unstated = _overlaid()[_UNSTATED_TRACE]
        self.assertEqual(tuple(unstated.y), (None, None, None, 0))
        self.assertEqual(unstated.customdata[3], _UNPRICED_LINE)
        self.assertEqual((unstated.yaxis, unstated.mode), ("y2", "markers"))
        self.assertIn("%{customdata}", unstated.hovertemplate)
        self.assertNotIn(unstated.hoverinfo, ("skip", "none"))
        self.assertIsNot(unstated.visible, False)
        self.assertIs(unstated.cliponaxis, False)

    def test_every_amount_stated_draws_no_marker(self) -> None:
        priced = _POINTS[:3]
        self.assertNotIn(_UNSTATED_TRACE, _overlaid(priced))


if __name__ == "__main__":
    unittest.main()
