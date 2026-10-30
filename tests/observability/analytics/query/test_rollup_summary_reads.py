# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one window totalled, and what the window before it is compared to.

Both reads carry spend as the rollup's cost cohort and tokens as the runs'
known non-overlapping totals beside the runs whose total is unknown, so the
cases below hand each a row carrying the cells a real cohort fragment selects
-- reported-only, AGY-only, mixed-provider, incomplete, missing-basis, empty,
and zero-valued -- and read back the cohort, never one summed amount.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query import cost_cohorts, token_totals
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.rollup_reads import (
    get_kpi_prev,
    get_summary,
)
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
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

_KNOWN_TOKENS = 18_500

_UNKNOWN_TOKEN_RUNS = 2

# The cohorts a window's spend has to keep apart, each the costs its runs state.
_COHORTS = MappingProxyType({
    "reported only": (cases.REPORTED, cases.REPORTED),
    "agy only": (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE),
    "mixed providers": (cases.REPORTED, cases.GEMINI_ESTIMATE, cases.BLENDED),
    "incomplete": (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED),
    "missing basis": (cases.REPORTED, cases.ABSENT_BASIS),
    "empty": (),
    "zero": (cases.COMPLETE_ZERO,),
})

_MIXED_COSTS = _COHORTS["mixed providers"]

# The counts of the totals branch, in the order the SELECT lists them:
# events / issues / repos / runs / failed / timed out.
_COUNTS = (200, 24, 3, 35, 6, 11)

