# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three axes one window's activity and spend are broken down along."""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.observability.analytics.query.rollup_reads import (
    get_backend_efficiency,
    get_repo_breakdown,
    get_stage_breakdown,
)
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

_CODEX = "codex"

_UNKNOWN = "unknown"

_REPO_A = "owner/a"

_REPO_B = "owner/b"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_AGENT_EXIT_CONDITION = "event = 'agent_exit'"

_RUNS_FIELD = "runs"

# The two fragments the row-weighted mean is recovered by, and the naive
# average it must never regress to: averaging per-day averages would weight a
# quiet day the same as a busy one.
_WEIGHTED_DURATION = ("SUM(duration_s_sum)", "NULLIF(SUM(duration_s_count), 0)")

_NAIVE_DURATION = "AVG(duration_s)"

# One stage row at its full width: stage / events / avg_dur / cost / input /
# output / runs / cache_cost / no_cache_cost.
_STAGE_ROW = (_STAGE_IMPLEMENTING, 20, 12.5, 0.5, 2000, 1500, 8, 0.3, 0.2)

_EXPECTED_STAGE = MappingProxyType({
    "stage": _STAGE_IMPLEMENTING,
    "count": 20,
    "avg_duration_s": 12.5,
    "total_cost_usd": 0.5,
    "total_input_tokens": 2000,
    "total_output_tokens": 1500,
    _RUNS_FIELD: 8,
    "cache_cost_usd": 0.3,
    "no_cache_cost_usd": 0.2,
})

# One backend row at its full width: backend / runs / failed / avg_dur / cost /
# input / output / cache_read / cache_write.
_BACKEND_ROW = (_CLAUDE, 20, 1, 35, 1.2, 5000, 4000, 1500, 800)

_EXPECTED_BACKEND = MappingProxyType({
    _RUNS_FIELD: 20,
    "failed": 1,
    "avg_duration_s": 35,
    "total_cost_usd": 1.2,
    "total_input_tokens": 5000,
    "total_output_tokens": 4000,
    "total_cache_read_tokens": 1500,
    "total_cache_write_tokens": 800,
})


class StageBreakdownReadTest(unittest.TestCase):
    """What each workflow stage counted, cost, and served from cache."""

    def test_an_unconfigured_database_breaks_none(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_stage_breakdown(connect=FakeConnect()), [])

    def test_a_missing_duration_stays_unset(self) -> None:
        # A stage no row carried a duration for reads back as unset, so a panel
        # can hide the column rather than show a zero it would read as instant.
        conn = FakeConnection(rows=(
            _STAGE_ROW,
            (_STAGE_VALIDATING, 10, None, 0.1, 100, 200, 3, 0.04, 0.06),
        ))
        with configured_db_url():
            rows = get_stage_breakdown(connect=conn.as_connect)
        assert_row_fields(self, rows[0], _EXPECTED_STAGE)
        self.assertIsNone(rows[1].avg_duration_s)

    def test_the_scan_weights_and_splits(self) -> None:
        # The cache split is prorated per bucket by token share, with the Codex
        # `total_cached_tokens` subset in the numerator only, so the two bands
        # sum back to the stage's total cost.
        conn = FakeConnection(rows=(_STAGE_ROW,))
        with configured_db_url():
            get_stage_breakdown(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _ROLLUP_SCAN,
                "stage IS NOT NULL",
                _AGENT_EXIT_CONDITION,
                "SUM(total_cost_usd)",
                "total_cached_tokens",
                "total_cache_read_tokens",
                "total_cache_write_tokens",
                "stage_cache_cost_usd",
                "stage_no_cache_cost_usd",
                *_WEIGHTED_DURATION,
            ),
        )
        self.assertNotIn(_NAIVE_DURATION, scan_sql)


class BackendEfficiencyReadTest(unittest.TestCase):
    """What each backend ran, failed, and spent inside the window."""

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

    def test_each_backend_row_keeps_its_rank(self) -> None:
        conn = FakeConnection(rows=(
            _BACKEND_ROW,
            (_CODEX, 10, 3, None, 0.4, 1000, 2000, 0, 0),
            (_UNKNOWN, 1, 0, None, 0, 0, 0, 0, 0),
        ))
        with configured_db_url():
            rows = get_backend_efficiency(connect=conn.as_connect)
        self.assertEqual(
            [row.backend for row in rows],
            [_CLAUDE, _CODEX, _UNKNOWN],
        )
        assert_row_fields(self, rows[0], _EXPECTED_BACKEND)
        self.assertIsNone(rows[1].avg_duration_s)

    def test_the_scan_pins_exits_and_names_nulls(self) -> None:
        conn = FakeConnection(rows=(_BACKEND_ROW,))
        with configured_db_url():
            get_backend_efficiency(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _ROLLUP_SCAN,
                _AGENT_EXIT_CONDITION,
                "COALESCE(backend, 'unknown')",
                "SUM(total_cache_read_tokens)",
                "SUM(total_cache_write_tokens)",
                *_WEIGHTED_DURATION,
            ),
        )


class RepoBreakdownReadTest(unittest.TestCase):
    """What share of the window each repository accounts for."""

    def test_an_unconfigured_database_breaks_none(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_repo_breakdown(connect=FakeConnect()), [])

    def test_each_repo_carries_its_issue_count(self) -> None:
        # The bare distinct-issue count is safe only because the grouping is by
        # repository, which is what keeps two issues sharing a number apart.
        conn = FakeConnection(rows=(
            (_REPO_A, 5, 30, 4, 0.5),
            (_REPO_B, 2, 10, 1, 0.1),
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
                "total_cost_usd": 0.5,
            },
        )
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (_ROLLUP_SCAN, "COUNT(DISTINCT issue)", _AGENT_EXIT_CONDITION),
        )


if __name__ == "__main__":
    unittest.main()
