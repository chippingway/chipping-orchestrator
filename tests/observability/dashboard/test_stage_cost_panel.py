# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The paired lifecycle bars a window's spend is split across.

The cases name what the section decides rather than what the two chart families
draw: the split the columns are laid out in, which axis lands in the wider one,
and -- the reading the whole pairing exists for -- the single height both
figures are pinned to. A bar family sizes itself by its own row count and the
legend band above it, so the cases drive windows whose two axes disagree on how
many buckets and legend lines they carry, read the height each figure was
handed straight back off the builder, and check every row of either split
still has its full height once its legend band is taken off the top.

Both builders are the section's own module-scope imports rather than a handle
it is passed, so a recorder stands in for them under `patch.object` on this
owner -- which is also what says the section reaches the two cost families
directly, since a stub planted here would not be seen at all if it went on
resolving a builder through something handed in.

The Plotly configuration is likewise reached rather than handed, so a case
patches it on the owner that holds it and drives the render, which is what says
the toolbar decision is resolved at call time rather than captured when this
module was imported.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.dashboard import render_config, stage_cost_panel
from orchestrator.observability.dashboard.charts import cost_horizontal, cost_review, cost_stage, primitives
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard import lifecycle_window_test_support as window
from tests.observability.dashboard.cost_panel_test_support import (
    COLUMN_RATIO,
    LEFT,
    RIGHT,
    CostPanelStreamlit,
    RecordingCharts,
    markup_in,
)

_STAGE_BUILDER = "cost_by_stage"

_ROUND_BUILDER = "cost_by_review_round"

# Two axes that disagree on bucket count, so the shared height is attributable
# to the longer of them rather than to whichever figure was drawn first.
_STAGES = ("implementing", "in_review", "validating")

_ROUNDS = ("0", "1")

# The row heights and base each split is sized from, restated here so a case
# reads the arithmetic rather than the owner's own expression back: a stage
# row, a review row holding two bars, and the margin and axis base beneath.
_ROW_HEIGHT = 40

_REVIEW_ROW_HEIGHT = 44

_BASE_HEIGHT = 80

# The legend bands those windows list: two shares for the stage split, two per
# role for the review split, and a third per series where something is unsplit.
_STAGE_BAND = primitives.legend_band_height(2)

_REVIEW_BAND = primitives.legend_band_height(4)

_FULL_REVIEW_BAND = primitives.legend_band_height(6)

# The heights the pairing comes to: two rounds beside three stages, six rounds
# beside one stage, and six stages beside two rounds.
_TWO_ROUNDS_HEIGHT = _REVIEW_ROW_HEIGHT * len(_ROUNDS) + _BASE_HEIGHT + _REVIEW_BAND

_SIX_ROUNDS_HEIGHT = _REVIEW_ROW_HEIGHT * len(window.ALL_ROUNDS) + _BASE_HEIGHT + _REVIEW_BAND

_SIX_STAGES_HEIGHT = _ROW_HEIGHT * len(_STAGES) * 2 + _BASE_HEIGHT + _STAGE_BAND

_TOOLBAR_KEY = "displayModeBar"

# The Streamlit options each call carries, named rather than spelled at every
# assertion.
_MARKUP_OPTION = "unsafe_allow_html"

_WIDTH_OPTION = "use_container_width"

_CONFIG_OPTION = "config"

_CLI_REPORTED = "CLI-reported"


# Every stage spends one CLI-reported run and every round one AGY review, so
# the note under each figure totals its bars on the basis they share.
_STAGE_COST = cohort_cases.cohort(cases.REPORTED)

_ROUND_COST = cohort_cases.cohort(cases.GEMINI_ESTIMATE)


def stage_rows(*stages: str) -> list[StageBreakdown]:
    """One breakdown row per named workflow stage."""
    return [
        StageBreakdown(stage=stage, count=1, runs=1, cost=_STAGE_COST)
        for stage in stages
    ]


