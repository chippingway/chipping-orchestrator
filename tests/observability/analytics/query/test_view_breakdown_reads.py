# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three breakdowns read off the agent-run view rather than the rollup."""
from __future__ import annotations

import unittest
from datetime import date
from itertools import product

from orchestrator.observability.analytics.query import cache_shares, cost_cohorts
from orchestrator.observability.analytics.query.breakdown_reads import (
    get_backend_daily_tokens,
    get_cost_coverage,
    get_review_round_breakdown,
)
from orchestrator.observability.analytics.query.token_totals import RUN_TOKEN_TOTAL_SQL
from tests.observability.analytics import analytics_cohorts as cohort_cases
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

# What a token volume read off the view is: the runs' stored non-overlapping
# totals, never the raw counters added up, beside the runs whose total is
# unknown -- so a Codex run's cached input is not counted twice, and a run no
# evidence totals is counted rather than summed as zero.
_TOKEN_TOTAL_FRAGMENTS = (
    RUN_TOKEN_TOTAL_SQL,
    "SUM(total_tokens)",
    "WHEN total_tokens IS NULL THEN 1",
)

# The raw counters, none of which a token volume may add up again.
_RAW_COUNTERS = ("input_tokens", "output_tokens", "cached_tokens", "cache_read_tokens", "cache_write_tokens")

# One round-and-role row at its full width: the bucket and role, their runs
# and failures, the role's three token-share bands -- the cache share, the
# rest, and the amount nothing split -- and the cells its cost cohort is read
# from.
_DEVELOPER = "developer"

_REVIEWER = "reviewer"

_INITIAL_DEV_COSTS = cohort_cases.NAMED_COSTS["mixed providers"]

_INITIAL_REV_COSTS = cohort_cases.NAMED_COSTS["agy only"]

_FIRST_DEV_COSTS = cohort_cases.NAMED_COSTS["incomplete"]

_UNROUNDED_COSTS = cohort_cases.NAMED_COSTS["missing basis"]

_INITIAL_DEV_BANDS = (0.3, 0.2, 0)

_INITIAL_REV_BANDS = (0, 0, 0.32)

_FIRST_DEV_BANDS = (0.1, 0.1, 0)

_UNROUNDED_BANDS = (0, 0, 0.07)

_ROUND_ROW = (_ROUND_ZERO, _DEVELOPER, 3, 1, *_INITIAL_DEV_BANDS) + cohort_cases.cohort_cells(_INITIAL_DEV_COSTS)

# Each role's rows arrive apart, in the bucket-then-role order the scan returns
# them, and the first round has no review run at all.
_ROUND_ROWS = (
    _ROUND_ROW,
    (_ROUND_ZERO, _REVIEWER, 2, 0, *_INITIAL_REV_BANDS) + cohort_cases.cohort_cells(_INITIAL_REV_COSTS),
    ("1", _DEVELOPER, 3, 2, *_FIRST_DEV_BANDS) + cohort_cases.cohort_cells(_FIRST_DEV_COSTS),
    (_UNKNOWN, _DEVELOPER, 2, 0, *_UNROUNDED_BANDS) + cohort_cases.cohort_cells(_UNROUNDED_COSTS),
)

_COVERAGE_ROW = (_REPORTED, 20, _REPORTED_TOKENS, 0)

