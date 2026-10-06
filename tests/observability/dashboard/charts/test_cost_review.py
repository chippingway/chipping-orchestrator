# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's spend is split per review round, tinted, and drawn."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import (
    cost_horizontal,
    cost_layout,
    cost_review,
    cost_stage,
    primitives,
)

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEVELOPER = "developer"

_REVIEWER = "reviewer"

_INITIAL_LABEL = "Initial"

_UNROUNDED_LABEL = "No review round"

_PINNED_HEIGHT = 320

_INITIAL_DEV_NO_CACHE = 8.0

_INITIAL_DEV_CACHE = 20.0

_INITIAL_REV_NO_CACHE = 3.0

_INITIAL_REV_CACHE = 9.0

_INITIAL_DEV_TOTAL = 28.0

_INITIAL_REV_TOTAL = 12.0

_FIRST_DEV_NO_CACHE = 2.0

_FIRST_DEV_CACHE = 7.0

_FIRST_REV_NO_CACHE = 3.0

_FIRST_REV_CACHE = 8.0

_THIRD_DEV_CACHE = 6.0

_THIRD_REV_CACHE = 4.0

_UNROUNDED_DEV_NO_CACHE = 5.0

# The amount a series carries in a round it drew no bar for.
_NO_SPEND = float(0)

_INITIAL_DEV_RUNS = 6

_INITIAL_REV_RUNS = 4

# The first pass, two of the rework rounds, and the runs that carried no round
# at all. Both halves of every priced bar are filled so the stack inside it is
# visible, round 3 is all cache and the unrounded runs all full price, and
# round 2 is absent from the window.
_INITIAL_ROW = ReviewRoundBucketRow(
    bucket="0",
    runs=_INITIAL_DEV_RUNS + _INITIAL_REV_RUNS,
    developer_runs=_INITIAL_DEV_RUNS,
    reviewer_runs=_INITIAL_REV_RUNS,
    developer_no_cache_cost_usd=_INITIAL_DEV_NO_CACHE,
    developer_cache_cost_usd=_INITIAL_DEV_CACHE,
    reviewer_no_cache_cost_usd=_INITIAL_REV_NO_CACHE,
    reviewer_cache_cost_usd=_INITIAL_REV_CACHE,
)

_FIRST_ROUND_ROW = ReviewRoundBucketRow(
    bucket="1",
    runs=4,
    developer_runs=2,
    reviewer_runs=2,
    developer_no_cache_cost_usd=_FIRST_DEV_NO_CACHE,
    developer_cache_cost_usd=_FIRST_DEV_CACHE,
    reviewer_no_cache_cost_usd=_FIRST_REV_NO_CACHE,
    reviewer_cache_cost_usd=_FIRST_REV_CACHE,
)

_THIRD_ROUND_ROW = ReviewRoundBucketRow(
    bucket="3",
    runs=2,
    developer_runs=1,
    reviewer_runs=1,
    developer_cache_cost_usd=_THIRD_DEV_CACHE,
    reviewer_cache_cost_usd=_THIRD_REV_CACHE,
)

_UNROUNDED_ROW = ReviewRoundBucketRow(
    bucket="unknown",
    runs=1,
    developer_runs=1,
    reviewer_runs=0,
    developer_no_cache_cost_usd=_UNROUNDED_DEV_NO_CACHE,
)

# A bucket the ordering does not name: the read model only ever writes the
# eight it does, so a window of nothing but this one has no row to draw.
_STRAY_ROW = ReviewRoundBucketRow(bucket="12", runs=1, developer_runs=1)

# Handed over out of round order, so the ordering shows in what comes back
# rather than being whatever the caller happened to pass.
_ROWS = (_UNROUNDED_ROW, _THIRD_ROUND_ROW, _INITIAL_ROW, _FIRST_ROUND_ROW)


def _review_traces() -> tuple[cost_layout.CostBarTrace, ...]:
    """The four series a window's rounds are described by."""
    bars = cost_review.review_cost_bars(_ROWS)
    return cost_review.review_cost_traces(bars, tuple(bars.labels))


