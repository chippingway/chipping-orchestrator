# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The newest agent runs a window holds, what each stored as its cost, and who has none to ask for.

A run's cost is the evidence the sync filed on its row, read back as it was filed: a CLI-reported amount stays the one
its record ranked ahead of any estimate, an estimate keeps the dates its rates were verified on, and a row an earlier
build stored with no evidence reads `unknown`, its amount under that basis -- none of it repriced from the tokens beside
it.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.raw_reads import get_recent_agent_exits
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.analytics_assertions import assert_row_fields
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url
from tests.observability.analytics.query.run_rows_test_support import run_cost_cells

_AGENT_EXIT = "agent_exit"

_BASE_SCAN = "FROM analytics_events"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_STAGE_ENTER = "stage_enter"

_STAGE_IMPLEMENTING = "implementing"

_REPO = "owner/r"

_ISSUE = 7

_BACKEND_CLAUDE = "claude"

_AGENT_ROLE_DEV = "dev"

_LIMIT = 10

_DURATION_S = 33.0

_REVIEW_ROUND = 1

_INPUT_TOKENS = 100

_OUTPUT_TOKENS = 200

_TOTAL_TOKENS = 300

_YEAR = 2026

_EXIT_TS_DAY = 25

_EXIT_TS_HOUR = 12

_WINDOW_END_DAY = 28

_EXIT_TS = datetime(_YEAR, 5, _EXIT_TS_DAY, _EXIT_TS_HOUR, 0, tzinfo=UTC)

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, _WINDOW_END_DAY, tzinfo=UTC)

# The columns of one row of the SELECT list ahead of its cost cells, in the
# order the projection unpacks them.
_EXIT_COLUMNS = (
    _EXIT_TS,
    _REPO,
    _ISSUE,
    _STAGE_IMPLEMENTING,
    _AGENT_ROLE_DEV,
    _BACKEND_CLAUDE,
    _DURATION_S,
    0,
    False,
    _REVIEW_ROUND,
    0,
    _INPUT_TOKENS,
    _OUTPUT_TOKENS,
    _TOTAL_TOKENS,
)

_EXIT_ROW = _EXIT_COLUMNS + run_cost_cells(cases.REPORTED)

# The same columns for a run whose token total its evidence left unknown.
_UNTOTALLED_COLUMNS = (*_EXIT_COLUMNS[:-1], None)

# The costs a run's row can store, each read back as that run's own evidence:
# a reported amount, a reported zero, each provider's dated estimate, a run
# blending the two, a subtotal, an unpriced run, and a basis-less amount.
_RUN_COSTS = (
    ("reported", cases.REPORTED),
    ("reported zero", cases.COMPLETE_ZERO),
    ("anthropic estimate", cases.ANTHROPIC_ESTIMATE),
    ("openai estimate", cases.OPENAI_ESTIMATE),
    ("antigravity estimate", cases.GEMINI_ESTIMATE),
    ("blended", cases.BLENDED),
    ("subtotal", cases.INCOMPLETE_SUBTOTAL),
    ("unpriced", cases.UNPRICED),
    ("missing basis", cases.ABSENT_BASIS),
)


