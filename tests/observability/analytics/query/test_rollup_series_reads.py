# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one window looks like day by day: its volume, and what it resolved."""
from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query.cost_cohorts import ROLLUP_COST_COHORT_SQL
from orchestrator.observability.analytics.query.rollup_reads import (
    get_throughput_breakdown,
    get_time_series,
)
from orchestrator.observability.analytics.query.token_totals import ROLLUP_TOKEN_TOTAL_SQL
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

_DONE = "done"

_REJECTED = "rejected"

_YEAR = 2026

_DAY_NUMBER = 25

_NEXT_DAY_NUMBER = 26

_DAY = date(_YEAR, 5, _DAY_NUMBER)

_NEXT_DAY = date(_YEAR, 5, _NEXT_DAY_NUMBER)

_WIDENED_DAY = datetime(_YEAR, 5, _DAY_NUMBER, 0, 0, tzinfo=UTC)

# A day holding a Claude run and a Codex run, each with its known total, beside
# an Antigravity run whose total is unknown: the known total is Claude's 470
# plus Codex's 1,100, the cache inside it Claude's 350 reads and writes plus
# Codex's 400 cached input, and the output inside it 20 plus 100.
_COSTS = (cases.REPORTED, cases.OPENAI_ESTIMATE, cases.GEMINI_ESTIMATE)

_KNOWN_TOKENS = cases.CLAUDE_TOTAL + cases.CODEX_TOTAL

_CACHE_TOKENS = cases.CLAUDE_CACHE + cases.CODEX_CACHED

_OUTPUT_TOKENS = cases.CLAUDE_OUTPUT + cases.CODEX_OUTPUT

_TOKEN_CELLS = (_KNOWN_TOKENS, 1, _CACHE_TOKENS, _OUTPUT_TOKENS)

_EXPECTED_CELL = MappingProxyType({
    "count": 3,
    "total_tokens": _KNOWN_TOKENS,
    "unknown_token_runs": 1,
    "cache_tokens": _CACHE_TOKENS,
    "output_tokens": _OUTPUT_TOKENS,
    # Claude's 100 input plus the 600 of Codex's 1,000 no cache answered.
    "uncached_input_tokens": cases.CLAUDE_INPUT + cases.CODEX_UNCACHED_INPUT,
})

# The rollup columns each per-day aggregate is reduced from, so a rename under
# the rollup surfaces here rather than as a flat line on a chart.
_REDUCED_COLUMNS = (
    ROLLUP_COST_COHORT_SQL,
    ROLLUP_TOKEN_TOTAL_SQL,
    "SUM(cache_tokens_in_total)",
    "SUM(output_tokens_in_total)",
)

# What a stack built off the raw counters would add, a Codex run's cached input
# among them twice, and the one summed amount a cohort replaces.
_RAW_SUMS = (
    "SUM(total_cost_usd)",
    "SUM(total_input_tokens)",
    "SUM(total_cache_read_tokens)",
    "SUM(total_cached_tokens)",
)


_NO_TOKENS = (0, 0, 0, 0)


def _cell(day: object, event: str, count: int, costs: tuple = (), tokens: tuple = _NO_TOKENS) -> tuple:
    """One `(day, event)` cell at its full width: key, count, cohort, tokens."""
    cohort_cells = cohort_cases.cohort_cells(costs)
    return (day, event, count, *cohort_cells, *tokens)


# Every selection that leaves the throughput read nothing to count: an events
# selection without `stage_enter`, a cleared one, and a stage selection that
# misses both terminals.
_EMPTY_SELECTIONS = (
    {"events": [_AGENT_EXIT]},
    {"events": []},
    {"stages": []},
    {"stages": [_STAGE_IMPLEMENTING, _STAGE_VALIDATING]},
)