class ReviewRoundOrderTest(unittest.TestCase):
    """Which rounds a window draws, in what order, labelled how."""

    def test_rounds_read_in_round_order(self) -> None:
        # A round number is an ordinal, so the rows are laid out by the round
        # rather than ranked by spend -- what the panel is read for is the
        # shape of the rework curve. A Plotly bar axis draws the first row at
        # the bottom, so they arrive flipped for the first pass to sit on top.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertEqual(
            tuple(bars.labels),
            (_UNROUNDED_LABEL, "Round 3", "Round 1", _INITIAL_LABEL),
        )
        self.assertEqual(
            tuple(bars.developer_totals),
            (
                _UNROUNDED_DEV_NO_CACHE,
                _THIRD_DEV_CACHE,
                _FIRST_DEV_NO_CACHE + _FIRST_DEV_CACHE,
                _INITIAL_DEV_TOTAL,
            ),
        )

    def test_a_round_with_no_rows_is_left_out(self) -> None:
        # Round 2 carried nothing in this window, and a row drawn for it would
        # read as a round that cost nothing rather than one that never ran.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertNotIn("Round 2", bars.labels)
        self.assertEqual(len(bars.labels), len(_ROWS))

    def test_the_sub_line_counts_roles_apart(self) -> None:
        # The two bars beside it are drawn from two different populations, so
        # one combined run count would explain neither.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertEqual(bars.subs[-1], "6 dev / 4 review runs")

    def test_no_named_round_draws_nothing(self) -> None:
        self.assertIsNone(cost_review.review_cost_bars((_STRAY_ROW,)))


class RoleTotalTest(unittest.TestCase):
    """A role's bar total is the two halves added back together."""

    def test_a_role_total_is_its_two_halves(self) -> None:
        self.assertEqual(
            cost_review.developer_cost_total(_INITIAL_ROW), _INITIAL_DEV_TOTAL,
        )
        self.assertEqual(
            cost_review.reviewer_cost_total(_INITIAL_ROW), _INITIAL_REV_TOTAL,
        )

    def test_a_role_that_spent_nothing_totals_zero(self) -> None:
        self.assertEqual(cost_review.reviewer_cost_total(_UNROUNDED_ROW), 0)


