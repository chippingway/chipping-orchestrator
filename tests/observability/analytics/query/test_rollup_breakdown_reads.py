# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three axes one window's activity and spend are broken down along.

Each read carries a group's spend as the rollup's cost cohort, so the cases hand
each a row carrying the cells a real cohort fragment selects -- reported-only,
AGY-only, mixed-provider, incomplete, and missing-basis -- and read back the
cohort, never one summed amount. The stage read also carries the token-share
bands its stated amount is split into, and the backend read the declared token
totals and the cache and output inside them that its ratios divide by; neither
reads a raw counter, which would count a Codex run's cached input twice.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.observability.analytics.query import cache_shares, cost_cohorts, token_totals
from orchestrator.observability.analytics.query.rollup_reads import (
    get_backend_efficiency,
    get_repo_breakdown,
    get_stage_breakdown,
)
from tests.observability.analytics import analytics_cohorts as cohort_cases
from tests.observability.analytics.analytics_assertions import assert_row_fields, assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url

_STAGE_ENTER = "stage_enter"

_STAGE_IMPLEMENTING = "implementing"

_STAGE_VALIDATING = "validating"

_CLAUDE = "claude"

_AGY = "agy"

_UNKNOWN = "unknown"

_REPO_A = "owner/a"

_REPO_B = "owner/b"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_AGENT_EXIT_CONDITION = "event = 'agent_exit'"

_RUNS_FIELD = "runs"

_COST_FIELD = "cost"

_REPORTED = "reported only"

_AGY_ONLY = "agy only"

_MISSING_BASIS = "missing basis"

_MIXED = "mixed providers"

_INCOMPLETE = "incomplete"

_REPORTED_COSTS = cohort_cases.NAMED_COSTS[_REPORTED]

_AGY_COSTS = cohort_cases.NAMED_COSTS[_AGY_ONLY]

_MISSING_BASIS_COSTS = cohort_cases.NAMED_COSTS[_MISSING_BASIS]

_MIXED_COSTS = cohort_cases.NAMED_COSTS[_MIXED]

_INCOMPLETE_COSTS = cohort_cases.NAMED_COSTS[_INCOMPLETE]

# The two fragments the row-weighted mean is recovered by, and the naive
# average it must never regress to: averaging per-day averages would weight a
# quiet day the same as a busy one.
_WEIGHTED_DURATION = ("SUM(duration_s_sum)", "NULLIF(SUM(duration_s_count), 0)")

_NAIVE_DURATION = "AVG(duration_s)"

# The spellings a reduction over the evidence replaces: one summed amount that
# merges every basis and reads an unpriced group as zero, and the raw counters
# a Codex run's cached input sits in twice.
_RAW_SUMS = (
    "SUM(total_cost_usd)",
    "total_input_tokens",
    "total_cached_tokens",
    "total_cache_read_tokens",
    "total_cache_write_tokens",
)

# A stage's lead cells: stage / events / mean duration / agent runs.
_STAGE_HEAD = (_STAGE_IMPLEMENTING, 20, 12.5, 8)

# Its known token total and the runs whose total is unknown, then the three
# token-share bands: the cache share, the rest, and the amount nothing split.
_STAGE_TOKENS = (18_000, 1)

_STAGE_BANDS = (0.3, 0.2, 0.12)

_EXPECTED_STAGE = MappingProxyType({
    "stage": _STAGE_IMPLEMENTING,
    "count": 20,
    "avg_duration_s": 12.5,
    _RUNS_FIELD: 8,
    "total_tokens": 18_000,
    "unknown_token_runs": 1,
    "bands": cache_shares.TokenShareBands(*_STAGE_BANDS),
})

# A backend's lead cells: backend / runs / failed / mean duration.
_BACKEND_HEAD = (_CLAUDE, 20, 1, 35)

# Its known token total, the runs whose total is unknown, and the cache and
# output counters inside the known totals.
_BACKEND_TOKENS = (9_000, 2, 3_000, 1_200)

_EXPECTED_BACKEND = MappingProxyType({
    _RUNS_FIELD: 20,
    "failed": 1,
    "avg_duration_s": 35,
    "total_tokens": 9_000,
    "unknown_token_runs": 2,
    "cache_tokens": 3_000,
    "output_tokens": 1_200,
    "input_side_tokens": 7_800,
})


def _cells(name: str) -> tuple:
    return cohort_cases.cohort_cells(cohort_cases.NAMED_COSTS[name])


def _stage_row(name: str, head: tuple = _STAGE_HEAD) -> tuple:
    return head + _cells(name) + _STAGE_TOKENS + _STAGE_BANDS


def _backend_row(name: str, head: tuple = _BACKEND_HEAD) -> tuple:
    return head + _cells(name) + _BACKEND_TOKENS


def _scan(read, row: tuple) -> str:
    """The SQL one read issued for a window answered by `row`."""
    conn = FakeConnection(rows=(row,))
    with configured_db_url():
        read(connect=conn.as_connect)
    scan_sql, _ = conn.executed[0]
    return scan_sql


