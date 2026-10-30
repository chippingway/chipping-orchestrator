# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One row per issue in a window, ranked by what it cost or by when it moved.

An issue's cost is the cohort its runs fold to, read back with each basis apart and its runs counted by the
completeness each states, and the cost order ranks on every amount those runs state. So the rows a fake driver hands
back here are the cells the read's fragments compute over each case's runs, and the ranking is held to the `ORDER BY`
SQL applies ahead of its `LIMIT`. What that ordering does with real rows -- an older costly issue kept past the cap,
equal amounts broken by the newest activity and then by the pair -- is the live Postgres test's to show.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.cost_cohorts import EVENT_COST_COHORT_SQL, EVENT_STATED_USD_SQL
from orchestrator.observability.analytics.query.issue_summaries import SORT_BY_COST
from orchestrator.observability.analytics.query.raw_reads import (
    get_issue_events,
    get_issues,
)
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.analytics_assertions import assert_row_fields, assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url
from tests.observability.analytics.query.run_rows_test_support import IssueAggregate

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

_KNOWN_TOKENS = 800

_UNKNOWN_TOKEN_RUNS = 1

_EVENT_COUNT = 3

_MAX_REVIEW_ROUND = 3

_FAILED_AGENT_RUNS = 2

_MAX_RETRY_COUNT = 4

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

# An issue that only ever entered a stage: no stage, no run, and no review
# round or retry recorded, so those aggregates are NULL.
_UNRUN_ISSUE = IssueAggregate(_REPO, _ISSUE, _EVENT_TS, _EVENT_TS)

# The amount column of every basis, which the ranking measure has to add up
# for a blended issue to rank at its whole stated total.
_AMOUNT_COLUMNS = (
    "cost_cli_reported_usd",
    "cost_anthropic_estimate_usd",
    "cost_openai_estimate_usd",
    "cost_gemini_estimate_usd",
    "cost_unknown_basis_usd",
)

# Issues whose runs state each kind of cost the ranking has to keep apart: a
# CLI-reported amount, one provider's estimates only (Antigravity's, priced
# on the Gemini basis), several bases blended, a subtotal beside unpriced
# usage, no amount at all, an amount an earlier build stored with no basis,
# a complete zero, and runs that printed no usage.
_ISSUE_COSTS = (
    ("reported", (cases.REPORTED,)),
    ("antigravity only", (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE)),
    ("mixed", (cases.REPORTED, cases.OPENAI_ESTIMATE, cases.BLENDED)),
    ("incomplete", (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED)),
    ("unpriced", (cases.UNPRICED,)),
    ("missing basis", (cases.ABSENT_BASIS,)),
    ("complete zero", (cases.COMPLETE_ZERO,)),
    ("no usage", (cases.NO_USAGE,)),
)

# What each ordering mode has to produce, and the ordering it must not fall
# back on. Ranking by cost happens in SQL because ordering after the `LIMIT`
# would drop the older expensive issues that mode exists to surface.
_SORT_MODES = (
    ({}, ("ORDER BY last_seen DESC, repo ASC, issue ASC LIMIT %s",), "stated_cost_usd DESC"),
    (
        {"sort_by": SORT_BY_COST},
        ("ORDER BY stated_cost_usd DESC NULLS LAST, last_seen DESC, repo ASC, issue ASC LIMIT %s",),
        "ORDER BY last_seen DESC",
    ),
)


def _read_issues(*aggregates: IssueAggregate) -> list:
    with configured_db_url():
        return get_issues(
            connect=FakeConnection(rows=tuple(aggregate.cells() for aggregate in aggregates)).as_connect,
        )


def _rounded(evidence: usage_cost.CostEvidence) -> tuple:
    """The evidence with each amount rounded past the float noise a SQL sum and a Python sum differ by."""
    parts = tuple(
        (part.basis, round(part.amount_usd, 9), part.rates_verified_on) for part in evidence.contributions
    )
    return evidence.completeness, parts


