# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's trace inside a window, oldest first, each run carrying the cost its row stored.

A run's cost is read off the evidence the sync filed on its row, so a CLI-reported amount, an estimate with the dates
its rates were verified on, a blended run, an unpriced one, and an amount an earlier build stored with no basis each
read back as that run's own evidence -- never repriced -- while an event that is no run carries no cost at all.
"""
from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query.raw_reads import get_issue_events
from orchestrator.observability.analytics.query.run_models import IssueEventRow
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.analytics_assertions import assert_row_fields, assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url
from tests.observability.analytics.query.run_rows_test_support import trace_row

_AGENT_EXIT = "agent_exit"

_STAGE_ENTER = "stage_enter"

_STAGE_IMPLEMENTING = "implementing"

_REPO = "owner/r"

_ISSUE = 7

_TRACE_DURATION_S = 42.0

_YEAR = 2026

_EVENT_TS_DAY = 25

_NOON_HOUR = 12

_WINDOW_END_DAY = 28

_NOON_TS = datetime(_YEAR, 5, _EVENT_TS_DAY, _NOON_HOUR, 0, tzinfo=UTC)

_LATEST_SEEN = datetime.fromisoformat("2026-05-26T09:30:00+00:00")

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, _WINDOW_END_DAY, tzinfo=UTC)

# The columns the drill-down tabulates, as a `stage_enter` fills them.
_STAGE_ENTER_COLUMNS = (
    _NOON_TS, _STAGE_ENTER, _STAGE_IMPLEMENTING, None, None, None, None, None,
)

# The same columns as an `agent_exit` fills them.
_AGENT_EXIT_COLUMNS = (
    _LATEST_SEEN, _AGENT_EXIT, _STAGE_IMPLEMENTING, _TRACE_DURATION_S, None, "dev", "claude", 0,
)

_STAGE_ENTER_ROW = trace_row(_STAGE_ENTER_COLUMNS)

# What a trace row with nothing to correlate reads back as.
_UNCORRELATED = MappingProxyType({
    "agent_spec": None,
    "session_id": None,
    "resume_session_id": None,
    "review_round": None,
    "retry_count": None,
    "timed_out": None,
    "extras": {},
    "cost": None,
})

# The costs a run's row can store, each read back as that run's own evidence.
_RUN_COSTS = (
    ("reported", cases.REPORTED),
    ("dated estimate", cases.GEMINI_ESTIMATE),
    ("blended", cases.BLENDED),
    ("subtotal", cases.INCOMPLETE_SUBTOTAL),
    ("unpriced", cases.UNPRICED),
    ("missing basis", cases.ABSENT_BASIS),
    ("complete zero", cases.COMPLETE_ZERO),
)


def _read_one_event(row: tuple) -> IssueEventRow:
    """Read `row` back as the only event of one issue's trace."""
    with configured_db_url():
        trace = get_issue_events(
            repo=_REPO,
            issue=_ISSUE,
            connect=FakeConnection(rows=(row,)).as_connect,
        )
    return trace[0]


class IssueEventsTest(unittest.TestCase):
    """The per-issue drill-down: every selected event, oldest first."""

    def test_an_unconfigured_database_returns_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(
                get_issue_events(repo=_REPO, issue=1, connect=FakeConnect()),
                [],
            )

    def test_a_trace_binds_its_pair_first(self) -> None:
        conn = FakeConnection(rows=(
            _STAGE_ENTER_ROW,
            trace_row(_AGENT_EXIT_COLUMNS, cost=cases.REPORTED),
        ))
        with configured_db_url():
            rows = get_issue_events(repo=_REPO, issue=_ISSUE, connect=conn.as_connect)
        self.assertEqual([row.event for row in rows], [_STAGE_ENTER, _AGENT_EXIT])
        assert_row_fields(
            self,
            rows[1],
            {
                "stage": _STAGE_IMPLEMENTING,
                "duration_s": _TRACE_DURATION_S,
                "backend": "claude",
                "cost": cases.REPORTED,
            },
        )
        # The pinned pair is bound, not interpolated, and binds ahead of the
        # generated window predicate. A run's cost is its own row's cells,
        # never a sum across the trace.
        scan_sql, bindings = conn.executed[0]
        self.assertIn("ORDER BY ts ASC, id ASC", scan_sql)
        self.assertEqual(bindings, (_REPO, _ISSUE))
        assert_sql_fragments(
            self,
            scan_sql,
            ("session_id", "review_round", "retry_count", "timed_out", "extras", "gemini_rates_verified_on"),
        )
        self.assertNotIn("SUM(", scan_sql)

    def test_a_row_narrower_than_the_trace_raises(self) -> None:
        # The trace row is the SELECT list, so a row missing its correlation
        # columns is a broken query, never an event that correlates nothing.
        with self.assertRaises(TypeError):
            _read_one_event(_STAGE_ENTER_ROW[1:])

    def test_a_blob_reads_back_as_a_mapping(self) -> None:
        # A driver hands a JSONB object back adapted or as its text, and both
        # read the same; a damaged or non-object blob reads as empty rather
        # than taking the rest of the trace down with it.
        correlation = {"reason": "agent_question"}
        for blob, expected in (
            (correlation, correlation),
            (json.dumps(correlation), correlation),
            ("{not json", {}),
            ("[1, 2]", {}),
        ):
            with self.subTest(blob=blob):
                event = _read_one_event(trace_row(_STAGE_ENTER_COLUMNS, extras=blob))
                self.assertEqual(event.extras, expected)

    def test_the_window_filters_thread_through(self) -> None:
        # The drill-down narrows with the dashboard above it, so a trace stays
        # consistent with what the widgets around it show.
        conn = FakeConnection()
        with configured_db_url():
            get_issue_events(
                repo=_REPO,
                issue=_ISSUE,
                start=_WINDOW_START,
                end=_WINDOW_END,
                events=[_AGENT_EXIT],
                connect=conn.as_connect,
            )
        scan_sql, bindings = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            ("ts >= %s", "ts < %s", "event IN (%s)"),
        )
        self.assertEqual(
            bindings,
            (_REPO, _ISSUE, _WINDOW_START, _WINDOW_END, _AGENT_EXIT),
        )

    def test_a_cleared_selection_never_dials(self) -> None:
        # A cleared multiselect matches no row, so the trace is answered
        # without reaching the database.
        for selection in ({"events": []}, {"stages": []}):
            with self.subTest(selection=selection), configured_db_url():
                self.assertEqual(
                    get_issue_events(
                        repo=_REPO,
                        issue=_ISSUE,
                        connect=FakeConnect(),
                        **selection,
                    ),
                    [],
                )


class TracedRunCostTest(unittest.TestCase):
    """A traced run carries the cost its row stored; any other event carries none."""

    def test_a_run_reads_back_its_stored_cost(self) -> None:
        # A CLI-reported amount stays the one its record ranked first, and an
        # estimate keeps the dates its rates were verified on.
        for name, spent in _RUN_COSTS:
            with self.subTest(cost=name):
                event = _read_one_event(trace_row(_AGENT_EXIT_COLUMNS, cost=spent))
                self.assertEqual(event.cost, spent)

    def test_an_uncorrelated_event_reads_with_none(self) -> None:
        # A `stage_enter` fills none of the run columns, carries no blob, and
        # states no usage, so it reads back as correlating nothing and costing
        # nothing it could state, rather than as measured values or a zero.
        event = _read_one_event(_STAGE_ENTER_ROW)
        self.assertEqual(event.event, _STAGE_ENTER)
        assert_row_fields(self, event, _UNCORRELATED)


if __name__ == "__main__":
    unittest.main()
