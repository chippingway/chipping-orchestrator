# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How one page load's two waves are driven, and what a failed one costs.

Streamlit lives in the optional `dashboard` dependency group, so the cases
below hand the load a stand-in that records the spinner it was opened under,
the banner it was asked to show, and the stop that ends the script -- which is
the whole of what this owner reaches Streamlit for. Its readers record
themselves into the same list, so a case can say which reads ran, in which
order, and on which side of the render between the waves, rather than only what
came back.
"""

from __future__ import annotations

import re
import unittest
from functools import partial
from typing import Any, Self
from unittest.mock import patch

from orchestrator.observability.analytics.query.connections import (
    AnalyticsReadError,
)
from orchestrator.observability.dashboard import dispatch, fanout, read_plan

# What the stand-in records around the reads, so one list carries the whole
# order a load ran in.
_SPINNER_OPEN = "spinner-open"

_SPINNER_CLOSE = "spinner-close"

_RENDER = "render"

# One read per wave, named as the page names them, so a case can say which side
# of that render a wave was dispatched on.
_FIRST_READ = "summary"

_SECOND_READ = "repo_rows"

_READ_FAILED = "connection refused"

# What the first-wave render hands back when the window has rows, and what it
# hands back when it drew the empty-window banner instead.
_CHROME = object()

_NOTHING_DRAWN = None

# What the page's own timer read when the load started. The line is logged
# against the span elapsed since, so only the read count and the flag beside it
# are read back out of it.
_STARTED_AT = 12.5

_LOAD_LINE = re.compile(
    r"^dashboard\.load: total=\d+\.\ds reads=(\d+) parallel=(true|false)$",
)

# Both waves of the plan the cases below are run against, counted the way the
# load line reports them.
_PLANNED_READS = "2"

# The logger an operator's `grep dashboard.load` is already filtered by.
_LOAD_LOGGER = "orchestrator._dashboard_read_dispatch"


class _PageStopped(Exception):
    """What `st.stop()` raises: the script ends where the banner was drawn."""


class _FakeStreamlit:
    """The spinner, banner, and stop this owner reaches Streamlit for.

    The spinner is the stand-in itself, so a load that opened a second one
    over the same wait is recorded as a second entry rather than hidden behind
    a fresh context object per call.
    """

    def __init__(self) -> None:
        self.events: list[str] = []
        self.spinners: list[str] = []
        self.errors: list[str] = []

    def spinner(self, message: str) -> _FakeStreamlit:
        self.spinners.append(message)
        return self

    def error(self, message: str) -> None:
        self.errors.append(message)

    def stop(self) -> None:
        raise _PageStopped(self.errors[-1])

    def __enter__(self) -> Self:
        self.events.append(_SPINNER_OPEN)
        return self

    def __exit__(self, *exception: object) -> bool:
        self.events.append(_SPINNER_CLOSE)
        return False


def _record_read(name: str, events: list[str], error: str = "") -> str:
    """Record that a wave reached this reader, then answer it or fail it."""
    events.append(name)
    if error:
        raise AnalyticsReadError(error)
    return name


def _record_render(events: list[str], drawn: Any, read_results: Any) -> Any:
    events.append(_RENDER)
    return drawn


class _LoadSupport(unittest.TestCase):
    """One page load driven against a recording stand-in."""

    def setUp(self) -> None:
        self.st = _FakeStreamlit()

    def _plan(
        self,
        *,
        parallel: bool = False,
        first_error: str = "",
    ) -> read_plan.DashboardReadPlan:
        first_read = partial(
            _record_read, _FIRST_READ, self.st.events, first_error,
        )
        second_read = partial(_record_read, _SECOND_READ, self.st.events)
        return read_plan.DashboardReadPlan(
            first_wave=[(_FIRST_READ, first_read)],
            second_wave=[(_SECOND_READ, second_read)],
            parallel=parallel,
            started_at=_STARTED_AT,
        )

    def _run(
        self,
        plan: read_plan.DashboardReadPlan,
        drawn: Any = _CHROME,
    ) -> tuple | None:
        return dispatch.run_read_waves(
            plan,
            st=self.st,
            render_first_wave=partial(_record_render, self.st.events, drawn),
        )


class ReadWaveDispatchTest(_LoadSupport):
    """What a load issues, in what order, and what one spinner covers."""

    def test_the_chrome_renders_between_waves(self) -> None:
        # The whole point of staging a load: the topbar and the KPI strip are
        # drawn off the first wave while the panels beneath them are still
        # being read, and one indicator covers the wait rather than one a wave.
        loaded = self._run(self._plan())

        self.assertEqual(self.st.events, [
            _SPINNER_OPEN, _FIRST_READ, _RENDER, _SECOND_READ, _SPINNER_CLOSE,
        ])
        self.assertEqual(self.st.spinners, [dispatch.LOADING_INDICATOR_MESSAGE])
        self.assertEqual(
            loaded,
            ({_FIRST_READ: _FIRST_READ, _SECOND_READ: _SECOND_READ}, _CHROME),
        )

    def test_an_empty_window_skips_wave_two(self) -> None:
        # A window with no rows has nothing for the ten panels to draw, so the
        # render reporting nothing back ends the load where it stands rather
        # than paying for reads whose results are never looked at.
        self.assertIsNone(self._run(self._plan(), drawn=_NOTHING_DRAWN))

        self.assertEqual(self.st.events, [
            _SPINNER_OPEN, _FIRST_READ, _RENDER, _SPINNER_CLOSE,
        ])

    def test_a_failed_read_stops_the_page(self) -> None:
        # A page whose window, tiles, and every panel each raised their own
        # trace would say the same thing seventeen times, so the first failing
        # reader becomes one banner naming what to check, and then the stop.
        with self.assertRaises(_PageStopped):
            self._run(self._plan(first_error=_READ_FAILED))

        self.assertEqual(self.st.events, [
            _SPINNER_OPEN, _FIRST_READ, _SPINNER_CLOSE,
        ])
        self.assertEqual(len(self.st.errors), 1)
        self.assertIn(_READ_FAILED, self.st.errors[0])

    def test_both_waves_are_issued_the_plans_way(self) -> None:
        # Which way a load's reads run is the plan's answer, handed to the
        # fan-out unchanged: a wave deciding for itself is how one load ends
        # up issued both ways at once.
        with patch.object(fanout, "fan_out_reads", return_value={}) as fan_out:
            self._run(self._plan(parallel=True))
            issued = [call.kwargs for call in fan_out.call_args_list]

        self.assertEqual(issued, [{"parallel": True}, {"parallel": True}])


class DashboardLoadLogTest(_LoadSupport):
    """The one line the two fan-out branches are compared from."""

    def test_a_completed_load_logs_its_totals(self) -> None:
        # The fan-out is an operator's switch rather than a setting, so the
        # wall clock, the reads behind it, and which way they were issued are
        # what make `grep dashboard.load` an A/B of the two branches. The count
        # comes off the plan, so a read added to either wave is reported here
        # without a second number to keep in step.
        with self.assertLogs(dispatch.log, level="INFO") as logged:
            self._run(self._plan(parallel=True))
            lines = [record.getMessage() for record in logged.records]

        self.assertEqual(len(lines), 1)
        line = _LOAD_LINE.match(lines[0])
        self.assertIsNotNone(line)
        self.assertEqual(line.groups(), (_PLANNED_READS, "true"))

    def test_the_line_keeps_its_logger_name(self) -> None:
        # A logger named after whichever module happens to hold the emit would
        # move the line every time that module does, and silently out of the
        # level and handler selection an operator already pointed at it.
        self.assertEqual(dispatch.log.name, _LOAD_LOGGER)

    def test_an_empty_window_logs_nothing_here(self) -> None:
        # The caller that drew the empty-window banner logs that load itself,
        # because what it spent is the first wave rather than both.
        with self.assertNoLogs(dispatch.log, level="INFO"):
            self._run(self._plan(), drawn=_NOTHING_DRAWN)


if __name__ == "__main__":
    unittest.main()