class StageBreakdownReadTest(unittest.TestCase):
    """What each workflow stage counted, cost, and split by token share."""

    def test_an_unconfigured_database_breaks_none(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_stage_breakdown(connect=FakeConnect()), [])

    def test_each_cohort_keeps_its_evidence(self) -> None:
        # A stage's spend is read back as the cohort its runs fold to, so an
        # AGY-only stage's Gemini estimate, a blended stage's parts, a
        # subtotal beside an unpriced run, and an amount with no basis each
        # stay what they are rather than one summed number.
        for name, costs in cohort_cases.NAMED_COSTS.items():
            conn = FakeConnection(rows=(_stage_row(name),))
            with self.subTest(cohort=name), configured_db_url():
                rows = get_stage_breakdown(connect=conn.as_connect)
                self.assertEqual(rows[0].cost, cohort_cases.cohort(*costs))
                assert_row_fields(self, rows[0], _EXPECTED_STAGE)

    def test_a_missing_duration_stays_unset(self) -> None:
        # A stage no row carried a duration for reads back as unset, so a panel
        # can hide the column rather than show a zero it would read as instant.
        conn = FakeConnection(rows=(_stage_row(_AGY_ONLY, (_STAGE_VALIDATING, 10, None, 3)),))
        with configured_db_url():
            rows = get_stage_breakdown(connect=conn.as_connect)
        self.assertIsNone(rows[0].avg_duration_s)

    def test_the_scan_reduces_and_splits_by_share(self) -> None:
        scan_sql = _scan(get_stage_breakdown, _stage_row(_REPORTED))
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _ROLLUP_SCAN,
                "stage IS NOT NULL",
                _AGENT_EXIT_CONDITION,
                cost_cohorts.ROLLUP_COST_COHORT_SQL,
                token_totals.ROLLUP_TOKEN_TOTAL_SQL,
                cache_shares.ROLLUP_TOKEN_SHARE_SQL,
                *_WEIGHTED_DURATION,
            ),
        )
        self.assertNotIn(_NAIVE_DURATION, scan_sql)
        for raw in _RAW_SUMS:
            self.assertNotIn(raw, scan_sql)

    def test_a_row_without_its_bands_raises(self) -> None:
        # A row narrower than its SELECT list is a broken query rather than a
        # stage whose spend nothing split.
        narrow = _stage_row(_REPORTED)[:-1]
        conn = FakeConnection(rows=(narrow,))
        with configured_db_url(), self.assertRaises(ValueError):
            get_stage_breakdown(connect=conn.as_connect)


class BackendEfficiencyReadTest(unittest.TestCase):
    """What each backend ran, failed, spent, and counted in declared tokens."""

    def test_an_unconfigured_database_compares_none(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_backend_efficiency(connect=FakeConnect()), [])

    def test_a_selection_without_exits_stops(self) -> None:
        # The pinned exit filter could never match, so the answer is settled
        # before a connection is opened.
        with configured_db_url():
            self.assertEqual(
                get_backend_efficiency(events=[_STAGE_ENTER], connect=FakeConnect()),
                [],
            )

    def test_each_backend_keeps_its_rank_and_evidence(self) -> None:
        conn = FakeConnection(rows=(
            _backend_row(_REPORTED),
            _backend_row(_AGY_ONLY, (_AGY, 10, 3, None)),
            _backend_row(_MISSING_BASIS, (_UNKNOWN, 1, 0, None)),
        ))
        with configured_db_url():
            rows = get_backend_efficiency(connect=conn.as_connect)
        self.assertEqual(
            [(row.backend, row.cost) for row in rows],
            [
                (_CLAUDE, cohort_cases.cohort(*_REPORTED_COSTS)),
                (_AGY, cohort_cases.cohort(*_AGY_COSTS)),
                (_UNKNOWN, cohort_cases.cohort(*_MISSING_BASIS_COSTS)),
            ],
        )
        assert_row_fields(self, rows[0], _EXPECTED_BACKEND)
        self.assertIsNone(rows[1].avg_duration_s)

    def test_the_scan_pins_exits_and_reads_totals(self) -> None:
        scan_sql = _scan(get_backend_efficiency, _backend_row(_REPORTED))
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _ROLLUP_SCAN,
                _AGENT_EXIT_CONDITION,
                "COALESCE(backend, 'unknown')",
                cost_cohorts.ROLLUP_COST_COHORT_SQL,
                token_totals.ROLLUP_TOKEN_TOTAL_SQL,
                "SUM(cache_tokens_in_total)",
                "SUM(output_tokens_in_total)",
                *_WEIGHTED_DURATION,
            ),
        )
        for raw in _RAW_SUMS:
            self.assertNotIn(raw, scan_sql)


class RepoBreakdownReadTest(unittest.TestCase):
    """What share of the window each repository accounts for."""

    def test_an_unconfigured_database_breaks_none(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_repo_breakdown(connect=FakeConnect()), [])

    def test_each_repo_carries_issues_and_cohort(self) -> None:
        # The bare distinct-issue count is safe only because the grouping is by
        # repository, which is what keeps two issues sharing a number apart.
        conn = FakeConnection(rows=(
            (_REPO_A, 5, 30, 4) + _cells(_MIXED),
            (_REPO_B, 2, 10, 1) + _cells(_INCOMPLETE),
        ))
        with configured_db_url():
            rows = get_repo_breakdown(connect=conn.as_connect)
        assert_row_fields(
            self,
            rows[0],
            {
                "repo": _REPO_A,
                "issues": 5,
                "events": 30,
                "agent_exits": 4,
                _COST_FIELD: cohort_cases.cohort(*_MIXED_COSTS),
            },
        )
        self.assertEqual(rows[1].cost, cohort_cases.cohort(*_INCOMPLETE_COSTS))

    def test_the_scan_reduces_each_repository(self) -> None:
        scan_sql = _scan(get_repo_breakdown, (_REPO_A, 1, 1, 1) + _cells(_REPORTED))
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _ROLLUP_SCAN,
                "COUNT(DISTINCT issue)",
                _AGENT_EXIT_CONDITION,
                cost_cohorts.ROLLUP_COST_COHORT_SQL,
            ),
        )
        self.assertNotIn("SUM(total_cost_usd)", scan_sql)


if __name__ == "__main__":
    unittest.main()
