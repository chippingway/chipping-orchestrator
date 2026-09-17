# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the page draws between its read waves, and when it stops drawing.

The chrome, the banners, and the strip are what an operator watches while the
second wave is still out, so the cases below drive each pass against the
recording page in `page_render_test_support` and read back which region it
wrote into. The one case that is not about markup is the short circuit: a
window that matched no row hands nothing back, and that return is what ends the
load before the panels beneath it are paid for.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import (
    card_html,
    dispatch,
    insights,
    page_models,
    page_pipeline,
    page_states,
)
from tests.observability.dashboard.page_render_test_support import (
    LAST_COVERED_DATE,
    THEME,
    WINDOW_END_DATE,
    WINDOW_START_DATE,
    RecordingRegion,
    markup_in,
    modules,
    page,
)

_TOTAL_EVENTS = 412

_AGENT_RUNS = 57

_DISTINCT_REPOS = 3

_SPEND = 12.5

_WINDOW_DAYS = 7

# A window with rows in it, and the one that matched nothing: the second is
# what the first-wave pass leaves the page through.
_SUMMARY = Summary(
    total_events=_TOTAL_EVENTS,
    distinct_repos=_DISTINCT_REPOS,
    total_cost_usd=_SPEND,
    total_agent_runs=_AGENT_RUNS,
)

_NO_ROWS = Summary()

# The first-wave reads the strip is assembled from, none of which a case here
# gives rows to: what is under test is which of them reaches the build, not the
# arithmetic the strip owner already pins.
_FIRST_WAVE_READS = (
    "cost_coverage_rows",
    "review_round_rows",
    "throughput_rows",
    "ts_points",
)

_BANNER = insights.InsightBanner(
    severity="warning", message="Spend is up against the window before it",
)

_FIRST_TILE_LABEL = "Total spend"

_LAST_TILE_LABEL = "Rework share"

_EMPTY_WINDOW_ATTRIBUTE = "render_empty_window"

_INSIGHTS_ATTRIBUTE = "compute_insights"

_RUN_WAVES_ATTRIBUTE = "run_read_waves"

_FIRST_WAVE_ATTRIBUTE = "render_first_wave"

_UNSAFE_HTML = MappingProxyType({"unsafe_allow_html": True})


def _read_results(summary: Summary) -> dict:
    """One first wave, with only the window's own aggregates answered for."""
    answered: dict = {name: () for name in _FIRST_WAVE_READS}
    answered["prev_summary"] = Summary()
    answered["summary"] = summary
    return answered


class RenderTopbarAndMetaTest(unittest.TestCase):
    """The two slots the controls left above the panels, filled in."""

    def setUp(self) -> None:
        self.topbar = RecordingRegion()
        self.meta = RecordingRegion()
        page_pipeline.render_topbar_and_meta(
            modules(RecordingRegion()),
            page(topbar=self.topbar, meta=self.meta),
            _SUMMARY,
        )

    def test_one_pass_fills_both_slots(self) -> None:
        self._assert_the_banner_says_what_is_on_file()
        self._assert_the_line_names_the_covered_days()
        self._assert_each_landed_in_the_slot_left_for_it()

    def _assert_the_banner_says_what_is_on_file(self) -> None:
        # The banner is drawn off the extent rather than the window, so it says
        # what is on file behind whatever the filter line below narrowed to,
        # with both of its counts spelled by the page's own formatters.
        banner = markup_in(self.topbar)

        self.assertIn(f"{_DISTINCT_REPOS} repos", banner)
        self.assertIn(f"<{_TOTAL_EVENTS}> events", banner)
        self.assertIn(f"[[{_SPEND}]]", banner)

    def _assert_the_line_names_the_covered_days(self) -> None:
        # The reads below are issued under `ts < end`, so restating `end`
        # itself would name a day none of the numbers above it covered.
        line = markup_in(self.meta)

        self.assertIn(WINDOW_START_DATE, line)
        self.assertIn(LAST_COVERED_DATE, line)
        self.assertNotIn(WINDOW_END_DATE, line)
        self.assertIn(f"{_WINDOW_DAYS} days", line)
        self.assertIn(f"<{_AGENT_RUNS}> runs", line)

    def _assert_each_landed_in_the_slot_left_for_it(self) -> None:
        # Both are written once the extent behind them is known, into slots the
        # controls reserved at the top of the page -- either one written to the
        # page body instead would be drawn under the panels it heads.
        self.assertEqual(len(self.topbar.markup), 1)
        self.assertEqual(len(self.meta.markup), 1)
        for _, options in (*self.topbar.markup, *self.meta.markup):
            with self.subTest(options=options):
                self.assertEqual(options, _UNSAFE_HTML)