def review_rows(*buckets: str) -> list[ReviewRoundBucketRow]:
    """One review row per named round bucket."""
    return [
        ReviewRoundBucketRow(bucket=bucket, runs=1, reviewer_cost=_ROUND_COST)
        for bucket in buckets
    ]


def render_bars(
    stages: tuple[str, ...] = _STAGES,
    rounds: tuple[str, ...] = _ROUNDS,
) -> tuple[CostPanelStreamlit, RecordingCharts]:
    """Draw the whole section for those two axes onto a fake page."""
    page = CostPanelStreamlit()
    charts = RecordingCharts()
    with (
        patch.object(stage_cost_panel, _STAGE_BUILDER, charts.cost_by_stage),
        patch.object(
            stage_cost_panel, _ROUND_BUILDER, charts.cost_by_review_round,
        ),
    ):
        stage_cost_panel.render_stage_review_bars(
            st=page,
            stage_rows=stage_rows(*stages),
            review_round_rows=review_rows(*rounds),
        )
    return page, charts


class PairedBarsHeightTest(unittest.TestCase):
    """One height, measured off whichever split needs more for its rows beneath its legend."""

    def test_the_split_needing_more_sets_the_height(self) -> None:
        # Fewer review rounds than stages can still need more height, since a
        # review row holds two bars and its legend lists both roles.
        for stages, rounds, expected in (
            (_STAGES, _ROUNDS, _TWO_ROUNDS_HEIGHT),
            (_STAGES[:1], window.ALL_ROUNDS, _SIX_ROUNDS_HEIGHT),
            (_STAGES * 2, _ROUNDS, _SIX_STAGES_HEIGHT),
        ):
            with self.subTest(stages=len(stages), rounds=len(rounds)):
                self.assertEqual(
                    stage_cost_panel.paired_bars_height(stage_rows(*stages), review_rows(*rounds)),
                    expected,
                )

    def test_each_row_keeps_its_height_under_a_legend(self) -> None:
        # Pinned to one height, each split still gives every bucket a full row
        # once its legend band is taken off the top, so two-line labels stay
        # apart however many lines the legend lists.
        height = stage_cost_panel.paired_bars_height(window.PARTLY_SPLIT_STAGES, window.PARTLY_SPLIT_ROUNDS)
        layouts = (
            (
                cost_stage.stage_cost_layout(cost_stage.stage_cost_bars(window.PARTLY_SPLIT_STAGES), height),
                _ROW_HEIGHT,
            ),
            (
                cost_review.review_cost_layout(cost_review.review_cost_bars(window.PARTLY_SPLIT_ROUNDS), height),
                _REVIEW_ROW_HEIGHT,
            ),
        )
        self.assertEqual(layouts[1][0].legend_band, _FULL_REVIEW_BAND)
        for layout, row_height in layouts:
            with self.subTest(rows=layout.row_count):
                beneath_legend = height - layout.legend_band - _BASE_HEIGHT
                self.assertGreaterEqual(beneath_legend, row_height * layout.row_count)

    def test_an_empty_window_is_one_placeholder_tall(self) -> None:
        # A window neither axis reported on is drawn as the placeholder each
        # family renders instead, at the height an empty cost panel comes to
        # rather than one that would collapse the card it is drawn in.
        self.assertEqual(
            stage_cost_panel.paired_bars_height([], []),
            cost_horizontal.DEFAULT_CHART_HEIGHT,
        )


class ChartBindingTest(unittest.TestCase):
    """Both figures are the cost owners' own builders, not a handed-in hub."""

    def test_each_axis_is_bound_to_its_own_family(self) -> None:
        # A section is the card and the figure inside it together. Reaching a
        # builder through a handle the caller passed down would let the two
        # halves of one pairing be assembled from different chart families --
        # and a pairing whose whole point is one shared height is exactly the
        # place two families that measure it differently would show.
        self.assertIs(
            getattr(stage_cost_panel, _STAGE_BUILDER),
            cost_stage.cost_by_stage,
        )
        self.assertIs(
            getattr(stage_cost_panel, _ROUND_BUILDER),
            cost_review.cost_by_review_round,
        )