class RoleSeriesTest(unittest.TestCase):
    """What the four series are named, offset into, and tinted by."""

    def test_review_is_described_before_development(self) -> None:
        # The legend is read back to front, so describing review first is what
        # puts development above it for a reader.
        self.assertEqual(
            tuple(trace.name for trace in _review_traces()),
            (
                "Review (no cache)",
                "Review (cache)",
                "Development (no cache)",
                "Development (cache)",
            ),
        )

    def test_the_two_roles_are_offset_apart(self) -> None:
        # Same offsetgroup stacks, different ones sit side by side, so a
        # role's two halves share a bar and the roles share the row.
        self.assertEqual(
            tuple(trace.offsetgroup for trace in _review_traces()),
            (_REVIEWER, _REVIEWER, _DEVELOPER, _DEVELOPER),
        )

    def test_the_cache_half_shades_the_role_hue(self) -> None:
        # A palette of its own for the cache halves would read as four roles
        # rather than two split two ways, and the shading is the per-stage
        # split's so the two panels tint a cache segment alike.
        traces = _review_traces()
        for index, role in ((0, _REVIEWER), (2, _DEVELOPER)):
            with self.subTest(role=role):
                hue = palette.AGENT_ROLE_COLORS[role]
                self.assertEqual(traces[index].color, hue)
                self.assertEqual(
                    traces[index + 1].color,
                    cost_stage.lighten_hex(hue, cost_stage.CACHE_LIGHTEN),
                )

    def test_only_the_outer_half_is_totalled(self) -> None:
        # The dollar text lands once per role bar instead of once per segment,
        # so the inner half is left without one.
        traces = _review_traces()
        self.assertIsNone(traces[0].totals)
        self.assertIsNone(traces[2].totals)
        self.assertIsNotNone(traces[1].totals)
        self.assertIsNotNone(traces[3].totals)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class ReviewFigureTest(unittest.TestCase):
    """What the builder draws, including the windows with nothing in them."""

    def test_the_roles_group_over_one_row(self) -> None:
        figure = cost_review.cost_by_review_round(_ROWS)
        self.assertEqual(figure.layout.barmode, "relative")
        self.assertEqual(figure.layout.legend.traceorder, "reversed")
        for trace in figure.data:
            with self.subTest(trace=trace.name):
                self.assertEqual(len(trace.y), len(_ROWS))

    def test_each_series_is_drawn_bottom_up(self) -> None:
        # Every column is flipped together, or a round's amounts would part
        # company with the label they belong to.
        expected = (
            (_NO_SPEND, _NO_SPEND, _FIRST_REV_NO_CACHE, _INITIAL_REV_NO_CACHE),
            (_NO_SPEND, _THIRD_REV_CACHE, _FIRST_REV_CACHE, _INITIAL_REV_CACHE),
            (
                _UNROUNDED_DEV_NO_CACHE,
                _NO_SPEND,
                _FIRST_DEV_NO_CACHE,
                _INITIAL_DEV_NO_CACHE,
            ),
            (_NO_SPEND, _THIRD_DEV_CACHE, _FIRST_DEV_CACHE, _INITIAL_DEV_CACHE),
        )
        traces = cost_review.cost_by_review_round(_ROWS).data
        for trace, amounts in zip(traces, expected):
            with self.subTest(trace=trace.name):
                self.assertEqual(tuple(trace.x), amounts)

    def test_a_round_is_labelled_and_counted(self) -> None:
        ticks = " ".join(cost_review.cost_by_review_round(_ROWS).data[0].y)
        self.assertIn(f"<b>{_INITIAL_LABEL}</b>", ticks)
        self.assertIn(f"<b>{_UNROUNDED_LABEL}</b>", ticks)
        self.assertIn("6 dev / 4 review runs", ticks)

    def test_only_the_outer_half_is_labelled(self) -> None:
        # Below $10 the amount keeps its cents and above it rounds to whole
        # dollars, which is the shared money label rather than this family's.
        traces = cost_review.cost_by_review_round(_ROWS).data
        self.assertIsNone(traces[0].text)
        self.assertIsNone(traces[2].text)
        review_totals = ["$0.00", "$4.00", "$11", "$12"]
        development_totals = ["$5.00", "$6.00", "$9.00", "$28"]
        self.assertEqual(list(traces[1].text), review_totals)
        self.assertEqual(list(traces[3].text), development_totals)

    def test_a_review_row_is_taller_than_a_bar(self) -> None:
        # Two bars share a row here where a ranking row carries one, so the
        # height the family sizes its other panels by would crowd them --
        # unless the caller pinned one.
        figure = cost_review.cost_by_review_round(_ROWS)
        self.assertGreater(
            figure.layout.height,
            primitives.horizontal_panel_height(len(_ROWS), height=None),
        )
        pinned = cost_review.cost_by_review_round(_ROWS, height=_PINNED_HEIGHT)
        self.assertEqual(pinned.layout.height, _PINNED_HEIGHT)

    def test_a_window_with_nothing_says_which(self) -> None:
        # An operator whose filter matched no agent exits and one whose window
        # holds no development or review runs are looking for different
        # things; one message for both would send the second after a broken
        # query.
        for rows, needle in (((), "agent_exit"), ((_STRAY_ROW,), "development")):
            with self.subTest(needle=needle):
                figure = cost_review.cost_by_review_round(rows)
                self.assertIn(needle, figure.layout.annotations[0].text)
                self.assertEqual(
                    figure.layout.height, cost_horizontal.DEFAULT_CHART_HEIGHT,
                )


if __name__ == "__main__":
    unittest.main()
