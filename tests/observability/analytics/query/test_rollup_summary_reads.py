# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one window totalled, and what the window before it is compared to."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.rollup_reads import (
    get_kpi_prev,
    get_summary,
)
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

_KIND_TOTALS = "t"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_WIN_CTE = "WITH win AS"

_TOTAL_RUNS_FIELD = "total_agent_runs"

_FAILED_RUNS_FIELD = "failed_agent_runs"

_YEAR = 2026

_WINDOW_END_DAY = 28

_PREVIOUS_START = datetime(_YEAR, 4, 1, tzinfo=UTC)

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, _WINDOW_END_DAY, tzinfo=UTC)

# The totals branch at its full width, in the order the cast list maps it:
# kind / label / events / issues / repos / cost / input / output / runs /
# failed / cache_read / cache_write / timed_out.
_TOTALS_ROW = (
    _KIND_TOTALS, None, 200, 24, 3, 4.5, 12_000, 8_000, 35, 6, 3_000, 1_500, 11,
)

# Every total the row above has to round-trip into, named field by field so a
# column-order regression is pinned to the exact KPI it would zero out.
_EXPECTED_TOTALS = MappingProxyType({
    "total_events": 200,
    "distinct_issues": 24,
    "distinct_repos": 3,
    "total_cost_usd": 4.5,
    "total_input_tokens": 12_000,
    "total_output_tokens": 8_000,
    _TOTAL_RUNS_FIELD: 35,
    _FAILED_RUNS_FIELD: 6,
    "total_cache_read_tokens": 3_000,
    "total_cache_write_tokens": 1_500,
    "timed_out_agent_runs": 11,
})

# A totals row missing the agent-run and cache columns its SELECT branch names.
_NARROW_TOTALS_ROW = (_KIND_TOTALS, None, 4, 2, 2, 0, 0, 0)

# The trimmed previous-window row: cost / input / output / cache_read /
# cache_write / runs, and the fields each has to land in.
_PREVIOUS_ROW = (2.5, 1000, 500, 200, 100, 7)

_EXPECTED_PREVIOUS = MappingProxyType({
    "total_cost_usd": 2.5,
    "total_input_tokens": 1000,
    "total_output_tokens": 500,
    "total_cache_read_tokens": 200,
    "total_cache_write_tokens": 100,
    _TOTAL_RUNS_FIELD: 7,
})

# What a trimmed read never touches, so a consumer sharing the `Summary` shape
# sees a default rather than a value carried over from the other window.
_UNREAD_PREVIOUS_FIELDS = MappingProxyType({
    "total_events": 0,
    "distinct_issues": 0,
    "distinct_repos": 0,
    _FAILED_RUNS_FIELD: 0,
    "timed_out_agent_runs": 0,
    "by_event": {},
    "by_stage": {},
})


