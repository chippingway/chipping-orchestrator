# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the panels under the figures put on the page, and in what order.

The four sections beneath the figure cards are each their own owner; what this
owner decides is the order they are drawn in and what each is drawn from. The
pass runs for real against the recording page, so one scenario answers all of
that off what an operator would see: every heading the page wrote, in order and
as many times as it wrote it; the three skill views, each reporting the one
word its own read carries; the run listing on the clock the sidebar picked; and
the trace narrowed by the window, events, and stages the controls resolved
rather than by anything the load came back with.

The trace is the one section drawn from a read of its own, so its scope entry
is stood in for on its defining owner by one that answers with the bounds it
was handed. That turns every narrowing the section passed down into a row of
the table, which is why a wrong window, event set, or stage set reads back as a
different table rather than the same one.

The whole second wave is that same page with the figure cards above it. Plotly
lives in the optional `dashboard` group and every card reaches for it, so that
half is stood in for on its own owner by a line naming the window and the run
count it was handed -- which is what makes both halves drawing one page state
readable off the page itself, beside the order they reached it in.
"""

from __future__ import annotations

import re
import unittest
from collections.abc import Callable, Sequence
from datetime import timedelta
from unittest.mock import patch

from orchestrator.observability.dashboard import (
    chart_sections,
    page_models,
    page_sections,
    recent_runs,
    scoped_reads,
)
from tests.observability.dashboard import (
    section_render_test_support as fixtures,
)
from tests.observability.dashboard.page_render_test_support import (
    LAST_COVERED_DATE,
    TZ_OFFSET,
    WINDOW_END_DATE,
    WINDOW_START_DATE,
    loaded,
    markup_in,
    modules,
    page,
)

_CHART_HALF = "render_chart_widgets"

_SCOPE_ENTRY = "scoped_read"

_SKILL_CARD = "Skill adoption"

_ISSUE_TRACE = f"Issue #{fixtures.ISSUE_NUMBER} drill-down"

_FOOTER = f"window {WINDOW_START_DATE} → {LAST_COVERED_DATE}"

# The four sections in page order, each named by the heading it puts on screen.
_SECTIONS = (
    _SKILL_CARD,
    recent_runs.RECENT_RUNS_LABEL,
    _ISSUE_TRACE,
    _FOOTER,
)

# The line the figure half is stood in for by. It names the window and the
# window's run count that half was handed, so the page itself says which state
# and which load it was drawn from.
_FIGURE_CARDS = (
    f"figure cards · {WINDOW_START_DATE} · {fixtures.AGENT_RUNS} runs"
)

_TS_COLUMN = "ts"

_ISSUE_COLUMN = "issue"

_EVENT_COLUMN = "event"

_STAGE_COLUMN = "stage"

_RESULT_COLUMN = "result"


def _draw_figure_line(
    handles: page_models.DashboardModules,
    page_state: page_models.DashboardPage,
    read_results: page_models.LoadedDashboard,
) -> None:
    """Stand in for the figure cards, naming the state they were drawn from."""
    window = page_state.controls.filters.window
    opened_on = window.start.date()
    summary = read_results.read_results["summary"]
    measured = summary.total_agent_runs
    handles.st.subheader(f"figure cards · {opened_on} · {measured} runs")


def _drawn_wave(
    render: Callable[..., None], drawn_onto: fixtures.RecordingPage,
) -> str:
    """Run one pass over `drawn_onto`, with the trace's read seam stood in for."""
    with patch.object(scoped_reads, _SCOPE_ENTRY, fixtures.traced_reads):
        render(
            modules(drawn_onto, frames=fixtures.frames()),
            page(filters=fixtures.traced_filters()),
            loaded(fixtures.section_rows()),
        )
    return markup_in(drawn_onto)


def _sections_drawn(drawn: str, sections: Sequence[str]) -> list[str]:
    """Every section the page drew, in order and as often as it drew it."""
    headings = [re.escape(section) for section in sections]
    return re.findall("|".join(headings), drawn)


