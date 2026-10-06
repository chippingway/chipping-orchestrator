# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's spend is ranked, bound, sized, and drawn when it is empty."""
from __future__ import annotations

import unittest
from importlib.util import find_spec
from inspect import signature

from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import cost_horizontal, primitives

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_ROW_HEIGHT = primitives.HORIZONTAL_BAR_ROW_HEIGHT

_EXTRA_HEIGHT = primitives.HORIZONTAL_BAR_EXTRA_HEIGHT

_PINNED_HEIGHT = 320

_CALLER_ACCENT = "#111111"

_ROW_COLOR = "#222222"

_CHEAPEST = "alpha"

_DEAREST = "beta"

_MIDDLE = "gamma"

_CHEAPEST_COST = 5.0

_DEAREST_COST = 15.0

_MIDDLE_COST = 10.0

_CHEAPEST_SUB = "1 run"

_MIDDLE_SUB = "3 runs"

# Rows in the order a caller hands them over, dearest in the middle, so both
# the ranking and the caller's own order are visible in what comes back.
_ROWS = (
    (_CHEAPEST, _CHEAPEST_SUB, _CHEAPEST_COST, _ROW_COLOR),
    (_DEAREST, "2 runs", _DEAREST_COST, _ROW_COLOR),
    (_MIDDLE, _MIDDLE_SUB, _MIDDLE_COST, _ROW_COLOR),
)

_RANKED_LABELS = (_CHEAPEST, _MIDDLE, _DEAREST)

_RANKED_COSTS = (_CHEAPEST_COST, _MIDDLE_COST, _DEAREST_COST)

_GIVEN_LABELS = (_MIDDLE, _DEAREST, _CHEAPEST)

_REPO_ROW = ("repo", "10 runs", 12_345.0, _ROW_COLOR)


class RankingTest(unittest.TestCase):
    """The order and tint the four columns of a ranking come back in."""

    def test_spend_ranks_it_largest_bar_last(self) -> None:
        # A Plotly bar axis draws the first row at the bottom, so the ranking
        # arrives flipped for the largest bar to sit on top -- all four columns
        # together, or a label would part company with the amount beside it.
        bars = cost_horizontal.horizontal_bars_data(_ROWS, None, False)
        self.assertEqual(tuple(bars.labels), _RANKED_LABELS)
        self.assertEqual(tuple(bars.costs), _RANKED_COSTS)
        subs = tuple(bars.subs)
        self.assertEqual(subs[0], _CHEAPEST_SUB)
        self.assertEqual(subs[1], _MIDDLE_SUB)

    def test_a_caller_s_own_order_is_kept(self) -> None:
        # A family that already ranked its rows -- by stage, by review round --
        # passes them through, and only the flip for the axis is applied.
        bars = cost_horizontal.horizontal_bars_data(_ROWS, None, True)
        self.assertEqual(tuple(bars.labels), _GIVEN_LABELS)

    def test_an_unpriced_row_ranks_below_a_priced(self) -> None:
        self.assertEqual(
            cost_horizontal.cost_item_sort_key(_ROWS[1]), -_DEAREST_COST,
        )
        self.assertEqual(
            cost_horizontal.cost_item_sort_key(("delta", "", None, "")), 0,
        )

    def test_a_colorless_row_falls_back_to_accent(self) -> None:
        # A ranking is one hue unless a family tints its rows, so a row with no
        # color of its own takes the caller's accent and then the page's.
        rows = ((_CHEAPEST, _CHEAPEST_SUB, _CHEAPEST_COST, ""),)
        tinted = cost_horizontal.horizontal_bars_data(rows, _CALLER_ACCENT, False)
        self.assertEqual(tuple(tinted.colors), (_CALLER_ACCENT,))
        default = cost_horizontal.horizontal_bars_data(rows, None, False)
        self.assertEqual(tuple(default.colors), (palette.ACCENT,))


class PinnedCallShapeTest(unittest.TestCase):
    """The builder answers for the call shape, not for `*args`."""

    def test_the_reported_signature_is_pinned(self) -> None:
        # `inspect.signature` is what a caller and any adapter above read, so
        # the pinned shape rather than the pair the body receives is reported.
        bound = signature(cost_horizontal.cost_horizontal_bars).parameters
        self.assertEqual(
            tuple(bound),
            ("items", "title", "accent", "preserve_order", "height"),
        )
        self.assertFalse(bound["preserve_order"].default)
        self.assertIsNone(bound["height"].default)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class RankingFigureTest(unittest.TestCase):
    """What the builder draws, including the window that ranked nothing."""

    def test_rows_may_be_passed_by_name(self) -> None:
        # `items` is the keyword the pinned signature binds the rows through.
        figure = cost_horizontal.cost_horizontal_bars(items=_ROWS)
        self.assertEqual(tuple(figure.data[0].x), _RANKED_COSTS)

    def test_bars_are_labelled_and_ticked(self) -> None:
        figure = cost_horizontal.cost_horizontal_bars((_REPO_ROW,))
        trace = figure.data[0]
        self.assertEqual(tuple(trace.text), ("$12.3K",))
        self.assertIn(f"<b>{_REPO_ROW[0]}</b>", trace.y[0])
        self.assertIn(_REPO_ROW[1], trace.y[0])

    def test_height_grows_with_the_rows_ranked(self) -> None:
        figure = cost_horizontal.cost_horizontal_bars(_ROWS)
        self.assertEqual(
            figure.layout.height, _ROW_HEIGHT * len(_ROWS) + _EXTRA_HEIGHT,
        )

    def test_nothing_ranked_is_one_bar_tall(self) -> None:
        # An empty ranking is the placeholder at the height a single-row panel
        # comes to, so a card reading nothing does not stand taller than the
        # ones beside it -- unless the caller pinned a height for both states.
        empty = cost_horizontal.cost_horizontal_bars(())
        self.assertGreaterEqual(len(empty.layout.annotations), 1)
        self.assertEqual(
            empty.layout.height, cost_horizontal.DEFAULT_CHART_HEIGHT,
        )
        pinned = cost_horizontal.cost_horizontal_bars((), height=_PINNED_HEIGHT)
        self.assertEqual(pinned.layout.height, _PINNED_HEIGHT)


if __name__ == "__main__":
    unittest.main()
