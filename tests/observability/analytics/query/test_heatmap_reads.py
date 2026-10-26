# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the work happened, bucketed by weekday and hour of a chosen zone."""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query.breakdown_reads import get_hourly_heatmap
from tests.observability.analytics.analytics_assertions import assert_column_values, assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url

_AGENT_EXIT = "agent_exit"

_BASE_SCAN = "FROM analytics_events"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

# One cell at its full width: weekday / hour / event count / cell tokens.
_CELL = (1, 9, 5, 25_000)

_CELLS = (_CELL, (1, 14, 7, 40_000), (3, 22, 2, 4_500))

# The offsets an operator can pick: none, an eastern zone, and a western one --
# which binds a negative integer Postgres reduces to a backwards shift.
_TZ_OFFSETS = (0, 7, -5)


class HourlyHeatmapReadTest(unittest.TestCase):
    """One weekday-and-hour cell, counted where the hour still exists."""

    def test_an_unconfigured_database_answers_empty(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_hourly_heatmap(connect=FakeConnect()), [])

    def test_each_cell_carries_count_and_tokens(self) -> None:
        conn = FakeConnection(rows=_CELLS)
        with configured_db_url():
            cells = get_hourly_heatmap(connect=conn.as_connect)
        assert_column_values(
            self,
            cells,
            {
                "weekday": [1, 1, 3],
                "hour": [9, 14, 22],
                "count": [5, 7, 2],
                "total_tokens": [25_000, 40_000, 4_500],
            },
        )

    def test_the_scan_stays_where_the_hour_survives(self) -> None:
        # The rollup buckets by day, so an hour of day is not recoverable from
        # it -- this read has to keep scanning the events table. Token volume
        # rides beside the count so a page can render intensity by spend rather
        # than by the many cheap rows that dwarf the agent runs.
        conn = FakeConnection(rows=(_CELL,))
        with configured_db_url():
            get_hourly_heatmap(connect=conn.as_connect)
        scan_sql, _ = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                _BASE_SCAN,
                "EXTRACT(DOW FROM",
                "EXTRACT(HOUR FROM",
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
            ),
        )
        self.assertNotIn(_ROLLUP_SCAN, scan_sql)

    def test_the_event_selection_binds(self) -> None:
        # Unlike the view-backed breakdowns beside it, this scan has an `event`
        # column, so the selection becomes an ordinary bound predicate rather
        # than a short circuit.
        conn = FakeConnection(rows=(_CELL,))
        with configured_db_url():
            get_hourly_heatmap(events=[_AGENT_EXIT], connect=conn.as_connect)
        scan_sql, bindings = conn.executed[0]
        self.assertIn("event IN (%s)", scan_sql)
        self.assertIn(_AGENT_EXIT, bindings)

    def test_the_offset_leads_the_bindings(self) -> None:
        # `ts` is normalized to UTC before the offset is added, so a session
        # whose own timezone is not UTC cannot shift the buckets a second time.
        # Both extractions take the offset, so it binds twice and ahead of the
        # window filters -- and is never spliced into the text.
        for tz_offset in _TZ_OFFSETS:
            conn = FakeConnection(rows=(_CELL,))
            with self.subTest(tz_offset=tz_offset), configured_db_url():
                get_hourly_heatmap(
                    tz_offset_hours=tz_offset,
                    connect=conn.as_connect,
                )
            scan_sql, bindings = conn.executed[0]
            assert_sql_fragments(
                self,
                scan_sql,
                ("ts AT TIME ZONE 'UTC'", "%s * INTERVAL '1 hour'"),
            )
            self.assertEqual(bindings[:2], (tz_offset, tz_offset))


if __name__ == "__main__":
    unittest.main()