class RecentAgentExitsTest(unittest.TestCase):
    """The read behind the recent-runs table: newest first, capped, filtered."""

    def test_an_unconfigured_database_returns_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_recent_agent_exits(connect=FakeConnect()), [])

    def test_a_non_positive_cap_never_dials(self) -> None:
        # Nothing can come back under a cap of zero, so the answer is settled
        # before a connection is opened.
        with configured_db_url():
            self.assertEqual(
                get_recent_agent_exits(limit=0, connect=FakeConnect()),
                [],
            )

    def test_a_row_projects_and_binds_in_order(self) -> None:
        # The pinned `event = 'agent_exit'` binds ahead of the generated
        # window predicate and the cap binds last, so the three groups cannot
        # drift out of the order the clause was composed in.
        conn = FakeConnection(rows=(_EXIT_ROW,))
        with configured_db_url():
            exits = get_recent_agent_exits(
                limit=_LIMIT,
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                connect=conn.as_connect,
            )
        self.assertEqual(len(exits), 1)
        assert_row_fields(
            self,
            exits[0],
            {
                "ts": _EXIT_TS,
                "repo": _REPO,
                "issue": _ISSUE,
                "stage": _STAGE_IMPLEMENTING,
                "agent_role": _AGENT_ROLE_DEV,
                "backend": _BACKEND_CLAUDE,
                "duration_s": _DURATION_S,
                "exit_code": 0,
                "timed_out": False,
                "review_round": _REVIEW_ROUND,
                "input_tokens": _INPUT_TOKENS,
                "output_tokens": _OUTPUT_TOKENS,
                "total_tokens": _TOTAL_TOKENS,
                "cost": cases.REPORTED,
            },
        )
        scan_sql, bindings = conn.executed[0]
        self.assertIn("event = %s", scan_sql)
        self.assertIn("ORDER BY ts DESC LIMIT %s", scan_sql)
        self.assertEqual(
            bindings,
            (_AGENT_EXIT, _WINDOW_START, _WINDOW_END, _REPO, _LIMIT),
        )

    def test_the_scan_stays_on_the_events_table(self) -> None:
        # Per-row `ts` precision, `review_round`, and `retry_count` are what
        # the day bucket threw away, so a read moved onto the rollup would be
        # asking it for columns it does not carry.
        conn = FakeConnection()
        with configured_db_url():
            get_recent_agent_exits(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        self.assertIn(_BASE_SCAN, scan_sql)
        self.assertNotIn(_ROLLUP_SCAN, scan_sql)

    def test_a_kept_agent_exit_still_queries(self) -> None:
        conn = FakeConnection()
        with configured_db_url():
            get_recent_agent_exits(
                events=[_AGENT_EXIT, _STAGE_ENTER],
                stages=[_STAGE_IMPLEMENTING],
                connect=conn.as_connect,
            )
        scan_sql, _ = conn.executed[0]
        # The event selection is dropped in favour of the pinned equality,
        # while the stage selection still narrows the scan.
        self.assertIn("event = %s", scan_sql)
        self.assertIn("stage IN (%s)", scan_sql)
        self.assertNotIn("event IN (%s)", scan_sql)

    def test_no_agent_exit_selected_never_dials(self) -> None:
        # Deselecting `agent_exit`, or clearing the stage multiselect, leaves
        # no row this table could show -- so no connection is opened either.
        for selection in ({"events": [_STAGE_ENTER]}, {"stages": []}):
            with self.subTest(selection=selection), configured_db_url():
                self.assertEqual(
                    get_recent_agent_exits(connect=FakeConnect(), **selection),
                    [],
                )


class RecentRunCostTest(unittest.TestCase):
    """Each run carries the cost its own row stored, never a sum or a reprice."""

    def test_a_run_reads_back_its_stored_cost(self) -> None:
        # The run's own cells, unsummed, are its evidence as filed -- the
        # basis its record ranked first, and an estimate's rate dates -- and
        # an unknown token total stays unknown rather than reading as zero.
        for name, spent in _RUN_COSTS:
            with self.subTest(cost=name):
                conn = FakeConnection(rows=(_UNTOTALLED_COLUMNS + run_cost_cells(spent),))
                with configured_db_url():
                    run = get_recent_agent_exits(connect=conn.as_connect)[0]
                self.assertEqual((run.cost, run.total_tokens), (spent, None))
                scan_sql, _ = conn.executed[0]
                self.assertIn("total_tokens, ", scan_sql)
                self.assertIn("anthropic_rates_verified_on", scan_sql)
                self.assertNotIn("SUM(", scan_sql)

    def test_a_row_of_another_width_raises(self) -> None:
        # The cost cells close the SELECT list, so a row short of one is a
        # broken query, never a run whose cost reads as NULL.
        conn = FakeConnection(rows=(_EXIT_ROW[:-1],))
        with configured_db_url(), self.assertRaises(TypeError):
            get_recent_agent_exits(connect=conn.as_connect)


if __name__ == "__main__":
    unittest.main()
