# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's spend is split per stage by token share, tinted, ranked, worded, and drawn.

A stage's cost is a cohort, so the cases name the cohorts a bar has to keep
apart -- reported-only, AGY-only, mixed-provider, incomplete, and
missing-basis -- and read back the basis and shortfall its sub-line names, the
figure drawn past it, and the cost its hover words, beside the three
token-share segments its stated amount is stacked into.
"""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.cache_shares import TokenShareBands
from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.dashboard import palette, spend_text
from orchestrator.observability.dashboard.charts import cost_horizontal, cost_stage
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEAREST = "implementing"

_CHEAPEST = "validating"

_UNPRICED_STAGE = "fixing"

_DEAREST_RUNS = 8

_DEAREST_EVENTS = 20

_PINNED_HEIGHT = 320

_SAMPLE_HUE = "#5b54e0"

# The dearest stage is mixed across providers and split mostly to cache, the
# cheapest is AGY-only with an amount no declared token total could split, and
# the unpriced one states no amount at all. They arrive out of rank order, so
# both the ranking and the flip for the axis show in what comes back.
_DEAREST_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["mixed providers"])

# The dearest stage's stated amount by token share -- the cache share, the
# rest, and nothing unsplit -- and the cheapest's, all of it unsplit.
_DEAREST_SHARES = (0.4, 0.29, 0)

_CHEAPEST_SHARES = (0, 0, 0.32)

_DEAREST_BANDS = TokenShareBands(*_DEAREST_SHARES)

_CHEAPEST_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["agy only"])

_CHEAPEST_BANDS = TokenShareBands(*_CHEAPEST_SHARES)

_UNPRICED_COST = cohort_cases.cohort(cases.UNPRICED, cases.UNPRICED)

_ROWS = (
    StageBreakdown(stage=_UNPRICED_STAGE, count=4, runs=2, cost=_UNPRICED_COST),
    StageBreakdown(stage=_CHEAPEST, count=5, runs=2, cost=_CHEAPEST_COST, bands=_CHEAPEST_BANDS),
    StageBreakdown(stage=_DEAREST, count=_DEAREST_EVENTS, runs=_DEAREST_RUNS, cost=_DEAREST_COST, bands=_DEAREST_BANDS),
)

# What the line under each stage's name says beside its run count, per cohort.
_SUB_LINES = (
    ("reported only", "CLI-reported"),
    ("agy only", "Gemini API token estimate"),
    ("mixed providers", "blended"),
    ("incomplete", "Anthropic API token estimate · subtotal"),
    ("missing basis", "blended · completeness unknown"),
)


def _stage(cost, *, stage: str = _DEAREST) -> StageBreakdown:
    return StageBreakdown(stage=stage, count=1, runs=1, cost=cost)


class StageSplitTest(unittest.TestCase):
    """The order, sub-line, segments, and words the columns come back in."""

    def test_stated_spend_ranks_it_dearest_bar_last(self) -> None:
        # A Plotly bar axis draws the first row at the bottom, so the split
        # arrives flipped for the dearest stage to sit on top -- every column
        # together, or a label would part company with the amounts beside it.
        # A stage stating no amount sits below every one that states some.
        bars = cost_stage.stage_cost_bars(_ROWS)
        self.assertEqual(tuple(bars.labels), (_UNPRICED_STAGE, _CHEAPEST, _DEAREST))
        self.assertEqual(tuple(bars.split.cache), (0, 0, _DEAREST_BANDS.cache_usd))
        self.assertEqual(tuple(bars.split.no_cache), (0, 0, _DEAREST_BANDS.no_cache_usd))
        self.assertEqual(tuple(bars.split.unsplit), (0, _CHEAPEST_BANDS.unsplit_usd, 0))
        self.assertEqual(tuple(bars.split.figures), ("unpriced", "$0.32", "$0.69"))

    def test_no_amount_ranks_below_a_zero(self) -> None:
        zero = _stage(cohort_cases.cohort(cases.COMPLETE_ZERO))
        unpriced = _stage(_UNPRICED_COST)
        self.assertLess(cost_stage.stage_cost_sort_key(zero), cost_stage.stage_cost_sort_key(unpriced))

    def test_the_sub_line_counts_runs_and_bases(self) -> None:
        # `count` is every analytics row carrying the stage, `runs` the agent
        # exits whose stated spend a bar is drawn from, so a stage with 20
        # events behind 8 runs is labelled by the 8 -- and by the basis its
        # amount is stated on and any shortfall, so an AGY-only stage reads as
        # a Gemini API token estimate and a mixed one as blended.
        for name, worded in _SUB_LINES:
            cost = cohort_cases.cohort(*cohort_cases.NAMED_COSTS[name])
            row = StageBreakdown(stage=_DEAREST, count=_DEAREST_EVENTS, runs=_DEAREST_RUNS, cost=cost)
            with self.subTest(cohort=name):
                bars = cost_stage.stage_cost_bars((row,))
                self.assertEqual(tuple(bars.subs), (f"{_DEAREST_RUNS} runs · {worded}",))

    def test_each_bar_carries_its_cost_worded_whole(self) -> None:
        # The hover is where a blended amount's parts are read, by their own
        # amounts, beside the segment under the cursor.
        bars = cost_stage.stage_cost_bars((_ROWS[2],))
        self.assertEqual(tuple(bars.split.notes), (spend_text.spend_line(_DEAREST_COST),))
        self.assertIn("CLI-reported $", bars.split.notes[0])


class CacheShadingTest(unittest.TestCase):
    """Both split segments of a bar are tinted from the stage's one hue."""

    def test_the_cache_share_shades_the_stage_hue(self) -> None:
        # A palette of its own for the cache segments would read as four
        # stages rather than two split two ways, so the cache segment is the
        # same hue at the shared opacity.
        bars = cost_stage.stage_cost_bars((_ROWS[2],))
        hue = palette.color_for(_DEAREST, explicit=palette.STAGE_COLORS)
        self.assertEqual(tuple(bars.colors), (hue,))
        self.assertEqual(
            tuple(bars.cache_colors),
            (cost_stage.lighten_hex(hue, cost_stage.CACHE_LIGHTEN),),
        )

    def test_a_hex_color_is_restated_as_rgba(self) -> None:
        self.assertEqual(
            cost_stage.lighten_hex(_SAMPLE_HUE, cost_stage.CACHE_LIGHTEN),
            "rgba(91,84,224,0.45)",
        )


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class StageFigureTest(unittest.TestCase):
    """What the builder draws, including the window that split nothing."""

    def test_the_three_shares_are_stacked_per_stage(self) -> None:
        # Stacked rather than drawn side by side, so a bar's length stays the
        # stage's stated amount, and named as token shares so the split never
        # reads as a measured cache charge.
        figure = cost_stage.cost_by_stage(_ROWS)
        no_cache_trace, cache_trace, unsplit_trace = figure.data
        self.assertEqual(figure.layout.barmode, "stack")
        self.assertEqual(
            [trace.name for trace in figure.data],
            ["Non-cache token share", "Cache token share", "Token share unknown"],
        )
        self.assertEqual(list(cache_trace.x), [0, 0, _DEAREST_BANDS.cache_usd])
        self.assertEqual(list(unsplit_trace.x), [0, _CHEAPEST_BANDS.unsplit_usd, 0])
        self.assertTrue(unsplit_trace.showlegend)
        for stage in (_DEAREST, _CHEAPEST, _UNPRICED_STAGE):
            with self.subTest(stage=stage):
                self.assertTrue(any(stage in tick for tick in no_cache_trace.y))

    def test_only_the_outer_segment_is_labelled(self) -> None:
        # The figure lands once per bar instead of once per segment, an
        # unpriced stage's as the word rather than a zero, and every segment's
        # hover adds the stage's whole cost.
        no_cache_trace, cache_trace, unsplit_trace = cost_stage.cost_by_stage(_ROWS).data
        self.assertIsNone(no_cache_trace.text)
        self.assertIsNone(cache_trace.text)
        self.assertEqual(list(unsplit_trace.text), ["unpriced", "$0.32", "$0.69"])
        self.assertEqual(cache_trace.customdata[2], spend_text.spend_line(_DEAREST_COST))
        self.assertIn("%{customdata}", cache_trace.hovertemplate)

    def test_nothing_unknown_stays_off_the_legend(self) -> None:
        figure = cost_stage.cost_by_stage((_ROWS[2],))
        self.assertFalse(figure.data[2].showlegend)

    def test_nothing_to_split_is_one_bar_tall(self) -> None:
        # An empty split is the shared placeholder at the height a single-row
        # panel comes to, so a card reading nothing does not stand taller than
        # the ones beside it -- unless the caller pinned a height for both
        # states.
        empty = cost_stage.cost_by_stage(())
        self.assertGreaterEqual(len(empty.layout.annotations), 1)
        self.assertEqual(
            empty.layout.height, cost_horizontal.DEFAULT_CHART_HEIGHT,
        )
        pinned = cost_stage.cost_by_stage((), height=_PINNED_HEIGHT)
        self.assertEqual(pinned.layout.height, _PINNED_HEIGHT)


if __name__ == "__main__":
    unittest.main()
