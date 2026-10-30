# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the page says when it has nothing to draw, and how it signs off.

Streamlit lives in the optional `dashboard` dependency group, so the cases
below hand each render a stand-in recording the markup, the notices, and the
stop that ends the script -- which is the whole of what this owner reaches
Streamlit for. All three land in one list as well, so a case can say what was
drawn before the script ended rather than only that it did. The theme is faked
the same way, marking every reading a formatter was handed, so a count reaching
the markup raw can be told from one the page shortened.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from orchestrator.observability.analytics.query.overview_models import (
    DataExtent,
    Summary,
)
from orchestrator.observability.dashboard import (
    dispatch,
    drilldown,
    page_models,
    page_states,
    windows,
)

_YEAR = 2026

_MAY = 5

_WINDOW_START = datetime(_YEAR, _MAY, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, _MAY, 8, tzinfo=UTC)

# The half-open window's own dates, and the day the footer closes on: the reads
# beneath the page stop before `end`, so the last day any of them covered is
# the one before it.
_WINDOW_START_DATE = "2026-05-01"

_WINDOW_END_DATE = "2026-05-08"

_LAST_COVERED_DATE = "2026-05-07"

_AGENT_RUNS = 1183

# A database with nothing in it has no run, which reads as none rather than as
# a spend of zero.
_NO_SPEND = '<span class="value">—</span><span class="note">no agent runs</span>'

# The theme the page draws through, with each formatter marking what it was
# handed, so a case can say which readings reached the markup shortened.
_THEME = SimpleNamespace(
    fmt_num=lambda number: f"<{number}>",
)

_FORMATTED_RUNS = f"<{_AGENT_RUNS}>"

_NO_EVENTS = "<0> events"

_NO_REPOS = "0 repos"

_NO_EXTENT = "no data recorded yet"

_SYNC_ENTRYPOINT = "analytics.sync.cli"

# What the stand-in records, so one list carries the order a render drew in.
_MARKUP = "markup"

_NOTICE = "notice"

_STOP = "stop"

# What the page's own timer read when the load that found nothing started, and
# the waves it had and had not spent by then.
_LOAD_START = 12.5

_FIRST_WAVE = (("summary", object()), ("prev_summary", object()))

_SECOND_WAVE = (("repo_rows", object()),)

_LOG_LOAD_ATTRIBUTE = "log_dashboard_load"

_DRILLDOWN_ATTRIBUTE = "render_drilldown_view"


class _PageStopped(Exception):
    """What `st.stop()` raises: the script ends where the notice was drawn."""