class SummaryReadTest(unittest.TestCase):
    """The one round-trip a page frames a whole window with."""

    def test_an_unconfigured_database_totals_nothing(self) -> None:
        with configured_db_url(None):
            summary = get_summary(connect=FakeConnect())
        self.assertEqual(summary, Summary())

    def test_a_window_with_no_rows_totals_nothing(self) -> None:
        with configured_db_url():
            summary = get_summary(connect=FakeConnection().as_connect)
        self.assertEqual(summary, Summary())

    def test_one_round_trip_answers_all_three(self) -> None:
        # The three branches arrive interleaved and out of rank order, so the
        # ranking the assertions read back is the in-Python sort rather than
        # whichever plan PostgreSQL picked for the union.
        conn = FakeConnection(rows=(
            _TOTALS_ROW,
            ("e", _AGENT_EXIT, 12, None, None, None, None, None, None, None, None, None, None),
            ("e", _STAGE_ENTER, 30, None, None, None, None, None, None, None, None, None, None),
            ("s", _STAGE_VALIDATING, 10, None, None, None, None, None, None, None, None, None, None),
            ("s", _STAGE_IMPLEMENTING, 20, None, None, None, None, None, None, None, None, None, None),
        ))
        with configured_db_url():
            summary = get_summary(connect=conn.as_connect)
        assert_row_fields(self, summary, _EXPECTED_TOTALS)
        self.assertEqual(
            list(summary.by_event.items()),
            [(_STAGE_ENTER, 30), (_AGENT_EXIT, 12)],
        )
        self.assertEqual(
            list(summary.by_stage.items()),
            [(_STAGE_IMPLEMENTING, 20), (_STAGE_VALIDATING, 10)],
        )
        self.assertEqual(len(conn.executed), 1)

    def test_the_scan_names_each_total_column(self) -> None:
        # Each KPI is a plain SUM of one pre-derived rollup column, so a column
        # rename under the rollup surfaces here instead of silently zeroing a
        # tile. The distinct-issue count is over `(repo, issue)` pairs because
        # issue numbers repeat across repositories, and the agent-run counters
        # narrow to exit rows so a non-exit bucket cannot inflate them.
        conn = FakeConnection(rows=(_TOTALS_ROW,))
        with configured_db_url():
            get_summary(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _WIN_CTE,
                _ROLLUP_SCAN,
                "COUNT(DISTINCT (repo, issue))",
                "event = 'agent_exit'",
                _TOTAL_RUNS_FIELD,
                _FAILED_RUNS_FIELD,
                "SUM(timed_out_count)",
                "SUM(total_input_tokens)",
                "SUM(total_output_tokens)",
                "SUM(total_cache_read_tokens)",
                "SUM(total_cache_write_tokens)",
            ),
        )

    def test_a_narrower_totals_row_raises(self) -> None:
        # Each total is read at the position its SELECT branch puts it, so a
        # row missing some is a broken query rather than totals left at zero.
        conn = FakeConnection(rows=(_NARROW_TOTALS_ROW,))
        with configured_db_url(), self.assertRaises(ValueError):
            get_summary(connect=conn.as_connect)

    def test_the_window_binds_as_days_once(self) -> None:
        # The predicate lives in the CTE, so the totals and both breakdown
        # branches inherit one filter instead of repeating it three times.
        conn = FakeConnection()
        with configured_db_url():
            get_summary(
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                connect=conn.as_connect,
            )
        self.assertEqual(len(conn.executed), 1)
        scan_sql, bindings = conn.executed[0]
        assert_sql_fragments(self, scan_sql, ("day >= %s", "day < %s", "repo = %s"))
        self.assertEqual(
            bindings[:3],
            (_WINDOW_START.date(), _WINDOW_END.date(), _REPO),
        )


class KpiPreviousReadTest(unittest.TestCase):
    """The trimmed scan a delta pill measures the current window against."""

    def test_an_unconfigured_database_compares_none(self) -> None:
        with configured_db_url(None):
            summary = get_kpi_prev(connect=FakeConnect())
        self.assertEqual(summary, Summary())

    def test_an_empty_window_compares_against_nothing(self) -> None:
        with configured_db_url():
            summary = get_kpi_prev(connect=FakeConnection().as_connect)
        self.assertEqual(summary, Summary())

    def test_scalars_round_trip_and_rest_default(self) -> None:
        conn = FakeConnection(rows=(_PREVIOUS_ROW,))
        with configured_db_url():
            summary = get_kpi_prev(connect=conn.as_connect)
        assert_row_fields(self, summary, _EXPECTED_PREVIOUS)
        assert_row_fields(self, summary, _UNREAD_PREVIOUS_FIELDS)

    def test_the_scan_skips_the_breakdowns(self) -> None:
        # The trimmed shape is the point: carrying the groupings or the
        # distinct counts would cost the comparison window the same three
        # scans the window it is compared against pays.
        conn = FakeConnection()
        with configured_db_url():
            get_kpi_prev(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        self.assertIn(_ROLLUP_SCAN, scan_sql)
        self.assertNotIn("GROUP BY", scan_sql)
        self.assertNotIn("COUNT(DISTINCT", scan_sql)

    def test_the_window_and_filters_bind_as_days(self) -> None:
        conn = FakeConnection()
        with configured_db_url():
            get_kpi_prev(
                start=_PREVIOUS_START,
                end=_WINDOW_START,
                repo=_REPO,
                events=[_AGENT_EXIT],
                stages=[_STAGE_IMPLEMENTING],
                connect=conn.as_connect,
            )
        self.assertEqual(len(conn.executed), 1)
        scan_sql, bindings = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            ("day >= %s", "day < %s", "repo = %s", "event IN (%s)", "stage IN (%s)"),
        )
        self.assertEqual(
            bindings[:3],
            (_PREVIOUS_START.date(), _WINDOW_START.date(), _REPO),
        )


if __name__ == "__main__":
    unittest.main()