_EXPECTED_COUNTS = MappingProxyType({
    "total_events": 200,
    "distinct_issues": 24,
    "distinct_repos": 3,
    _TOTAL_RUNS_FIELD: 35,
    _FAILED_RUNS_FIELD: 6,
    "timed_out_agent_runs": 11,
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

# The spellings a reduction over the evidence replaces: one summed amount, and
# the raw counters a Codex run's cached input sits in twice.
_RAW_SUMS = (
    "SUM(total_cost_usd)",
    "SUM(total_input_tokens)",
    "SUM(total_cache_read_tokens)",
)

_PREVIOUS_RUNS = 7


_TOKENS = (_KNOWN_TOKENS, _UNKNOWN_TOKEN_RUNS)

# Each breakdown branch's rows ahead of padding, out of rank order: kind, label, count.
_BREAKDOWNS = (
    ("e", _AGENT_EXIT, 12),
    ("e", _STAGE_ENTER, 30),
    ("s", _STAGE_VALIDATING, 10),
    ("s", _STAGE_IMPLEMENTING, 20),
)


def _totals_row(costs: tuple = _MIXED_COSTS) -> tuple:
    """The totals branch at its full width: kind, label, counts, cohort, tokens."""
    return (_KIND_TOTALS, None, *_COUNTS) + cohort_cases.cohort_cells(costs) + _TOKENS


def _padded(breakdown: tuple) -> tuple:
    """One breakdown branch's row, its every other cell padded with a NULL."""
    return breakdown + (None,) * (len(_totals_row()) - len(breakdown))


def _previous_row(costs: tuple = _MIXED_COSTS) -> tuple:
    """The trimmed previous-window row: runs, cohort, tokens."""
    return (_PREVIOUS_RUNS,) + cohort_cases.cohort_cells(costs) + _TOKENS


def _summary_of(costs: tuple) -> Summary:
    """The summary a window whose runs state `costs` reads back as."""
    conn = FakeConnection(rows=(_totals_row(costs),))
    with configured_db_url():
        return get_summary(connect=conn.as_connect)


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
        conn = FakeConnection(rows=(_totals_row(), *map(_padded, _BREAKDOWNS)))
        with configured_db_url():
            summary = get_summary(connect=conn.as_connect)
        assert_row_fields(self, summary, _EXPECTED_COUNTS)
        self.assertEqual((summary.total_tokens, summary.unknown_token_runs), (_KNOWN_TOKENS, _UNKNOWN_TOKEN_RUNS))
        self.assertEqual(summary.cost, cohort_cases.cohort(*_MIXED_COSTS))
        self.assertEqual(
            list(summary.by_event.items()),
            [(_STAGE_ENTER, 30), (_AGENT_EXIT, 12)],
        )
        self.assertEqual(
            list(summary.by_stage.items()),
            [(_STAGE_IMPLEMENTING, 20), (_STAGE_VALIDATING, 10)],
        )
        self.assertEqual(len(conn.executed), 1)

    def test_spend_reads_back_as_its_cohort(self) -> None:
        # Each cohort is read back as the one its runs reduce to, so a window
        # with no run, a complete zero, an incomplete subtotal, and an amount
        # with no stated basis stay four answers rather than one summed number.
        for name, costs in _COHORTS.items():
            conn = FakeConnection(rows=(_totals_row(costs),))
            with self.subTest(cohort=name), configured_db_url():
                summary = get_summary(connect=conn.as_connect)
                self.assertEqual(summary.cost, cohort_cases.cohort(*costs))
        self.assertEqual(_summary_of(()).cost, cost_cohorts.EMPTY_COST_COHORT)
        zero = _summary_of(_COHORTS["zero"]).cost
        self.assertEqual((zero.is_empty, zero.evidence.complete_usd), (False, 0))

    def test_the_scan_reduces_the_evidence(self) -> None:
        # Each count is a plain SUM of one pre-derived rollup column, so a column
        # rename under the rollup surfaces here instead of silently zeroing a
        # tile. The distinct-issue count is over `(repo, issue)` pairs because
        # issue numbers repeat across repositories, and the agent-run counters
        # narrow to exit rows so a non-exit bucket cannot inflate them. Spend
        # and tokens are the shared rollup reductions, never a raw sum.
        conn = FakeConnection(rows=(_totals_row(),))
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
                cost_cohorts.ROLLUP_COST_COHORT_SQL,
                token_totals.ROLLUP_TOKEN_TOTAL_SQL,
            ),
        )
        for raw_sum in _RAW_SUMS:
            with self.subTest(raw_sum=raw_sum):
                self.assertNotIn(raw_sum, scan_sql)
        # Each breakdown branch pads every cell the totals branch selects past
        # its count, so the union is one width.
        padding = ", ".join(("NULL",) * (5 + cost_cohorts.COST_COHORT_WIDTH + 2))
        self.assertEqual(scan_sql.count(padding), 2)

    def test_a_narrower_totals_row_raises(self) -> None:
        # Each total is read at the position its SELECT branch puts it, so a
        # row missing some is a broken query rather than totals left at zero.
        conn = FakeConnection(rows=(_totals_row()[:-1],))
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
        # The window a delta is measured against carries its own cohort and
        # unknown token runs, so a comparison can only say what both sides state.
        for name, costs in _COHORTS.items():
            conn = FakeConnection(rows=(_previous_row(costs),))
            with self.subTest(cohort=name), configured_db_url():
                summary = get_kpi_prev(connect=conn.as_connect)
                self.assertEqual(summary.cost, cohort_cases.cohort(*costs))
                self.assertEqual(
                    (summary.total_agent_runs, summary.total_tokens, summary.unknown_token_runs),
                    (_PREVIOUS_RUNS, _KNOWN_TOKENS, _UNKNOWN_TOKEN_RUNS),
                )
                assert_row_fields(self, summary, _UNREAD_PREVIOUS_FIELDS)

    def test_the_scan_skips_the_breakdowns(self) -> None:
        # The trimmed shape is the point: carrying the groupings or the
        # distinct counts would cost the comparison window the same three
        # scans the window it is compared against pays. Its spend and tokens
        # are the same reductions the current window's are.
        conn = FakeConnection()
        with configured_db_url():
            get_kpi_prev(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (_ROLLUP_SCAN, cost_cohorts.ROLLUP_COST_COHORT_SQL, token_totals.ROLLUP_TOKEN_TOTAL_SQL),
        )
        self.assertNotIn("GROUP BY", scan_sql)
        self.assertNotIn("COUNT(DISTINCT", scan_sql)
        for raw_sum in _RAW_SUMS:
            with self.subTest(raw_sum=raw_sum):
                self.assertNotIn(raw_sum, scan_sql)

    def test_a_narrower_row_raises(self) -> None:
        conn = FakeConnection(rows=(_previous_row()[:-1],))
        with configured_db_url(), self.assertRaises(ValueError):
            get_kpi_prev(connect=conn.as_connect)

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