class _PageStreamlit:
    """The markup, notices, and stop these renders reach Streamlit for."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.markup: list[tuple[str, dict]] = []
        self.notices: list[str] = []

    def markdown(self, body: str, **options) -> None:
        self.events.append(_MARKUP)
        self.markup.append((body, options))

    def stop(self) -> None:
        self.events.append(_STOP)
        raise _PageStopped

    def show_notice(self, text: str) -> None:
        """Record an `st.info(...)`, which the lookup below routes here."""
        self.events.append(_NOTICE)
        self.notices.append(text)

    def __getattr__(self, attribute_name: str):
        if attribute_name == "info":
            return self.show_notice
        raise AttributeError(attribute_name)


def _modules(st: Any) -> page_models.DashboardModules:
    return page_models.DashboardModules(
        st=st, pd=None, theme=_THEME,
    )


def _page(*, parallel: bool = True) -> page_models.DashboardPage:
    """A page whose plan carries the clock and waves a load is timed by."""
    return page_models.DashboardPage(
        extent=DataExtent(min_ts=_WINDOW_START, max_ts=_WINDOW_END),
        controls=page_models.DashboardControls(
            filters=page_models.DashboardFilters(
                window=windows.DateWindow(
                    start=_WINDOW_START, end=_WINDOW_END,
                ),
                repo=None,
                issue_input=None,
                events=None,
                stages=None,
            ),
            topbar_slot=None,
            meta_slot=None,
            timezone_offset=0,
        ),
        reads=SimpleNamespace(
            started_at=_LOAD_START,
            first_wave=list(_FIRST_WAVE),
            second_wave=list(_SECOND_WAVE),
            parallel=parallel,
        ),
    )


class RenderNoDataTest(unittest.TestCase):
    """The startup state a database with nothing in it is answered with."""

    def test_the_banner_reports_the_empty_database(self) -> None:
        # There is no window to narrow anything to yet, so the banner stands in
        # for the whole chrome with every count it carries zeroed and its spend
        # the empty cohort.
        body, options = self._render().markup[0]

        self.assertEqual(options, {"unsafe_allow_html": True})
        self.assertIn(_NO_EXTENT, body)
        self.assertIn(_NO_REPOS, body)
        self.assertIn(_NO_EVENTS, body)
        self.assertIn(_NO_SPEND, body)

    def test_the_notice_names_the_sync_that_fills_it(self) -> None:
        # A page with nothing on it reads as a broken one, so the notice says
        # which command turns an empty database into a drawable window.
        st = self._render()

        self.assertEqual(st.notices, [page_states.NO_DATA_MESSAGE])
        self.assertIn(_SYNC_ENTRYPOINT, page_states.NO_DATA_MESSAGE)

    def test_the_script_ends_on_that_notice(self) -> None:
        # Everything below needs an extent to pick a window from, so the page
        # stops here rather than falling through to a filter bar with no dates
        # to offer -- but not before the operator has been told why.
        self.assertEqual(self._render().events, [_MARKUP, _NOTICE, _STOP])

    def _render(self) -> _PageStreamlit:
        st = _PageStreamlit()
        # Reaching the stop is this render finishing, so every case above runs
        # through it rather than around it.
        with self.assertRaises(_PageStopped):
            page_states.render_no_data(
                st=st, extent=DataExtent(), theme=_THEME,
            )
        return st


class RenderEmptyWindowTest(unittest.TestCase):
    """The notice a filtered window matching no row leaves through."""

    def test_the_notice_offers_the_way_out(self) -> None:
        st, _, _, _ = self._render()

        self.assertEqual(st.notices, [page_states.EMPTY_WINDOW_MESSAGE])

    def test_only_the_first_wave_is_logged(self) -> None:
        # A short-circuited load never reaches the line `run_read_waves` ends
        # on, so the notice that ended it measures the load instead -- off the
        # plan's own clock, the reads it had already spent, and the way they
        # were issued. Counting both waves here would report reads nobody paid
        # for on every empty window.
        for parallel in (True, False):
            with self.subTest(parallel=parallel):
                _, _, logged, _ = self._render(parallel=parallel)

                logged.assert_called_once_with(
                    load_start=_LOAD_START,
                    reads=len(_FIRST_WAVE),
                    parallel=parallel,
                )

    def test_the_trace_beneath_is_still_drawn(self) -> None:
        # An operator narrowing to one issue is exactly who lands on an empty
        # window, and that trace is scoped by the issue on top of the window
        # rather than by the cache key the skipped reads share, so it can still
        # have something to show.
        st, page, _, traced = self._render()

        traced.assert_called_once()
        modules, filters = traced.call_args.args
        self.assertIs(modules.st, st)
        self.assertIs(filters, page.controls.filters)

    def _render(self, *, parallel: bool = True) -> tuple:
        st = _PageStreamlit()
        page = _page(parallel=parallel)
        with (
            patch.object(dispatch, _LOG_LOAD_ATTRIBUTE) as logged,
            patch.object(drilldown, _DRILLDOWN_ATTRIBUTE) as traced,
        ):
            page_states.render_empty_window(_modules(st), page)
            return st, page, logged, traced


class RenderDashboardFooterTest(unittest.TestCase):
    """The line the page closes on, and what it restates."""

    def test_the_span_closes_on_the_last_covered_day(self) -> None:
        # The reads above are issued under `ts < end`, so restating `end`
        # itself would name a day none of the numbers covered.
        footer = self._footer()

        self.assertIn(_WINDOW_START_DATE, footer)
        self.assertIn(_LAST_COVERED_DATE, footer)
        self.assertNotIn(_WINDOW_END_DATE, footer)

    def test_the_run_count_goes_through_the_theme(self) -> None:
        # The footer sits under tiles the same formatter shortened, so a raw
        # integer here would be one count spelled two ways on one page.
        self.assertIn(f"{_FORMATTED_RUNS} agent runs", self._footer())

    def _footer(self) -> str:
        st = _PageStreamlit()
        page_states.render_dashboard_footer(
            _modules(st),
            _page().controls.filters,
            Summary(total_agent_runs=_AGENT_RUNS),
        )
        body, options = st.markup[0]
        self.assertEqual(options, {"unsafe_allow_html": True})
        return body


if __name__ == "__main__":
    unittest.main()
