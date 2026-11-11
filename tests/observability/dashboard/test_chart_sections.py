# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order a window's figure cards are drawn in, and what each is handed.

Every card here is its own owner and pinned beside it; what this owner decides
is which of them the second wave reaches first and which read family each is
given. The cases stub every panel on the module that holds it -- which is also
the check that the pass names the owners rather than resolving a render off a
facade -- and answer each read with its own key, so a card handed the wrong
family reads back as the wrong word.
"""

from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType

from orchestrator.observability.dashboard import (
    activity_panel,
    chart_sections,
    issue_cost_panel,
    page_models,
    reliability_panel,
    stage_cost_panel,
    usage_panel,
)
from tests.observability.dashboard.page_render_test_support import (
    THEME,
    TZ_OFFSET,
    WINDOW,
    draw_sections,
    loaded,
    modules,
    page,
    section_reads,
)

_HERO_CARD = "render_hero_usage"

_LIFECYCLE_BARS = "render_stage_review_bars"

_ISSUE_RANKING = "render_issues_and_backends"

_REPOSITORY_PAIR = "render_repo_and_reliability"

_ACTIVITY_GRID = "render_activity_heatmap"

# The five cards, in the order the page stacks them and paired with the owner
# each is stubbed on.
_CHART_PANELS = (
    (usage_panel, _HERO_CARD),
    (stage_cost_panel, _LIFECYCLE_BARS),
    (issue_cost_panel, _ISSUE_RANKING),
    (reliability_panel, _REPOSITORY_PAIR),
    (activity_panel, _ACTIVITY_GRID),
)

# What each keyword-taking card is drawn from. The reads answer with their own
# keys, so the expected value of every one of these is the name itself.
_CARD_READS = MappingProxyType({
    _HERO_CARD: ("ts_points", "backend_daily_rows"),
    _LIFECYCLE_BARS: ("stage_rows", "review_round_rows"),
    _ISSUE_RANKING: ("issues_rows", "backend_rows"),
    _ACTIVITY_GRID: ("heatmap_rows",),
})

# The counts the run-health tiles report, carried down from the strip the first
# wave already drew rather than reduced a second time here.
_RESOLVED = 9

_REJECTED = 2


class ChartSectionOrderTest(unittest.TestCase):
    """Which card the second wave reaches first, and what each is given."""

    def setUp(self) -> None:
        self.st = object()
        drawn, recorder = draw_sections(
            _CHART_PANELS,
            partial(
                chart_sections.render_chart_widgets,
                modules(self.st),
                page(),
                loaded(
                    section_reads(),
                    resolved=_RESOLVED,
                    rejected=_REJECTED,
                ),
            ),
        )
        self.drawn = drawn
        self.recorder = recorder

    def test_the_cards_stack_in_page_order(self) -> None:
        # The order is the page's argument rather than a layout preference: the
        # hero card asks whether a day's cost tracked the work behind it, the
        # three beneath it say where that cost went and whether it held up, and
        # the grid is the only one keeping the clock, so it closes the run.
        self.assertEqual(
            self.drawn, [attribute for _, attribute in _CHART_PANELS],
        )

    def test_each_card_is_handed_the_reads_it_draws(self) -> None:
        for card, reads in _CARD_READS.items():
            drawn = getattr(self.recorder, card).call_args.kwargs
            with self.subTest(card=card):
                self.assertIs(drawn["st"], self.st)
                self.assertEqual(
                    {name: drawn[name] for name in reads},
                    {name: name for name in reads},
                )

    def test_the_ranking_is_handed_the_page_s_theme(self) -> None:
        # It is the one card that formats a reading itself rather than handing
        # rows to a figure, so it needs the same formatters the tiles above it
        # were spelled by.
        self.assertIs(
            getattr(self.recorder, _ISSUE_RANKING).call_args.kwargs["theme"],
            THEME,
        )

    def test_the_repository_pair_is_handed_one_shape(self) -> None:
        # It is the only card drawn from four reads at once, so it takes a
        # shape rather than positional rows a repo list and a throughput series
        # could be swapped between -- and the two counts on it come off the
        # strip the first wave drew rather than a second reduction here.
        drawn_modules, panel = getattr(
            self.recorder, _REPOSITORY_PAIR,
        ).call_args.args

        self.assertIs(drawn_modules.st, self.st)
        self.assertIsInstance(panel, page_models.ReliabilityPanelData)
        self.assertEqual(
            (panel.repos, panel.summary, panel.throughput),
            ("repo_rows", "summary", "throughput_rows"),
        )
        self.assertEqual(panel.window, WINDOW)
        self.assertEqual((panel.resolved, panel.rejected), (_RESOLVED, _REJECTED))

    def test_the_grid_is_handed_the_picked_zone(self) -> None:
        # The grid buckets its cells by the hour they landed on, so the offset
        # the sidebar picked has to reach it or the label and the cells would
        # be read in two different zones.
        self.assertEqual(
            getattr(self.recorder, _ACTIVITY_GRID).call_args.kwargs[
                "tz_offset_choice"
            ],
            TZ_OFFSET,
        )


if __name__ == "__main__":
    unittest.main()
