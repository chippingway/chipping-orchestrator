# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's spend is split per review round and role by token share, tinted, worded, and drawn.

Each role's cost in a round is a cohort, so the rounds below carry the cohorts
a bar has to keep apart -- a mixed-provider development pass beside an
AGY-only review, an incomplete rework round, and runs with no basis and no
round -- and the cases read back each role's three token-share segments, the
figure past its bar, the cost its hover words, and the sub-line naming the
round's basis and shortfall.
"""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.cache_shares import TokenShareBands
from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.dashboard import palette, spend_text
from orchestrator.observability.dashboard.charts import (
    cost_horizontal,
    cost_layout,
    cost_review,
    cost_stage,
    primitives,
)
from tests.observability.analytics import analytics_cohorts as cohort_cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEVELOPER = "developer"

_REVIEWER = "reviewer"

_INITIAL_LABEL = "Initial"

_UNROUNDED_LABEL = "No review round"

_PINNED_HEIGHT = 320

_INITIAL_DEV_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["mixed providers"])

_INITIAL_REV_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["agy only"])

_FIRST_DEV_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["incomplete"])

_UNROUNDED_DEV_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["missing basis"])

# Each role's stated amount by token share: the cache share, the rest, and
# the amount no declared total split.
_INITIAL_DEV_SHARES = (0.4, 0.29, 0)

_INITIAL_REV_SHARES = (0, 0, 0.32)

_FIRST_DEV_SHARES = (0.3, 0.2, 0)

_UNROUNDED_DEV_SHARES = (0.2, 0.22, 0.07)

_INITIAL_DEV_BANDS = TokenShareBands(*_INITIAL_DEV_SHARES)

_INITIAL_REV_BANDS = TokenShareBands(*_INITIAL_REV_SHARES)

_FIRST_DEV_BANDS = TokenShareBands(*_FIRST_DEV_SHARES)

_UNROUNDED_DEV_BANDS = TokenShareBands(*_UNROUNDED_DEV_SHARES)

_NO_RUNS = "—"

# The first pass, one rework round with no review run in it, and the runs that
# carried no round at all; round 2 is absent from the window. The two roles of
# the first pass are AGY-only review beside mixed-provider development.
_INITIAL_ROW = ReviewRoundBucketRow(
    bucket="0",
    runs=_INITIAL_DEV_COST.runs + _INITIAL_REV_COST.runs,
    developer_cost=_INITIAL_DEV_COST,
    reviewer_cost=_INITIAL_REV_COST,
    developer_bands=_INITIAL_DEV_BANDS,
    reviewer_bands=_INITIAL_REV_BANDS,
)

_FIRST_ROUND_ROW = ReviewRoundBucketRow(
    bucket="1",
    runs=_FIRST_DEV_COST.runs,
    developer_cost=_FIRST_DEV_COST,
    developer_bands=_FIRST_DEV_BANDS,
)

_UNROUNDED_ROW = ReviewRoundBucketRow(
    bucket="unknown",
    runs=_UNROUNDED_DEV_COST.runs,
    developer_cost=_UNROUNDED_DEV_COST,
    developer_bands=_UNROUNDED_DEV_BANDS,
)

# A bucket the ordering does not name: the read model only ever writes the
# eight it does, so a window of nothing but this one has no row to draw.
_STRAY_ROW = ReviewRoundBucketRow(bucket="12", runs=1)

# Handed over out of round order, so the ordering shows in what comes back
# rather than being whatever the caller happened to pass.
_ROWS = (_UNROUNDED_ROW, _INITIAL_ROW, _FIRST_ROUND_ROW)


def _review_traces() -> tuple[cost_layout.CostBarTrace, ...]:
    """The six series a window's rounds are described by."""
    bars = cost_review.review_cost_bars(_ROWS)
    return cost_review.review_cost_traces(bars, tuple(bars.labels))