class TimeSeriesReadTest(unittest.TestCase):
    """The per-day-and-event cells the volume, spend, and token charts pivot."""

    def test_an_unconfigured_database_plots_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_time_series(connect=FakeConnect()), [])

    def test_each_aggregate_rides_on_its_cell(self) -> None:
        conn = FakeConnection(rows=(_cell(_DAY, _AGENT_EXIT, 3, _COSTS, _TOKEN_CELLS),))
        with configured_db_url():
            points = get_time_series(connect=conn.as_connect)
        self.assertEqual(len(points), 1)
        assert_row_fields(self, points[0], _EXPECTED_CELL)
        self.assertEqual(points[0].cost, cohort_cases.cohort(*_COSTS))
        # The three bands a stack draws add up to the known total, so the
        # cached input Codex counts inside its input is drawn once.
        point = points[0]
        self.assertEqual(
            point.uncached_input_tokens + point.output_tokens + point.cache_tokens,
            point.total_tokens,
        )
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(self, scan_sql, _REDUCED_COLUMNS)
        for raw_sum in _RAW_SUMS:
            with self.subTest(raw_sum=raw_sum):
                self.assertNotIn(raw_sum, scan_sql)
        # The rollup is already keyed on the day, so the bucket is the grouping
        # key rather than a truncation computed at scan time.
        self.assertIn("GROUP BY day, event", scan_sql)
        self.assertIn("ORDER BY day ASC, event ASC", scan_sql)

    def test_a_runless_cell_holds_the_empty_cohort(self) -> None:
        # A day of stage events carries no run, which is an empty cohort rather
        # than a spend of zero, and no tokens.
        conn = FakeConnection(rows=(_cell(_DAY, _STAGE_ENTER, 5),))
        with configured_db_url():
            point = get_time_series(connect=conn.as_connect)[0]
        self.assertTrue(point.cost.is_empty)
        self.assertIsNone(point.cost.evidence.total_usd)
        self.assertEqual((point.total_tokens, point.unknown_token_runs), (0, 0))

    def test_a_narrower_cell_raises(self) -> None:
        narrow = _cell(_DAY, _AGENT_EXIT, 1)[:-1]
        conn = FakeConnection(rows=(narrow,))
        with configured_db_url(), self.assertRaises(ValueError):
            get_time_series(connect=conn.as_connect)

    def test_a_widened_day_narrows_back_to_a_date(self) -> None:
        # Some drivers hand the `day` column back as a timestamp even where the
        # column is a date, and a chart keying its series on days would then be
        # comparing a date against midnight.
        conn = FakeConnection(rows=(
            _cell(_WIDENED_DAY, _STAGE_ENTER, 5),
            _cell(_NEXT_DAY, _STAGE_ENTER, 7),
        ))
        with configured_db_url():
            points = get_time_series(connect=conn.as_connect)
        self.assertEqual([point.day for point in points], [_DAY, _NEXT_DAY])


class ThroughputReadTest(unittest.TestCase):
    """The two terminal stages each day resolved or turned away."""

    def test_an_unconfigured_database_counts_nothing(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_throughput_breakdown(connect=FakeConnect()), [])

    def test_a_selection_without_terminals_stops(self) -> None:
        for selection in _EMPTY_SELECTIONS:
            with self.subTest(selection=selection), configured_db_url():
                self.assertEqual(
                    get_throughput_breakdown(
                        connect=FakeConnect(),
                        **selection,
                    ),
                    [],
                )

    def test_each_day_is_a_resolved_rejected_pair(self) -> None:
        conn = FakeConnection(rows=((_DAY, 3, 1), (_NEXT_DAY, 5, 0)))
        with configured_db_url():
            rows = get_throughput_breakdown(connect=conn.as_connect)
        self.assertEqual(
            [(row.day, row.resolved, row.rejected) for row in rows],
            [(_DAY, 3, 1), (_NEXT_DAY, 5, 0)],
        )
        scan_sql, bindings = conn.executed[0]
        # The pinned event binds ahead of the generated predicate, and both
        # terminals are bound rather than spliced into the clause.
        assert_sql_fragments(self, scan_sql, ("event = %s", "stage IN"))
        self.assertEqual(bindings[0], _STAGE_ENTER)
        self.assertTrue({_DONE, _REJECTED}.issubset(bindings))

    def test_a_named_terminal_narrows_the_scan(self) -> None:
        # A selection naming one terminal alongside work in flight is asking
        # about that terminal, so the intersection is what binds.
        conn = FakeConnection(rows=((_DAY, 1, 0),))
        with configured_db_url():
            rows = get_throughput_breakdown(
                stages=[_DONE, _STAGE_IMPLEMENTING],
                connect=conn.as_connect,
            )
        self.assertEqual(len(rows), 1)
        _, bindings = conn.executed[0]
        self.assertIn(_DONE, bindings)
        self.assertNotIn(_REJECTED, bindings)
        self.assertNotIn(_STAGE_IMPLEMENTING, bindings)


if __name__ == "__main__":
    unittest.main()
