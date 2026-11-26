# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a window's unpriced runs have no amount, counted by model and reason over the whole filtered selection.

The count reads the reasons each run's record carried into `extras`, which only the events table holds, so it scans
that table and pins `agent_exit` itself -- uncapped, unlike the run listing beside it -- and reads the rows back in the
order SQL ranked them. A run recorded without reasons comes back with none, under each model it names.
"""
from __future__ import annotations

import unittest
from datetime import datetime

from orchestrator.observability.analytics.query.breakdown_reads import get_unpriced_reasons
from orchestrator.observability.analytics.query.cost_models import UnpricedReasonRow
from orchestrator.observability.usage import cost_evidence as usage_cost, unpriced as usage_unpriced
from tests.observability.analytics.analytics_assertions import assert_sql_fragments
from tests.observability.analytics.query.query_fake_driver import FakeConnect, FakeConnection
from tests.observability.analytics.query.query_test_support import configured_db_url

_ASTRA = "gpt-6-astra"

_REPO = "owner/r"

_WINDOW_START = datetime.fromisoformat("2026-11-01T00:00:00+00:00")

_WINDOW_END = datetime.fromisoformat("2026-11-26T00:00:00+00:00")

_STAGE_ENTER = "stage_enter"

# Rows in the order SQL ranked them: the most affected first, and a reason left unrecorded after the recorded ones.
_RANKED = (
    (_ASTRA, usage_unpriced.INDETERMINATE_REQUEST_TIER, 8),
    (_ASTRA, usage_unpriced.MISSING_CACHE_WRITE_COUNT, 8),
    (_ASTRA, None, 2),
    ("third-party-model-x", usage_unpriced.MISSING_MODEL_PRICE, 1),
)


class UnpricedReasonReadTest(unittest.TestCase):
    """The read behind the Cost details section's count of unpriced runs by model and reason."""

    def test_an_unconfigured_database_answers_empty(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_unpriced_reasons(connect=FakeConnect()), [])

    def test_no_agent_exit_selected_never_dials(self) -> None:
        for events in ([_STAGE_ENTER], []):
            with self.subTest(events=events), configured_db_url():
                self.assertEqual(get_unpriced_reasons(events=events, connect=FakeConnect()), [])

    def test_rows_come_back_as_ranked(self) -> None:
        conn = FakeConnection(rows=_RANKED)
        with configured_db_url():
            rows = get_unpriced_reasons(connect=conn.as_connect)
        self.assertEqual(rows, [UnpricedReasonRow(*ranked) for ranked in _RANKED])

    def test_the_scan_counts_every_selected_run(self) -> None:
        # The unpriced condition binds ahead of the window predicate and the
        # reason vocabulary after it; the event selection is dropped in favour
        # of the pinned `agent_exit`, and no cap stands between the count and
        # the runs it covers.
        conn = FakeConnection()
        with configured_db_url():
            get_unpriced_reasons(
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                events=["agent_exit", _STAGE_ENTER],
                connect=conn.as_connect,
            )
        scan_sql, bindings = conn.executed[0]
        assert_sql_fragments(
            self,
            scan_sql,
            (
                "FROM analytics_events WHERE event = 'agent_exit' AND cost_completeness = %s",
                "extras->'unpriced_reasons'",
                "COUNT(DISTINCT id)",
                "jsonb_array_elements_text",
            ),
        )
        for absent in ("LIMIT", "analytics_daily_rollup", "analytics_agent_runs", "event IN ("):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, scan_sql)
        expected = (usage_cost.INCOMPLETE, _WINDOW_START, _WINDOW_END, _REPO, *usage_unpriced.REASONS)
        self.assertEqual(bindings, expected)


if __name__ == "__main__":
    unittest.main()