class StageBarsRenderOptionTest(unittest.TestCase):
    """Each payload is handed over the way it has to be to be seen."""

    def test_each_axis_is_drawn_in_a_bordered_card(self) -> None:
        # The outline is what makes each figure read as its own panel rather
        # than as two halves of one strip drawn across the gutter.
        page, _ = render_bars()
        self.assertEqual(page.borders, [(LEFT, True), (RIGHT, True)])

    def test_the_headers_and_notes_are_markup(self) -> None:
        # A header and the note under a figure are HTML the markup owner
        # built, so a column handed one without this flag prints the tags an
        # operator was meant to read through.
        page, _ = render_bars()
        self.assertEqual(len(page.markdowns), 2 * len(page.figures))
        for drawn in page.markdowns:
            with self.subTest(column=drawn.column):
                self.assertIs(drawn.options[_MARKUP_OPTION], True)

    def test_each_figure_fills_the_column_it_is_in(self) -> None:
        # Both panels are sized by the 7:5 split above them, so a figure left
        # at Plotly's own width would sit in a column measured for something
        # else and break the alignment the shared height buys.
        page, _ = render_bars()
        for drawn in page.figures:
            with self.subTest(column=drawn.column):
                self.assertIs(drawn.options[_WIDTH_OPTION], True)


class StageReviewBarsTest(unittest.TestCase):
    """The section lays both figures out and sizes them as one."""

    def test_both_figures_share_one_height(self) -> None:
        _, charts = render_bars()
        heights = {request.height for request in charts.requests}
        self.assertEqual(
            heights, {_TWO_ROUNDS_HEIGHT},
        )

    def test_the_stage_axis_takes_the_wider_column(self) -> None:
        page, charts = render_bars()
        self.assertEqual(page.column_request, COLUMN_RATIO)
        drawn_in = {
            drawn.column: drawn.payload.builder for drawn in page.figures
        }
        self.assertEqual(
            drawn_in, {LEFT: _STAGE_BUILDER, RIGHT: _ROUND_BUILDER},
        )
        self.assertEqual(len(charts.requests), len(page.figures))

    def test_each_column_is_headed_by_its_own(self) -> None:
        page, _ = render_bars()
        self.assertIn("Cost by workflow stage", markup_in(page, LEFT))
        self.assertIn(
            "Development and review by round", markup_in(page, RIGHT),
        )

    def test_each_figure_is_closed_by_its_note(self) -> None:
        # What the bars add up to is worded under each figure with its basis --
        # an AGY-only review spend as a Gemini API token estimate -- and the
        # cache and non-cache segments are said to be a token-share allocation
        # rather than a measured cache charge.
        page, _ = render_bars()
        self.assertIn(f"Bars total $1.26 ({_CLI_REPORTED})", markup_in(page, LEFT))
        self.assertIn("Bars total $0.24 (Gemini API token estimate)", markup_in(page, RIGHT))
        for column in (LEFT, RIGHT):
            with self.subTest(column=column):
                self.assertIn("not a measured cache charge", markup_in(page, column))

    def test_an_empty_split_notes_nothing(self) -> None:
        page, _ = render_bars(stages=(), rounds=())
        self.assertEqual(len(page.markdowns), len(page.figures))
        self.assertNotIn("Bars total", markup_in(page, LEFT) + markup_in(page, RIGHT))

    def test_the_toolbar_choice_is_read_at_call(self) -> None:
        # Every figure on the page is drawn under one configuration, and the
        # owner publishes it as a proxy Plotly cannot serialize -- so each
        # chart is handed a plain-dict copy of whatever that owner holds when
        # the section runs.
        sentinel = {_TOOLBAR_KEY: True}
        with patch.object(render_config, "PLOTLY_CONFIG", sentinel):
            page, _ = render_bars()
        handed = [drawn.options[_CONFIG_OPTION] for drawn in page.figures]
        self.assertEqual(handed, [sentinel, sentinel])
        for config in handed:
            self.assertIsInstance(config, dict)
            self.assertIsNot(config, sentinel)


if __name__ == "__main__":
    unittest.main()
