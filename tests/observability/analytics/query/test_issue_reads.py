# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One row per issue in a window, and one issue's trace inside it."""
from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query.issue_summaries import SORT_BY_COST
from orchestrator.observability.analytics.query.query_rows import IssueEventQueryRow
from orchestrator.observability.analytics.query.raw_reads import (
    get_issue_events,
    get_issues,
)
from orchestrator.observability.analytics.query.run_models import IssueEventRow
from tests.observability.analytics.analytics_assertions import assert_row_fields, assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url

_AGENT_EXIT = "agent_exit"

_STAGE_ENTER = "stage_enter"

_STAGE_IMPLEMENTING = "implementing"

_STAGE_VALIDATING = "validating"

_REPO = "owner/r"

_REPO_A = "owner/a"

_REPO_B = "owner/b"

_ISSUE = 7

_GROUP_BY_PAIR = "GROUP BY repo, issue"

_BASE_SCAN = "FROM analytics_events"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

# The cap the issue table defaults to, and the one a caller overrides it with.
_DEFAULT_LIMIT = 100

_CHOSEN_LIMIT = 25

_TOTAL_COST_USD = 0.42

_TOTAL_INPUT_TOKENS = 500

_TOTAL_OUTPUT_TOKENS = 300

_EVENT_COUNT = 3

_AGENT_EXITS = 1

_MAX_REVIEW_ROUND = 3

_FAILED_AGENT_RUNS = 2

_MAX_RETRY_COUNT = 4

_TRACE_DURATION_S = 42.0

_TRACE_COST_USD = 0.05

_YEAR = 2026

_EVENT_TS_DAY = 25

_NOON_HOUR = 12

_LATER_SEEN_DAY = 26

_LATEST_SEEN_MINUTE = 30

_WINDOW_END_DAY = 28

_EVENT_TS = datetime(_YEAR, 5, _EVENT_TS_DAY, 10, 0, tzinfo=UTC)

_NOON_TS = datetime(_YEAR, 5, _EVENT_TS_DAY, _NOON_HOUR, 0, tzinfo=UTC)

_LATER_SEEN = datetime(_YEAR, 5, _LATER_SEEN_DAY, 9, 0, tzinfo=UTC)

_LATEST_SEEN = datetime(
    _YEAR, 5, _LATER_SEEN_DAY, 9, _LATEST_SEEN_MINUTE, tzinfo=UTC,
)

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, _WINDOW_END_DAY, tzinfo=UTC)

# A row from before the review-round and retry columns existed: everything the
# SELECT list gained since reads back as unset rather than as a measured zero.
_SHORT_ROW = (_REPO, _ISSUE, 1, _EVENT_TS, _EVENT_TS, None, 0, None, 0, 0)

# One issue's trace as a row from before it read any correlation: the nine
# columns the drill-down tabulates and nothing after them.
_LEGACY_TRACE_ROW = (
    _NOON_TS, _STAGE_ENTER, _STAGE_IMPLEMENTING, None, None, None, None, None, None,
)

# The run columns a full-width trace row carries between those nine and its
# blob, all NULL.
_NULL_RUN_COLUMNS = (None,) * (
    len(IssueEventQueryRow._fields) - len(_LEGACY_TRACE_ROW) - 1
)

# What a trace row with nothing to correlate reads back as.
_UNCORRELATED = MappingProxyType({
    "agent_spec": None,
    "session_id": None,
    "resume_session_id": None,
    "review_round": None,
    "retry_count": None,
    "timed_out": None,
    "extras": {},
})