class PageSectionRenderTest(unittest.TestCase):
    """What one pass over the panels beneath the figure cards draws."""

    def setUp(self) -> None:
        self.st = fixtures.RecordingPage()
        self.drawn = _drawn_wave(
            page_sections.render_remaining_widgets, self.st,
        )

    def test_one_pass_draws_the_four_sections(self) -> None:
        self._assert_the_sections_follow_in_page_order()
        self._assert_each_skill_view_reports_its_read()
        self._assert_the_listing_reads_the_picked_zone()
        self._assert_the_trace_reads_the_picked_filters()

    def _assert_the_sections_follow_in_page_order(self) -> None:
        # The skill card reports what the runs behind the figures were working
        # with, the listing is the rows every reading above was reduced from,
        # the trace is one of those rows opened out, and the footer restates
        # what all of it was measured over -- so it is last, and each of the
        # four is drawn once rather than once per read it consulted.
        self.assertEqual(
            _sections_drawn(self.drawn, _SECTIONS), list(_SECTIONS),
        )

    def _assert_each_skill_view_reports_its_read(self) -> None:
        # The card is drawn from three reads at once, so a view handed the
        # wrong one reports a word none of its own rows carry.
        for reported in fixtures.SKILL_READS:
            with self.subTest(reported=reported):
                self.assertIn(f">{reported}<", self.drawn)

    def _assert_the_listing_reads_the_picked_zone(self) -> None:
        # The listing is the first of the two tables on the page, and its
        # timestamps are read in the zone the sidebar picked rather than left
        # in UTC.
        listed = self.st.frames[0]

        self.assertEqual(
            [run[_ISSUE_COLUMN] for run in listed],
            list(fixtures.RUN_ISSUES),
        )
        self.assertEqual(
            listed[0][_TS_COLUMN].utcoffset(), timedelta(hours=TZ_OFFSET),
        )

    def _assert_the_trace_reads_the_picked_filters(self) -> None:
        # The trace is narrowed by what the controls resolved rather than by
        # anything the load answered, so the read behind it reports every
        # narrowing back as a row: one per event and stage it was bound to,
        # stamped with the window's own start and naming the issue it was
        # scoped to. The footer closes on that same window and run count.
        scope = fixtures.TRACE_SCOPE.format(
            repo=fixtures.RUN_REPO,
            issue=fixtures.ISSUE_NUMBER,
            end=WINDOW_END_DATE,
        )

        # A trace bound to something the sidebar did not resolve comes back
        # with no row at all, which the section answers with a notice instead
        # of the second table -- so the count is asked before the rows are.
        self.assertEqual(len(self.st.frames), 2)
        traced = self.st.frames[1]

        self.assertEqual(
            [(row[_EVENT_COLUMN], row[_STAGE_COLUMN]) for row in traced],
            [
                (event, fixtures.TRACE_STAGES[0])
                for event in fixtures.TRACE_EVENTS
            ],
        )
        self.assertEqual(
            {row[_TS_COLUMN].isoformat() for row in traced},
            {f"{WINDOW_START_DATE}T00:00:00+00:00"},
        )
        self.assertEqual({row[_RESULT_COLUMN] for row in traced}, {scope})
        self.assertIn(f"<{fixtures.AGENT_RUNS}> agent runs", self.drawn)


class DashboardWidgetsRenderTest(unittest.TestCase):
    """The whole second wave on one page, in the order the page draws it."""

    def test_the_figure_cards_open_the_page(self) -> None:
        # Splitting the order across two calls is what lets a caller draw
        # either half against a stand-in; keeping the pair in one call is what
        # keeps the page's order readable from a single place. The window and
        # the run count the stood-in half names are the ones the footer closes
        # on, so both halves are drawn from the one page state and the one
        # load the wave was opened with.
        st = fixtures.RecordingPage()
        with patch.object(chart_sections, _CHART_HALF, _draw_figure_line):
            drawn = _drawn_wave(page_sections.render_dashboard_widgets, st)

        self.assertEqual(
            _sections_drawn(drawn, (_FIGURE_CARDS, *_SECTIONS)),
            [_FIGURE_CARDS, *_SECTIONS],
        )


if __name__ == "__main__":
    unittest.main()