class IssuesOverviewTest(unittest.TestCase):
    """The issues table: one aggregate row per `(repo, issue)` pair."""

    def test_an_unconfigured_database_returns_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_issues(connect=FakeConnect()), [])

    def test_a_non_positive_cap_never_dials(self) -> None:
        with configured_db_url():
            self.assertEqual(get_issues(limit=0, connect=FakeConnect()), [])

    def test_a_pair_is_one_row_with_its_own_cohort(self) -> None:
        # The same bare issue number under two repos is two rows, and the
        # order the SQL returned them in survives the projection. An issue
        # with no run reads as an empty cohort and no stated amount, never as
        # a measured zero.
        conn = FakeConnection(rows=(
            IssueAggregate(
                _REPO_B, 1, _LATER_SEEN, _LATEST_SEEN, (cases.REPORTED,),
                event_count=_EVENT_COUNT,
                latest_stage=_STAGE_VALIDATING,
                total_tokens=_KNOWN_TOKENS,
                unknown_token_runs=_UNKNOWN_TOKEN_RUNS,
            ).cells(),
            IssueAggregate(_REPO_A, 1, _EVENT_TS, _NOON_TS, event_count=5).cells(),
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
                "agent_exits": 1,
                "stated_cost_usd": cases.REPORTED_USD,
                "total_tokens": _KNOWN_TOKENS,
                "unknown_token_runs": _UNKNOWN_TOKEN_RUNS,
            },
        )
        self.assertEqual(issues[0].cost.evidence, cases.REPORTED)
        self.assertTrue(issues[1].cost.is_empty)
        self.assertIsNone(issues[1].stated_cost_usd)
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

    def test_null_aggregates_read_as_unset(self) -> None:
        # A maximum over no recorded value stays `None` rather than reading as
        # a measured round zero.
        rows = _read_issues(_UNRUN_ISSUE)
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
            IssueAggregate(
                _REPO, _ISSUE, _EVENT_TS, _EVENT_TS, (cases.REPORTED,),
                max_review_round=_MAX_REVIEW_ROUND,
                failed_agent_runs=_FAILED_AGENT_RUNS,
                max_retry_count=_MAX_RETRY_COUNT,
            ).cells(),
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


class IssueCostReadTest(unittest.TestCase):
    """An issue's cost is the cohort its runs fold to, beside the amount it is ranked on."""

    def test_each_cost_reads_as_its_runs_fold(self) -> None:
        # The ranking's amount is every amount the runs state, whatever basis
        # or completeness, so it is the folded total -- a subtotal's known
        # part included -- and nothing where no run states an amount.
        for name, costs in _ISSUE_COSTS:
            with self.subTest(issue=name):
                row = _read_issues(IssueAggregate(_REPO, _ISSUE, _EVENT_TS, _EVENT_TS, costs))[0]
                folded = usage_cost.reduce_costs(costs)
                self.assertEqual(row.cost.runs, len(costs))
                self.assertEqual(_rounded(row.cost.evidence), _rounded(folded))
                if folded.total_usd is None:
                    self.assertIsNone(row.stated_cost_usd)
                else:
                    self.assertAlmostEqual(row.stated_cost_usd, folded.total_usd)

    def test_a_row_of_another_width_raises(self) -> None:
        # The cohort cells close the SELECT list, so a row short of them is a
        # broken query, never an issue whose cost reads as NULL.
        narrow = FakeConnection(rows=(_UNRUN_ISSUE.cells()[:-1],))
        with configured_db_url(), self.assertRaises(TypeError):
            get_issues(connect=narrow.as_connect)


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

    def test_cost_order_ranks_on_every_stated_amount(self) -> None:
        # The measure is summed per issue in the same scan as its cohort, and
        # adds every basis's amount -- an amount stored with no evidence read
        # under the `unknown` basis, as the cohort reads it.
        conn = FakeConnection()
        with configured_db_url():
            get_issues(connect=conn.as_connect, sort_by=SORT_BY_COST)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (f"SUM({EVENT_STATED_USD_SQL}) AS stated_cost_usd", EVENT_COST_COHORT_SQL),
        )
        assert_sql_fragments(
            self,
            EVENT_STATED_USD_SQL,
            (*_AMOUNT_COLUMNS, "WHEN cost_completeness IS NULL THEN cost_usd"),
        )

    def test_an_unknown_ordering_mode_is_refused(self) -> None:
        # A typo never degrades to the default ordering, and the refusal comes
        # before the connection so the caller cannot half-run the read.
        with configured_db_url(), self.assertRaises(ValueError):
            get_issues(sort_by="not-a-mode", connect=FakeConnect())


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
