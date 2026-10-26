# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three breakdowns read off the agent-run view rather than the rollup."""
from __future__ import annotations

import unittest
from datetime import date
from itertools import product

from orchestrator.observability.analytics.query.breakdown_reads import (
    get_backend_daily_tokens,
    get_cost_coverage,
    get_review_round_breakdown,
)
from tests.observability.analytics.analytics_assertions import (
    assert_column_values,
    assert_sql_fragments,
)
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url

_AGENT_EXIT = "agent_exit"

_STAGE_ENTER = "stage_enter"

_VIEW_SCAN = "FROM analytics_agent_runs"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_UNKNOWN = "unknown"

_UNKNOWN_PRICE = "unknown-price"

_REPORTED = "reported"

_ROUND_ZERO = "0"

_CLAUDE = "claude"

_CODEX = "codex"

_YEAR = 2026

_DAY_ONE = date(_YEAR, 5, 1)

_DAY_TWO = date(_YEAR, 5, 2)

_REPORTED_TOKENS = 800_000

_UNPRICED_TOKENS = 60_000

_CLAUDE_DAY_ONE_TOKENS = 12_000

# The four token columns each of these three sums, so a volume read off any of
# them is measured against the same billable bands.
_TOKEN_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)

# One review-round bucket at its full width, a group per line: the bucket and
# its totals, the two roles' run counts, their costs, and the cache band of
# each role's cost followed by its no-cache complement.
_ROUND_ROW = (
    _ROUND_ZERO, 12, 1, 40,
    7, 5,
    28, 12,
    20, 8, 9, 3,
)

_ROUND_ROWS = (
    _ROUND_ROW,
    ("1", 8, 2, 25, 4, 4, 10, 15, 7, 3, 11, 4),
    ("3-5", 4, 4, 18, 1, 3, 5, 13, 5, 0, 13, 0),
    (_UNKNOWN, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0),
)

_COVERAGE_ROW = (_REPORTED, 20, _REPORTED_TOKENS)

_BACKEND_ROW = (_DAY_ONE, _CLAUDE, _CLAUDE_DAY_ONE_TOKENS)

# The three reads and one row wide enough for each, so what they share -- the
# scan target and both short circuits -- is pinned once per read rather than
# once per family.
_VIEW_READS = (
    (get_review_round_breakdown, _ROUND_ROW),
    (get_cost_coverage, _COVERAGE_ROW),
    (get_backend_daily_tokens, _BACKEND_ROW),
)

# The same three where only the call matters, so a check about what never
# happens does not have to name a row it will not read.
_VIEW_READ_CALLS = tuple(read for read, _row in _VIEW_READS)

# The two selections the view leaves nothing to match: one that names other
# events, and the cleared multiselect.
_EXIT_FREE_SELECTIONS = ([_STAGE_ENTER], [])


class ViewReadShortCircuitTest(unittest.TestCase):
    """What the three settle before dialing, because the view fixes it."""

    def test_an_unconfigured_database_answers_empty(self) -> None:
        for read in _VIEW_READ_CALLS:
            with self.subTest(read=read.__name__), configured_db_url(None):
                self.assertEqual(read(connect=FakeConnect()), [])

    def test_a_selection_without_exits_stops(self) -> None:
        # The view filters to `agent_exit` internally and carries no `event`
        # column to push a selection into, so a selection those rows fall
        # outside of is answered without opening a socket.
        for read, events in product(_VIEW_READ_CALLS, _EXIT_FREE_SELECTIONS):
            with self.subTest(read=read.__name__, events=events):
                with configured_db_url():
                    empty = read(events=events, connect=FakeConnect())
                self.assertEqual(empty, [])

    def test_a_selection_naming_exits_scans(self) -> None:
        for read, row in _VIEW_READS:
            conn = FakeConnection(rows=(row,))
            with self.subTest(read=read.__name__), configured_db_url():
                rows = read(events=[_AGENT_EXIT], connect=conn.as_connect)
                self.assertEqual(len(rows), 1)
            scan_sql, _ = conn.executed[0]
            self.assertIn(_VIEW_SCAN, scan_sql)
            self.assertNotIn(_ROLLUP_SCAN, scan_sql)
            # The selection cannot reach the SQL, which is the whole reason the
            # short circuit above has to exist.
            self.assertNotIn("event IN", scan_sql)