# What each ordering mode has to produce, and the ordering it must not fall
# back on. Ranking by cost happens in SQL because ordering after the `LIMIT`
# would drop the older expensive issues that mode exists to surface.
_SORT_MODES = (
    ({}, ("ORDER BY last_seen DESC",), "SUM(cost_usd) DESC"),
    (
        {"sort_by": SORT_BY_COST},
        ("ORDER BY SUM(cost_usd) DESC NULLS LAST", "last_seen DESC"),
        "ORDER BY last_seen DESC",
    ),
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


class IssuesOverviewTest(unittest.TestCase):
    """The issues table: one aggregate row per `(repo, issue)` pair."""

    def test_an_unconfigured_database_returns_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_issues(connect=FakeConnect()), [])

    def test_a_non_positive_cap_never_dials(self) -> None:
        with configured_db_url():
            self.assertEqual(get_issues(limit=0, connect=FakeConnect()), [])

    def test_a_pair_is_one_row_with_a_null_cost(self) -> None:
        # The same bare issue number under two repos is two rows, and the
        # order the SQL returned them in survives the projection. A `NULL`
        # cost stays `None` rather than reading as a measured zero.
        conn = FakeConnection(rows=(
            (
                _REPO_B, 1, _EVENT_COUNT, _LATER_SEEN, _LATEST_SEEN,
                _STAGE_VALIDATING, _AGENT_EXITS, _TOTAL_COST_USD,
                _TOTAL_INPUT_TOKENS, _TOTAL_OUTPUT_TOKENS,
            ),
            (
                _REPO_A, 1, 5, _EVENT_TS, _NOON_TS,
                _STAGE_IMPLEMENTING, 2, None, 0, 0,
            ),
        ))
        with configured_db_url():
            issues = get_issues(connect=conn.as_connect)
        self.assertEqual(
            [(row.repo, row.issue) for row in issues],
            [(_REPO_B, 1), (_REPO_A, 1)],
        )
        assert_row_fields(
            self,
            issues[0],
            {
                "event_count": _EVENT_COUNT,
                "first_seen": _LATER_SEEN,
                "last_seen": _LATEST_SEEN,
                "latest_stage": _STAGE_VALIDATING,
                "agent_exits": _AGENT_EXITS,
                "total_cost_usd": _TOTAL_COST_USD,
                "total_input_tokens": _TOTAL_INPUT_TOKENS,
                "total_output_tokens": _TOTAL_OUTPUT_TOKENS,
            },
        )
        self.assertIsNone(issues[1].total_cost_usd)
        scan_sql, bindings = conn.executed[0]
        self.assertIn(_GROUP_BY_PAIR, scan_sql)
        self.assertIn("LIMIT %s", scan_sql)
        self.assertEqual(bindings[-1], _DEFAULT_LIMIT)

    def test_the_window_binds_before_the_cap(self) -> None:
        conn = FakeConnection()
        with configured_db_url():
            get_issues(
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                limit=_CHOSEN_LIMIT,
                connect=conn.as_connect,
            )
        scan_sql, bindings = conn.executed[0]
        assert_sql_fragments(self, scan_sql, ("ts >= %s", "ts < %s", "repo = %s"))
        self.assertEqual(
            bindings,
            (_WINDOW_START, _WINDOW_END, _REPO, _CHOSEN_LIMIT),
        )

    def test_a_short_rows_gaps_read_as_unset(self) -> None:
        conn = FakeConnection(rows=(_SHORT_ROW,))
        with configured_db_url():
            rows = get_issues(connect=conn.as_connect)
        assert_row_fields(
            self,
            rows[0],
            {
                "latest_stage": None,
                "max_review_round": None,
                "failed_agent_runs": 0,
                "max_retry_count": None,
            },
        )

    def test_review_round_columns_round_trip(self) -> None:
        conn = FakeConnection(rows=(
            (
                _REPO, _ISSUE, 8, _EVENT_TS, _EVENT_TS, _STAGE_IMPLEMENTING,
                5, 0.55, 800, 400,
                _MAX_REVIEW_ROUND, _FAILED_AGENT_RUNS, _MAX_RETRY_COUNT,
            ),
        ))
        with configured_db_url():
            rows = get_issues(connect=conn.as_connect)
        assert_row_fields(
            self,
            rows[0],
            {
                "max_review_round": _MAX_REVIEW_ROUND,
                "failed_agent_runs": _FAILED_AGENT_RUNS,
                "max_retry_count": _MAX_RETRY_COUNT,
            },
        )
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            ("MAX(review_round)", "MAX(retry_count)", "failed_agent_runs"),
        )


