# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one issue's trace shows, and the three things it says instead.

Streamlit and pandas are faked so a render runs end-to-end in the default
install: the heading, the notices, the banner, and what is handed to
`st.dataframe` are what an operator sees, and the fake frame is the row list it
was built from, so the columns and their order can be read straight off it. The
scope entry is faked the same way, which is what lets a case say whose read was
issued inside it and under which filters without standing a database up. A
run's cost reads as the recent-runs listing words it, and an event that is no
run leaves both cost cells empty rather than reading as a zero.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from orchestrator.observability.analytics.query import raw_reads
from orchestrator.observability.analytics.query.connections import (
    AnalyticsReadError,
)
from orchestrator.observability.analytics.query.run_models import IssueEventRow
from orchestrator.observability.dashboard import (
    drilldown,
    page_models,
    scoped_reads,
    windows,
)
from tests.observability.analytics import analytics_usage_cases as cases

_REPO = "owner/repo"

_ISSUE = 1181

_READ_FAILED = "connection refused"

_SCOPED_READ_ATTRIBUTE = "scoped_read"

_YEAR = 2026

_MAY = 5

_NOON = 12

_WINDOW_START = datetime(_YEAR, _MAY, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, _MAY, 8, tzinfo=UTC)

_EVENT_AT = datetime(_YEAR, _MAY, 4, _NOON, tzinfo=UTC)

_EVENTS = ("stage_entered", "agent_exit")

_STAGES = ("implementing",)

_EVENT_COLUMN = "event"

_COST_COLUMN = "cost"

_RATES_COLUMN = "rates"

_FIRST_EVENT = "stage_entered"

_SECOND_EVENT = "agent_exit"

# The columns one traced event is read in: when it happened and what it was,
# then where in the state machine, then how long it took and how it went, then
# who ran it and what it cost.
_COLUMNS = (
    "ts",
    _EVENT_COLUMN,
    "stage",
    "duration (s)",
    "result",
    "agent",
    "backend",
    "exit",
    _COST_COLUMN,
    _RATES_COLUMN,
)


class _DrilldownStreamlit:
    """Fake `st` recording the heading, notices, banners, and frames."""

    def __init__(self) -> None:
        self.subheaders: list[str] = []
        self.notices: list[str] = []
        self.errors: list[str] = []
        self.frames: list = []

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def dataframe(self, frame, **options) -> None:
        self.frames.append((frame, options))

    def show_notice(self, text: str) -> None:
        """Record an `st.info(...)`, which the lookup below routes here."""
        self.notices.append(text)

    def __getattr__(self, attribute_name: str):
        if attribute_name == "info":
            return self.show_notice
        raise AttributeError(attribute_name)


class _RecordingScope:
    """Stand-in for the scope entry, recording what was issued inside it."""

    def __init__(
        self,
        trace: Sequence[IssueEventRow] = (),
        *,
        failure: Exception | None = None,
    ) -> None:
        self.trace = list(trace)
        self.failure = failure
        self.calls: list[tuple] = []

    def __call__(
        self,
        getter: Callable[..., Any],
        /,
        **read_filters: Any,
    ) -> list[IssueEventRow]:
        self.calls.append((getter, read_filters))
        if self.failure is not None:
            raise self.failure
        return self.trace


def _issue_event(**overrides: Any) -> IssueEventRow:
    readings = {
        "ts": _EVENT_AT,
        _EVENT_COLUMN: _FIRST_EVENT,
        "stage": "implementing",
        "duration_s": 12.5,
        "event_result": "ok",
        "agent_role": "developer",
        "backend": "claude",
        "exit_code": 0,
        "cost": cases.ANTHROPIC_ESTIMATE,
    }
    readings.update(overrides)
    return IssueEventRow(**readings)


def _render(
    scope: _RecordingScope,
    *,
    repo: str | None = _REPO,
    issue_input: int | None = _ISSUE,
    events: Sequence[str] | None = _EVENTS,
    stages: Sequence[str] | None = _STAGES,
) -> _DrilldownStreamlit:
    """Draw the section over one run's selections, on a faked page."""
    st = _DrilldownStreamlit()
    modules = page_models.DashboardModules(
        st=st,
        # A frame here is the row list it was built from, so a case reads the
        # projected columns off what the page was handed.
        pd=SimpleNamespace(DataFrame=list),
        theme=None,
    )
    filters = page_models.DashboardFilters(
        window=windows.DateWindow(start=_WINDOW_START, end=_WINDOW_END),
        repo=repo,
        issue_input=issue_input,
        events=events,
        stages=stages,
    )
    with patch.object(scoped_reads, _SCOPED_READ_ATTRIBUTE, scope):
        drilldown.render_drilldown_view(modules, filters)
    return st