class ReviewRoundReadTest(unittest.TestCase):
    """How one window's spend divides across the rounds it took."""

    def test_each_bucket_carries_roles_and_bands(self) -> None:
        conn = FakeConnection(rows=_ROUND_ROWS)
        with configured_db_url():
            rows = get_review_round_breakdown(connect=conn.as_connect)
        assert_column_values(
            self,
            rows,
            {
                "bucket": [_ROUND_ZERO, "1", "3-5", _UNKNOWN],
                "runs": [12, 8, 4, 1],
                "failed": [1, 2, 4, 0],
                "total_cost_usd": [40, 25, 18, 0],
                "developer_runs": [7, 4, 1, 1],
                "reviewer_runs": [5, 4, 3, 0],
                "developer_cost_usd": [28, 10, 5, 0],
                "reviewer_cost_usd": [12, 15, 13, 0],
                "developer_cache_cost_usd": [20, 7, 5, 0],
                "developer_no_cache_cost_usd": [8, 3, 0, 0],
                "reviewer_cache_cost_usd": [9, 11, 13, 0],
                "reviewer_no_cache_cost_usd": [3, 4, 0, 0],
            },
        )

    def test_the_scan_labels_and_splits_rounds(self) -> None:
        # A run that recorded no round reads as `unknown` whatever its role or
        # stage -- every current run records one, a fresh implementation as
        # round zero -- the scan narrows to the two reviewed roles, and each
        # role's cost is prorated by its cache-token share, with the Codex
        # `cached_tokens` subset in the numerator only, so the two bands sum
        # back to the role's total.
        conn = FakeConnection(rows=(_ROUND_ROW,))
        with configured_db_url():
            get_review_round_breakdown(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        self.assertNotIn("stage = 'implementing'", scan_sql)
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _VIEW_SCAN,
                "SUM(cost_usd)",
                "agent_role IN ('developer', 'reviewer')",
                "agent_role = 'developer'",
                "agent_role = 'reviewer'",
                "WHEN review_round IS NULL THEN 'unknown'",
                "THEN '6+'",
                "cached_tokens",
                "developer_cache_cost_usd",
                "developer_no_cache_cost_usd",
                "reviewer_cache_cost_usd",
                "reviewer_no_cache_cost_usd",
            ),
        )


class CostCoverageReadTest(unittest.TestCase):
    """Which sources the window's spend could be attributed to."""

    def test_an_unpriced_model_keeps_its_bucket(self) -> None:
        # `unknown-price` is the signal that a model is missing from the price
        # tables, so it never folds into the `unknown` bucket a run with no
        # recorded source falls to: the two ask for different fixes.
        conn = FakeConnection(rows=(
            _COVERAGE_ROW,
            ("estimated", 5, 100_000),
            (_UNKNOWN_PRICE, 3, _UNPRICED_TOKENS),
            ("no-usage", 2, 20_000),
            (_UNKNOWN, 1, 5_000),
        ))
        with configured_db_url():
            rows = get_cost_coverage(connect=conn.as_connect)
        self.assertEqual(
            [row.cost_source for row in rows],
            [_REPORTED, "estimated", _UNKNOWN_PRICE, "no-usage", _UNKNOWN],
        )
        by_source = {row.cost_source: row for row in rows}
        self.assertEqual(by_source[_REPORTED].total_tokens, _REPORTED_TOKENS)
        self.assertEqual(
            by_source[_UNKNOWN_PRICE].total_tokens,
            _UNPRICED_TOKENS,
        )

    def test_the_scan_names_nulls_and_sums_bands(self) -> None:
        conn = FakeConnection(rows=(_COVERAGE_ROW,))
        with configured_db_url():
            get_cost_coverage(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            ("COALESCE(cost_source, 'unknown')", *_TOKEN_COLUMNS),
        )


class BackendDailyTokensReadTest(unittest.TestCase):
    """What each backend spent in tokens, day by day."""

    def test_each_cell_pairs_a_day_and_backend(self) -> None:
        conn = FakeConnection(rows=(
            _BACKEND_ROW,
            (_DAY_ONE, _CODEX, 4_500),
            (_DAY_TWO, _CLAUDE, 8_000),
        ))
        with configured_db_url():
            rows = get_backend_daily_tokens(connect=conn.as_connect)
        assert_column_values(
            self,
            rows,
            {
                "day": [_DAY_ONE, _DAY_ONE, _DAY_TWO],
                "backend": [_CLAUDE, _CODEX, _CLAUDE],
                "total_tokens": [_CLAUDE_DAY_ONE_TOKENS, 4_500, 8_000],
            },
        )

    def test_the_scan_groups_and_names_nulls(self) -> None:
        # Grouping by day and backend together is what lets a chart stack the
        # bands without a second pass, and the token sum covers the cache bands
        # so the stack reconciles with the cost line beside it.
        conn = FakeConnection(rows=(_BACKEND_ROW,))
        with configured_db_url():
            get_backend_daily_tokens(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                "GROUP BY day, backend_label",
                "COALESCE(backend, 'unknown')",
                *_TOKEN_COLUMNS,
            ),
        )


if __name__ == "__main__":
    unittest.main()
