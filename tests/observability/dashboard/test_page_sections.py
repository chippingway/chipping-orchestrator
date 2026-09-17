# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the panels under the figures put on the page, and in what order.

The four sections beneath the figure cards are each their own owner; what this
owner decides is the order they are drawn in and what each is drawn from. The
pass runs for real against the recording page, so one scenario answers all of
that off what an operator would see: the heading each section names itself by,
in the order the page wrote them; the three skill views, each reporting the one
word its own read carries; the run listing on the clock the sidebar picked; and
the trace and the footer narrowed by what the controls resolved rather than by
anything the reads came back with.

The whole second wave is that same page with the figure cards above it. Plotly
lives in the optional `dashboard` group and every card reaches for it, so that
half is stood in for on its own owner by a line naming the window it was handed
-- which is what makes both halves drawing one page state readable off the page
itself, beside the order they reached it in.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from datetime import timedelta
from unittest.mock import patch

from orchestrator.observability.dashboard import (
    chart_sections,
    drilldown,
    page_models,
    page_sections,
    recent_runs,
)
from tests.observability.dashboard.page_render_test_support import (
    LAST_COVERED_DATE,
    TZ_OFFSET,
    WINDOW_START_DATE,
    loaded,
    markup_in,
    modules,
    page,
)
from tests.observability.dashboard.section_render_test_support import (
    AGENT_RUNS,
    ISSUE_NUMBER,
    RUN_ISSUES,
    SKILL_READS,
    RecordingPage,
    frames,
    section_rows,
)

_CHART_HALF = "render_chart_widgets"

_SKILL_CARD = "Skill adoption"

_ISSUE_TRACE = f"Issue #{ISSUE_NUMBER} drill-down"

_FOOTER = f"window {WINDOW_START_DATE} → {LAST_COVERED_DATE}"

# The four sections in page order, each named by the heading it puts on screen.
_SECTIONS = (
    _SKILL_CARD,
    recent_runs.RECENT_RUNS_LABEL,
    _ISSUE_TRACE,
    _FOOTER,
)

# The line the figure half is stood in for by. It names the window that half
# was handed, so the page itself says which state it was drawn from.
_FIGURE_CARDS = f"figure cards · {WINDOW_START_DATE}"

_TS_COLUMN = "ts"

_ISSUE_COLUMN = "issue"


def _draw_figure_line(
    handles: page_models.DashboardModules,
    page_state: page_models.DashboardPage,
    read_results: page_models.LoadedDashboard,
) -> None:
    """Stand in for the figure cards, naming the window they were opened on."""
    window = page_state.controls.filters.window
    opened_on = window.start.date()
    handles.st.subheader(f"figure cards · {opened_on}")


def _drawn_in_order(drawn: str, sections: Sequence[str]) -> list[str]:
    """The sections that reached the page, in the order it wrote them."""
    return sorted(
        (section for section in sections if section in drawn), key=drawn.index,
    )


class PageSectionRenderTest(unittest.TestCase):
    """What one pass over the panels beneath the figure cards draws."""

    def setUp(self) -> None:
        self.st = RecordingPage()
        page_sections.render_remaining_widgets(
            modules(self.st, frames=frames()),
            page(issue=ISSUE_NUMBER),
            loaded(section_rows()),
        )
        self.drawn = markup_in(self.st)

    def test_one_pass_draws_the_four_sections(self) -> None:
        self._assert_the_sections_follow_in_page_order()
        self._assert_each_skill_view_reports_its_read()
        self._assert_the_listing_reads_the_picked_zone()
        self._assert_the_trace_and_footer_are_filtered()

    def _assert_the_sections_follow_in_page_order(self) -> None:
        # The skill card reports what the runs behind the figures were working
        # with, the listing is the rows every reading above was reduced from,
        # the trace is one of those rows opened out, and the footer restates
        # what all of it was measured over -- so it is last.
        self.assertEqual(
            _drawn_in_order(self.drawn, _SECTIONS), list(_SECTIONS),
        )

    def _assert_each_skill_view_reports_its_read(self) -> None:
        # The card is drawn from three reads at once, so a view handed the
        # wrong one reports a word none of its own rows carry.
        for reported in SKILL_READS:
            with self.subTest(reported=reported):
                self.assertIn(f">{reported}<", self.drawn)

    def _assert_the_listing_reads_the_picked_zone(self) -> None:
        # It is the one section drawn through pandas, and its timestamps are
        # read in the zone the sidebar picked rather than left in UTC.
        self.assertEqual(len(self.st.frames), 1)
        listed = self.st.frames[0]

        self.assertEqual(
            [run[_ISSUE_COLUMN] for run in listed], list(RUN_ISSUES),
        )
        self.assertEqual(
            listed[0][_TS_COLUMN].utcoffset(), timedelta(hours=TZ_OFFSET),
        )

    def _assert_the_trace_and_footer_are_filtered(self) -> None:
        # The trace refuses to open on a number until a repository is picked
        # beside it, which is a reading of the filters the controls resolved
        # rather than of anything the reads answered; the footer closes on that
        # same filter set's span, with the window's run count spelled by the
        # page's own formatter.
        self.assertIn(drilldown.MISSING_REPO_MESSAGE, self.drawn)
        self.assertIn(f"<{AGENT_RUNS}> agent runs", self.drawn)


class DashboardWidgetsRenderTest(unittest.TestCase):
    """The whole second wave on one page, in the order the page draws it."""

    def test_the_figure_cards_open_the_page(self) -> None:
        # Splitting the order across two calls is what lets a caller draw
        # either half against a stand-in; keeping the pair in one call is what
        # keeps the page's order readable from a single place. The window the
        # stood-in half names is the one the footer closes on, so both halves
        # are drawn from the state the wave was opened with.
        st = RecordingPage()
        with patch.object(chart_sections, _CHART_HALF, _draw_figure_line):
            page_sections.render_dashboard_widgets(
                modules(st, frames=frames()),
                page(issue=ISSUE_NUMBER),
                loaded(section_rows()),
            )

        drawn = markup_in(st)
        self.assertEqual(
            _drawn_in_order(drawn, (_FIGURE_CARDS, *_SECTIONS)),
            [_FIGURE_CARDS, *_SECTIONS],
        )


if __name__ == "__main__":
    unittest.main()