class IssuesOrderingTest(unittest.TestCase):
    """Which of the two rankings the issues table is read in."""

    def test_each_ordering_mode_ranks_in_sql(self) -> None:
        for mode, expected_fragments, rejected_fragment in _SORT_MODES:
            with self.subTest(mode=mode):
                conn = FakeConnection()
                with configured_db_url():
                    get_issues(connect=conn.as_connect, **mode)
                scan_sql, _ = conn.executed[0]
                assert_sql_fragments(self, scan_sql, expected_fragments)
                self.assertNotIn(rejected_fragment, scan_sql)

    def test_an_unknown_ordering_mode_is_refused(self) -> None:
        # A typo never degrades to the default ordering, and the refusal comes
        # before the connection so the caller cannot half-run the read.
        with configured_db_url(), self.assertRaises(ValueError):
            get_issues(sort_by="not-a-mode", connect=FakeConnect())


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
            (_NOON_TS, _STAGE_ENTER, _STAGE_IMPLEMENTING, None, None, None, None, None, None),
            (
                _LATEST_SEEN, _AGENT_EXIT, _STAGE_IMPLEMENTING, _TRACE_DURATION_S,
                None, "dev", "claude", 0, _TRACE_COST_USD,
            ),
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
                "cost_usd": _TRACE_COST_USD,
            },
        )
        # The pinned pair is bound, not interpolated, and binds ahead of the
        # generated window predicate.
        scan_sql, bindings = conn.executed[0]
        self.assertIn("ORDER BY ts ASC, id ASC", scan_sql)
        self.assertEqual(bindings, (_REPO, _ISSUE))
        assert_sql_fragments(
            self,
            scan_sql,
            ("session_id", "review_round", "retry_count", "timed_out", "extras"),
        )

    def test_a_legacy_row_reads_with_no_correlation(self) -> None:
        # A row from before the trace read correlation, and a full-width one
        # whose run columns and blob are NULL, both read back as carrying
        # none rather than as measured values.
        full_width = (*_LEGACY_TRACE_ROW, *_NULL_RUN_COLUMNS, None)
        for row in (_LEGACY_TRACE_ROW, full_width):
            with self.subTest(width=len(row)):
                event = _read_one_event(row)
                self.assertEqual(event.event, _STAGE_ENTER)
                assert_row_fields(self, event, _UNCORRELATED)

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
                event = _read_one_event(
                    (*_LEGACY_TRACE_ROW, *_NULL_RUN_COLUMNS, blob),
                )
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


class EventsTableScanTest(unittest.TestCase):
    """Both reads stay on the events table rather than the rollup.

    The aggregate carries MIN/MAX `ts`, `latest_stage`, and the review-round
    and retry maxima, and the trace addresses individual rows; the day bucket
    threw all of that away, so a read moved onto it would be asking for
    columns it does not carry.
    """

    def test_neither_read_migrates_to_the_rollup(self) -> None:
        reads = (
            ("issues", lambda connect: get_issues(connect=connect)),
            (
                "issue_events",
                lambda connect: get_issue_events(
                    repo=_REPO, issue=_ISSUE, connect=connect,
                ),
            ),
        )
        for name, read in reads:
            with self.subTest(read=name):
                conn = FakeConnection()
                with configured_db_url():
                    read(conn.as_connect)
                scan_sql, _ = conn.executed[0]
                self.assertIn(_BASE_SCAN, scan_sql)
                self.assertNotIn(_ROLLUP_SCAN, scan_sql)


if __name__ == "__main__":
    unittest.main()