class ReviewRoundOrderTest(unittest.TestCase):
    """Which rounds a window draws, in what order, labelled and worded how."""

    def test_rounds_read_in_round_order(self) -> None:
        # A round number is an ordinal, so the rows are laid out by the round
        # rather than ranked by spend -- what the panel is read for is the
        # shape of the rework curve. A Plotly bar axis draws the first row at
        # the bottom, so they arrive bottom-up for the first pass to sit on top.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertEqual(
            tuple(bars.labels),
            (_UNROUNDED_LABEL, "Round 1", _INITIAL_LABEL),
        )
        self.assertEqual(
            tuple(bars.developer.cache),
            (_UNROUNDED_DEV_BANDS.cache_usd, _FIRST_DEV_BANDS.cache_usd, _INITIAL_DEV_BANDS.cache_usd),
        )
        self.assertEqual(tuple(bars.reviewer.unsplit), (0, 0, _INITIAL_REV_BANDS.unsplit_usd))

    def test_a_round_with_no_rows_is_left_out(self) -> None:
        # Round 2 carried nothing in this window, and a row drawn for it would
        # read as a round that cost nothing rather than one that never ran.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertNotIn("Round 2", bars.labels)
        self.assertEqual(len(bars.labels), len(_ROWS))

    def test_the_sub_line_counts_roles_and_bases(self) -> None:
        # The two bars beside it are drawn from two different populations, so
        # one combined run count would explain neither; the basis and any
        # shortfall are the round's, both roles folded.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertEqual(
            tuple(bars.subs),
            (
                "2 dev / 0 review runs · blended · completeness unknown",
                "3 dev / 0 review runs · Anthropic API token estimate · subtotal",
                "3 dev / 2 review runs · blended",
            ),
        )

    def test_each_role_is_figured_on_its_own(self) -> None:
        # A role with no run in a round reads as having none rather than a
        # zero, and an AGY-only review reads as the Gemini estimate it is.
        bars = cost_review.review_cost_bars(_ROWS)
        self.assertEqual(tuple(bars.reviewer.figures), (_NO_RUNS, _NO_RUNS, "$0.32"))
        self.assertEqual(tuple(bars.developer.figures), ("$0.49", "$0.50", "$0.69"))
        self.assertEqual(bars.reviewer.notes[-1], spend_text.spend_line(_INITIAL_REV_COST))
        self.assertIn("Gemini API token estimate", bars.reviewer.notes[-1])

    def test_no_named_round_draws_nothing(self) -> None:
        self.assertIsNone(cost_review.review_cost_bars((_STRAY_ROW,)))


class RoleSeriesTest(unittest.TestCase):
    """What the six series are named, offset into, and tinted by."""

    def test_review_is_described_before_development(self) -> None:
        # The legend is read back to front, so describing review first is what
        # puts development above it for a reader; each segment is named as a
        # token share, never a cache charge.
        self.assertEqual(
            tuple(trace.name for trace in _review_traces()),
            (
                "Review (non-cache token share)",
                "Review (cache token share)",
                "Review (token share unknown)",
                "Development (non-cache token share)",
                "Development (cache token share)",
                "Development (token share unknown)",
            ),
        )

    def test_the_two_roles_are_offset_apart(self) -> None:
        # Same offsetgroup stacks, different ones sit side by side, so a
        # role's segments share a bar and the roles share the row.
        self.assertEqual(
            tuple(trace.offsetgroup for trace in _review_traces()),
            (_REVIEWER,) * 3 + (_DEVELOPER,) * 3,
        )

    def test_the_cache_share_shades_the_role_hue(self) -> None:
        # A palette of its own for the cache segments would read as four roles
        # rather than two split two ways, and the shading is the per-stage
        # split's so the two panels tint a cache segment alike.
        traces = _review_traces()
        for index, role in ((0, _REVIEWER), (3, _DEVELOPER)):
            with self.subTest(role=role):
                hue = palette.AGENT_ROLE_COLORS[role]
                self.assertEqual(traces[index].color, hue)
                self.assertEqual(
                    traces[index + 1].color,
                    cost_stage.lighten_hex(hue, cost_stage.CACHE_LIGHTEN),
                )

    def test_only_the_outer_segment_is_figured(self) -> None:
        traces = _review_traces()
        self.assertEqual(
            tuple(trace.labels is not None for trace in traces),
            (False, False, True, False, False, True),
        )


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

    def test_a_round_is_labelled_and_counted(self) -> None:
        ticks = " ".join(cost_review.cost_by_review_round(_ROWS).data[0].y)
        self.assertIn(f"<b>{_INITIAL_LABEL}</b>", ticks)
        self.assertIn(f"<b>{_UNROUNDED_LABEL}</b>", ticks)
        self.assertIn("3 dev / 2 review runs", ticks)

    def test_the_outer_segment_carries_the_figure(self) -> None:
        traces = cost_review.cost_by_review_round(_ROWS).data
        self.assertIsNone(traces[0].text)
        self.assertEqual(list(traces[2].text), [_NO_RUNS, _NO_RUNS, "$0.32"])
        self.assertEqual(list(traces[5].text), ["$0.49", "$0.50", "$0.69"])
        initial_development = spend_text.spend_line(_INITIAL_DEV_COST)
        self.assertEqual(traces[3].customdata[-1], initial_development)

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