class RenderDashboardInsightsTest(unittest.TestCase):
    """The banners a window is worth interrupting the page for."""

    def test_a_raised_banner_reaches_the_page(self) -> None:
        # The stack is drawn by the markup owner every other banner on the page
        # is, so a fix under that owner reaches this one too.
        drawn = self._render([_BANNER])

        self.assertIn(_BANNER.message, drawn)
        self.assertEqual(drawn, card_html.insights_html([_BANNER]))

    def test_a_quiet_window_draws_no_stack_at_all(self) -> None:
        # The banners sit between the chrome and the strip, so an empty stack
        # has to draw nothing rather than an empty container the page would
        # then carry a gap for.
        self.assertEqual(self._render([]), "")

    def _render(self, banners: list) -> str:
        st = RecordingRegion()
        with patch.object(
            insights, _INSIGHTS_ATTRIBUTE, return_value=banners,
        ) as computed:
            page_pipeline.render_dashboard_insights(modules(st), _SUMMARY, ())
            self.assertEqual(computed.call_args.args, (_SUMMARY,))
        return markup_in(st)


class RenderFirstWaveTest(unittest.TestCase):
    """What one pass over the first wave draws, and what it hands back."""

    def setUp(self) -> None:
        self.topbar = RecordingRegion()
        self.meta = RecordingRegion()
        self.st = RecordingRegion()

    def test_a_window_with_rows_opens_on_the_strip(self) -> None:
        # The four tiles are the reading every panel below is compared against,
        # so they are drawn off the first wave rather than waiting for the
        # second -- and the counts they were reduced to travel on with them.
        kpis = self._render(_SUMMARY)

        self.assertIsInstance(kpis, page_models.DashboardKpis)
        self.assertEqual(kpis.tiles[0]["label"], _FIRST_TILE_LABEL)
        self.assertIn(_FIRST_TILE_LABEL, markup_in(self.st))
        self.assertIn(_LAST_TILE_LABEL, markup_in(self.st))

    def test_an_empty_window_leaves_before_the_strip(self) -> None:
        # Reporting nothing back is what the dispatch short-circuits the second
        # wave on, so a window with no event has to leave through the notice
        # rather than fall on through to a strip of zeroes.
        with patch.object(page_states, _EMPTY_WINDOW_ATTRIBUTE) as noticed:
            kpis = self._render(_NO_ROWS)
            noticed.assert_called_once()

        self.assertIsNone(kpis)
        self.assertEqual(self.st.markup, [])

    def test_the_chrome_is_drawn_either_way(self) -> None:
        # The notice keeps the page around it, so the banner and the filter
        # line are written before that branch rather than inside it.
        with patch.object(page_states, _EMPTY_WINDOW_ATTRIBUTE):
            self._render(_NO_ROWS)

        self.assertEqual(len(self.topbar.markup), 1)
        self.assertEqual(len(self.meta.markup), 1)

    def _render(self, summary: Summary):
        return page_pipeline.render_first_wave(
            modules(self.st),
            page(topbar=self.topbar, meta=self.meta),
            _read_results(summary),
        )


class LoadDashboardDataTest(unittest.TestCase):
    """The staged load, and the two answers it can come back with."""

    def test_a_completed_load_arrives_as_one_shape(self) -> None:
        # Every section below is handed the reads and the tiles together, so
        # what the dispatch hands back in two pieces is paired up here.
        read_results = {"summary": object()}
        tiles = object()

        with patch.object(
            dispatch, _RUN_WAVES_ATTRIBUTE, return_value=(read_results, tiles),
        ) as driven:
            answered = self._load(driven)

        self.assertIs(answered.read_results, read_results)
        self.assertIs(answered.kpis, tiles)

    def test_a_short_circuited_load_answers_with_none(self) -> None:
        # The dispatch reports nothing when the first-wave render ended the
        # load, and the caller passes that on rather than a half-filled shape.
        with patch.object(
            dispatch, _RUN_WAVES_ATTRIBUTE, return_value=None,
        ) as driven:
            self.assertIsNone(self._load(driven))

    def test_the_chrome_it_hands_over_is_its_own(self) -> None:
        # The dispatch draws whatever it is handed between the waves, so the
        # pass it is handed has to be the one a fix under this owner reaches.
        first_wave = {"summary": object()}
        with (
            patch.object(
                dispatch, _RUN_WAVES_ATTRIBUTE, return_value=(first_wave, ()),
            ) as driven,
            patch.object(page_pipeline, _FIRST_WAVE_ATTRIBUTE) as chrome,
        ):
            self._load(driven)
            driven.call_args.kwargs["render_first_wave"](first_wave)
            drawn_modules, _, drawn_reads = chrome.call_args.args

        self.assertIs(drawn_reads, first_wave)
        self.assertIs(drawn_modules.theme, THEME)

    def _load(self, driven):
        st = RecordingRegion()
        page_state = page(reads=SimpleNamespace(parallel=True))
        answered = page_pipeline.load_dashboard_data(modules(st), page_state)
        self.assertIs(driven.call_args.args[0], page_state.reads)
        self.assertIs(driven.call_args.kwargs["st"], st)
        return answered


if __name__ == "__main__":
    unittest.main()