class IssueTraceReadTest(unittest.TestCase):
    """The one page read issued outside the cached wrappers, still scoped."""

    def test_the_read_carries_the_window_and_issue(self) -> None:
        # A cache key is hashed per window and filter set, so the issue this
        # trace is narrowed to has to travel with the read rather than in that
        # key -- and it still enters the shared scope, sharing the socket the
        # waves above it opened. The selections reach the read as lists while a
        # cleared one stays `None`, which is the difference between no clause
        # and a selection that must match nothing.
        for events, stages in ((_EVENTS, _STAGES), (None, None)):
            with self.subTest(events=events):
                scope = _RecordingScope()

                _render(scope, events=events, stages=stages)

                self.assertEqual(
                    scope.calls,
                    [(
                        raw_reads.get_issue_events,
                        {
                            "repo": _REPO,
                            "issue": _ISSUE,
                            "start": _WINDOW_START,
                            "end": _WINDOW_END,
                            "events": events and list(events),
                            "stages": stages and list(stages),
                        },
                    )],
                )


class DrilldownEventRowTest(unittest.TestCase):
    """One traced event is projected into the columns it is read in."""

    def test_columns_are_in_reading_order(self) -> None:
        row = drilldown.drilldown_event_row(_issue_event())
        self.assertEqual(tuple(row), _COLUMNS)

    def test_every_reading_comes_off_the_event(self) -> None:
        # The result column is the one read through the row model's historical
        # public name rather than off the field the model stores it in.
        event = _issue_event()
        row = drilldown.drilldown_event_row(event)
        self.assertEqual(
            tuple(row.values()),
            (
                event.ts,
                event.event,
                event.stage,
                event.duration_s,
                event.event_result,
                event.agent_role,
                event.backend,
                event.exit_code,
                "$0.30 (Anthropic API token estimate)",
                "rates verified 2026-10-29",
            ),
        )

    def test_a_non_run_event_states_no_cost(self) -> None:
        row = drilldown.drilldown_event_row(_issue_event(cost=None))
        self.assertEqual((row[_COST_COLUMN], row[_RATES_COLUMN]), (None, None))

    def test_a_basis_less_amount_says_so(self) -> None:
        # A run an earlier build recorded with no cost evidence keeps its
        # amount, and its row says nothing is known of its basis.
        row = drilldown.drilldown_event_row(_issue_event(cost=cases.ABSENT_BASIS))
        self.assertEqual(row[_COST_COLUMN], "$0.07 (basis unknown, completeness unknown)")


class RenderDrilldownViewTest(unittest.TestCase):
    """What the section draws, and what it says when it cannot draw it."""

    def test_no_issue_selected_draws_nothing(self) -> None:
        # The section is the only part of the page an operator opts into, so a
        # run that named no issue must not even head it -- nor spend a read.
        scope = _RecordingScope()

        st = _render(scope, issue_input=None)

        self.assertEqual(scope.calls, [])
        self.assertEqual(st.subheaders, [])
        self.assertEqual(st.notices, [])

    def test_a_number_with_no_repo_names_the_control(self) -> None:
        # GitHub issue numbers repeat across repositories, so the trace would
        # interleave unrelated runs. The heading is still written, so the
        # notice says which issue it is about.
        scope = _RecordingScope([_issue_event()])

        st = _render(scope, repo=None)

        self.assertEqual(scope.calls, [])
        self.assertEqual(st.notices, [drilldown.MISSING_REPO_MESSAGE])
        self.assertEqual(st.frames, [])
        self.assertIn(str(_ISSUE), st.subheaders[0])

    def test_a_traced_issue_renders_the_frame(self) -> None:
        scope = _RecordingScope([
            _issue_event(), _issue_event(event=_SECOND_EVENT),
        ])

        st = _render(scope)

        self.assertEqual(st.notices, [])
        frame, options = st.frames[0]
        self.assertEqual(options, {"use_container_width": True})
        self.assertEqual(tuple(frame[0]), _COLUMNS)
        self.assertEqual(
            [row[_EVENT_COLUMN] for row in frame],
            [_FIRST_EVENT, _SECOND_EVENT],
        )

    def test_an_untraced_issue_names_its_scope(self) -> None:
        # An empty frame would read as a broken panel, so the notice names the
        # scope the filters left: this repository, this issue, this window.
        st = _render(_RecordingScope())

        self.assertEqual(st.frames, [])
        self.assertIn(f"{_REPO}#{_ISSUE}", st.notices[0])

    def test_a_failed_read_banners_the_driver_message(self) -> None:
        # Every panel above this one already rendered, so a trace that cannot
        # reach the database reports itself rather than stopping the page.
        st = _render(
            _RecordingScope(failure=AnalyticsReadError(_READ_FAILED)),
        )

        self.assertEqual(st.frames, [])
        self.assertEqual(st.notices, [])
        self.assertIn(_READ_FAILED, st.errors[0])


if __name__ == "__main__":
    unittest.main()
