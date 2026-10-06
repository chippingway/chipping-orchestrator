# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's spend is split per stage, tinted, ranked, and drawn."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import cost_horizontal, cost_stage

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEAREST = "implementing"

_CHEAPEST = "validating"

_DEAREST_TOTAL = 12.0

_DEAREST_CACHE = 9.0

_NO_CACHE = 3.0

_CHEAPEST_TOTAL = 4.0

_CHEAPEST_CACHE = 1.0

_DEAREST_RUNS = 8

_EVENT_COUNT = 20

_PINNED_HEIGHT = 320

_SAMPLE_HUE = "#5b54e0"

# Two stages whose bars differ in every column that matters: the dearest is
# mostly cache, the cheapest mostly full price, and the caller hands them over
# dearest first, so both the ranking and the flip for the axis are visible in
# what comes back.
_ROWS = (
    StageBreakdown(
        stage=_DEAREST,
        count=_EVENT_COUNT,
        total_cost_usd=_DEAREST_TOTAL,
        runs=_DEAREST_RUNS,
        cache_cost_usd=_DEAREST_CACHE,
        no_cache_cost_usd=_NO_CACHE,
    ),
    StageBreakdown(
        stage=_CHEAPEST,
        count=5,
        total_cost_usd=_CHEAPEST_TOTAL,
        runs=3,
        cache_cost_usd=_CHEAPEST_CACHE,
        no_cache_cost_usd=_NO_CACHE,
    ),
)

# A window read before the cache split existed: both halves sit at the
# dataclass default and only the total says the stage cost anything.
_UNSPLIT_ROW = StageBreakdown(
    stage=_DEAREST,
    count=10,
    total_cost_usd=_DEAREST_TOTAL,
    runs=_DEAREST_RUNS,
)


class StageSplitTest(unittest.TestCase):
    """The order and sub-line the seven columns come back in."""

    def test_spend_ranks_it_dearest_bar_last(self) -> None:
        # A Plotly bar axis draws the first row at the bottom, so the split
        # arrives flipped for the dearest stage to sit on top -- every column
        # together, or a label would part company with the amounts beside it.
        bars = cost_stage.stage_cost_bars(_ROWS)
        self.assertEqual(tuple(bars.labels), (_CHEAPEST, _DEAREST))
        self.assertEqual(tuple(bars.cache), (_CHEAPEST_CACHE, _DEAREST_CACHE))
        self.assertEqual(tuple(bars.totals), (_CHEAPEST_TOTAL, _DEAREST_TOTAL))

    def test_an_unpriced_stage_ranks_below_a_priced(self) -> None:
        self.assertEqual(
            cost_stage.stage_cost_sort_key(_ROWS[0]), -_DEAREST_TOTAL,
        )
        self.assertEqual(
            cost_stage.stage_cost_sort_key(StageBreakdown(stage="ready", count=0)),
            0,
        )

    def test_the_sub_line_counts_runs_not_events(self) -> None:
        # `count` is every analytics row carrying the stage, `runs` the agent
        # exits that reported the spend a bar is drawn from, so a stage with 20
        # events behind 8 runs is labelled by the 8.
        bars = cost_stage.stage_cost_bars((_ROWS[0],))
        self.assertEqual(tuple(bars.subs), (f"{_DEAREST_RUNS} runs",))


class CacheShadingTest(unittest.TestCase):
    """Both halves of a bar are tinted from the stage's one hue."""

    def test_the_cache_half_shades_the_stage_hue(self) -> None:
        # A palette of its own for the cache halves would read as four stages
        # rather than two split two ways, so the cache half is the same hue at
        # the shared opacity.
        bars = cost_stage.stage_cost_bars((_ROWS[0],))
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


class FullTokenDenominatorTest(unittest.TestCase):
    """A stage with no split still reads at its true length."""

    def test_a_row_with_neither_half_plots_its_total(self) -> None:
        # Falling through would draw an empty bar for spend that happened, so
        # the whole total becomes the full-price half.
        self.assertEqual(
            cost_stage.stage_no_cache_cost(_UNSPLIT_ROW), _DEAREST_TOTAL,
        )

    def test_a_split_row_keeps_the_half_it_has(self) -> None:
        # The fallback is only for the unsplit row: a stage that was all cache
        # has a full-price half of zero, and reading its total there would
        # double the bar.
        all_cache = StageBreakdown(
            stage=_DEAREST,
            count=1,
            total_cost_usd=_DEAREST_TOTAL,
            runs=1,
            cache_cost_usd=_DEAREST_TOTAL,
        )
        self.assertEqual(cost_stage.stage_no_cache_cost(all_cache), 0)
        self.assertEqual(cost_stage.stage_no_cache_cost(_ROWS[0]), _NO_CACHE)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class StageFigureTest(unittest.TestCase):
    """What the builder draws, including the window that split nothing."""

    def test_the_two_halves_are_stacked_per_stage(self) -> None:
        # Stacked rather than drawn side by side, so a bar's length stays the
        # stage's whole spend and the split inside it reads as the cache's
        # share of it.
        figure = cost_stage.cost_by_stage(_ROWS)
        no_cache_trace, cache_trace = figure.data
        self.assertEqual(figure.layout.barmode, "stack")
        self.assertEqual(
            [no_cache_trace.name, cache_trace.name], ["No cache", "Cache"],
        )
        self.assertEqual(list(no_cache_trace.x), [_NO_CACHE, _NO_CACHE])
        self.assertEqual(list(cache_trace.x), [_CHEAPEST_CACHE, _DEAREST_CACHE])
        for stage in (_DEAREST, _CHEAPEST):
            with self.subTest(stage=stage):
                self.assertTrue(any(stage in tick for tick in no_cache_trace.y))

    def test_only_the_outer_half_is_labelled(self) -> None:
        # The dollar text lands once per bar instead of once per segment, so
        # the base is left bare and the cache half carries the stage's total.
        no_cache_trace, cache_trace = cost_stage.cost_by_stage(_ROWS).data
        self.assertIsNone(no_cache_trace.text)
        self.assertEqual(list(cache_trace.text), ["$4.00", "$12"])

    def test_an_unsplit_row_draws_its_whole_total(self) -> None:
        figure = cost_stage.cost_by_stage((_UNSPLIT_ROW,))
        no_cache_trace, cache_trace = figure.data
        self.assertEqual(list(no_cache_trace.x), [_DEAREST_TOTAL])
        self.assertEqual(list(cache_trace.x), [float(0)])

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