_BACKEND_ROW = (_DAY_ONE, _CLAUDE, _CLAUDE_DAY_ONE_TOKENS, 0)

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
    """How one window's spend divides across the rounds it took and the two roles that worked them."""

    def test_each_round_folds_its_two_roles(self) -> None:
        # A role's cohort is read whole off its own row -- an AGY review's
        # Gemini estimate, a mixed development's parts, a subtotal, an amount
        # with no basis -- and a round folds its two roles into one cohort,
        # busiest round first; a role with no run in a round is the empty
        # cohort with no bands, not a zero.
        conn = FakeConnection(rows=_ROUND_ROWS)
        with configured_db_url():
            rows = get_review_round_breakdown(connect=conn.as_connect)
        empty = cost_cohorts.EMPTY_COST_COHORT
        assert_column_values(
            self,
            rows,
            {
                "bucket": [_ROUND_ZERO, "1", _UNKNOWN],
                "runs": [5, 3, 2],
                "failed": [1, 2, 0],
                "developer_runs": [3, 3, 2],
                "reviewer_runs": [2, 0, 0],
                "developer_cost": [
                    cohort_cases.cohort(*_INITIAL_DEV_COSTS),
                    cohort_cases.cohort(*_FIRST_DEV_COSTS),
                    cohort_cases.cohort(*_UNROUNDED_COSTS),
                ],
                "reviewer_cost": [cohort_cases.cohort(*_INITIAL_REV_COSTS), empty, empty],
                "developer_bands": [
                    cache_shares.TokenShareBands(*_INITIAL_DEV_BANDS),
                    cache_shares.TokenShareBands(*_FIRST_DEV_BANDS),
                    cache_shares.TokenShareBands(*_UNROUNDED_BANDS),
                ],
                "reviewer_bands": [
                    cache_shares.TokenShareBands(*_INITIAL_REV_BANDS),
                    cache_shares.NO_TOKEN_SHARE,
                    cache_shares.NO_TOKEN_SHARE,
                ],
            },
        )
        initial = cohort_cases.cohort(*_INITIAL_DEV_COSTS, *_INITIAL_REV_COSTS)
        self.assertEqual(rows[0].cost, initial)

    def test_the_scan_groups_rounds_and_roles(self) -> None:
        # A run that recorded no round reads as `unknown` whatever its role or
        # stage -- every current run records one, a fresh implementation as
        # round zero -- the scan narrows to the two reviewed roles and groups
        # them apart, and each role's spend is the run view's cohort and
        # token-share split rather than a sum of `cost_usd`.
        conn = FakeConnection(rows=(_ROUND_ROW,))
        with configured_db_url():
            get_review_round_breakdown(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        self.assertNotIn("stage = 'implementing'", scan_sql)
        self.assertNotIn("cost_usd)", scan_sql)
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _VIEW_SCAN,
                "agent_role IN ('developer', 'reviewer')",
                "GROUP BY bucket, agent_role",
                "WHEN review_round IS NULL THEN 'unknown'",
                "THEN '6+'",
                cost_cohorts.RUN_COST_COHORT_SQL,
                cache_shares.RUN_TOKEN_SHARE_SQL,
            ),
        )

    def test_a_row_of_another_width_raises(self) -> None:
        # A row narrower or wider than its SELECT list is a broken query, never
        # a role whose cost or bands read as NULL.
        for row in (_ROUND_ROW[:-1], (*_ROUND_ROW, None)):
            conn = FakeConnection(rows=(row,))
            with self.subTest(width=len(row)), configured_db_url(), self.assertRaises(TypeError):
                get_review_round_breakdown(connect=conn.as_connect)


class CostCoverageReadTest(unittest.TestCase):
    """Which sources the window's spend could be attributed to."""

    def test_an_unpriced_model_keeps_its_bucket(self) -> None:
        # `unknown-price` is the signal that a model is missing from the price
        # tables, so it never folds into the `unknown` bucket a run with no
        # recorded source falls to: the two ask for different fixes.
        # A source's runs whose token totals nothing settles are counted
        # beside its known subtotal: the `unknown` bucket here totals none of
        # its tokens, which is not the same as spending none.
        conn = FakeConnection(rows=(
            _COVERAGE_ROW,
            ("estimated", 5, 100_000, 0),
            (_UNKNOWN_PRICE, 3, _UNPRICED_TOKENS, 1),
            ("no-usage", 2, 20_000, 0),
            (_UNKNOWN, 1, 0, 1),
        ))
        with configured_db_url():
            rows = get_cost_coverage(connect=conn.as_connect)
        assert_column_values(
            self,
            rows,
            {
                "cost_source": [_REPORTED, "estimated", _UNKNOWN_PRICE, "no-usage", _UNKNOWN],
                "total_tokens": [_REPORTED_TOKENS, 100_000, _UNPRICED_TOKENS, 20_000, 0],
                "unknown_token_runs": [0, 0, 1, 0, 1],
            },
        )

    def test_the_scan_names_nulls_and_sums_totals(self) -> None:
        conn = FakeConnection(rows=(_COVERAGE_ROW,))
        with configured_db_url():
            get_cost_coverage(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            ("COALESCE(cost_source, 'unknown')", *_TOKEN_TOTAL_FRAGMENTS),
        )
        for counter in _RAW_COUNTERS:
            self.assertNotIn(counter, scan_sql)


class BackendDailyTokensReadTest(unittest.TestCase):
    """What each backend spent in tokens, day by day."""

    def test_each_cell_pairs_a_day_and_backend(self) -> None:
        conn = FakeConnection(rows=(
            _BACKEND_ROW,
            (_DAY_ONE, "agy", 0, 2),
            (_DAY_TWO, _CLAUDE, 8_000, 0),
        ))
        with configured_db_url():
            rows = get_backend_daily_tokens(connect=conn.as_connect)
        assert_column_values(
            self,
            rows,
            {
                "day": [_DAY_ONE, _DAY_ONE, _DAY_TWO],
                "backend": [_CLAUDE, "agy", _CLAUDE],
                "total_tokens": [_CLAUDE_DAY_ONE_TOKENS, 0, 8_000],
                "unknown_token_runs": [0, 2, 0],
            },
        )

    def test_the_scan_groups_and_names_nulls(self) -> None:
        # Grouping by day and backend together is what lets a chart stack the
        # bands without a second pass, and the volume is the runs' stored
        # totals, so cached input already inside a run's input is not stacked
        # on top of it again.
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
                *_TOKEN_TOTAL_FRAGMENTS,
            ),
        )
        for counter in _RAW_COUNTERS:
            self.assertNotIn(counter, scan_sql)


if __name__ == "__main__":
    unittest.main()
