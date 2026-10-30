# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one replay leaves behind on the connection it was handed."""
from __future__ import annotations

import unittest
from datetime import datetime

from orchestrator.observability.analytics.sync import columns
from tests.observability.analytics.sync.sync_fake_driver import FakeConnection
from tests.observability.analytics.sync.sync_test_support import (
    AGENT_EXIT,
    jsonl_log,
    run_sync,
    sample_record,
)

_CONTENT_HASH_HEX_LEN = 64

_FIRST_LINE = 1

_FUTURE_KEY = "custom_future_key"

_FUTURE_VALUE = "something-new"

_SAMPLE_DURATION_S = 12.5


class InsertedRowTest(unittest.TestCase):
    """A well-formed line becomes one row carrying the promoted columns, the
    extras the table has no column for, and the provenance only the run knows:
    where the line came from and the hash the arbiter deduplicates it on.
    """

    def test_each_record_lands_once(self) -> None:
        written = [
            sample_record(issue=1, stage="implementing"),
            sample_record(issue=2, event=AGENT_EXIT, duration_s=_SAMPLE_DURATION_S),
        ]
        with jsonl_log(written) as path:
            fake = FakeConnection()
            sync_result = run_sync(path, fake)
        self.assertEqual(sync_result.inserted, len(written))
        self.assertEqual(sync_result.skipped_duplicate, 0)
        self.assertEqual(sync_result.skipped_malformed, 0)
        self.assertEqual(sync_result.total_lines, len(written))
        self.assertEqual(len(fake.inserts), len(written))
        # Two commits -- the events insert and the rollup refresh behind it --
        # over one connection that is closed exactly once.
        self.assertEqual(fake.commit_called, 2)
        self.assertEqual(fake.rollback_called, 0)
        self.assertEqual(fake.close_called, 1)

    def test_the_row_carries_its_source_and_extras(self) -> None:
        record = sample_record(event=AGENT_EXIT, backend="claude", **{_FUTURE_KEY: _FUTURE_VALUE})
        with jsonl_log([record]) as path:
            fake = FakeConnection()
            run_sync(path, fake)
            _, row_values = fake.inserts[0]
            tail = row_values[len(columns.TABLE_COLUMNS):]
            self.assertEqual(row_values[columns.TABLE_COLUMNS.index("backend")], "claude")
            self.assertEqual(tail[0], {_FUTURE_KEY: _FUTURE_VALUE})
            self.assertEqual(tail[1:3], (str(path), _FIRST_LINE))
            self.assertEqual(len(tail[3]), _CONTENT_HASH_HEX_LEN)

    def test_the_timestamp_reaches_the_driver_typed(self) -> None:
        # `ts` is TIMESTAMPTZ and psycopg expects a datetime; a string would be
        # inserted as text under some configurations rather than refused.
        with jsonl_log([sample_record()]) as path:
            fake = FakeConnection()
            run_sync(path, fake)
            _, row_values = fake.inserts[0]
        ts_cell = row_values[columns.PROMOTED_COLUMNS.index("ts")]
        self.assertIsInstance(ts_cell, datetime)
        self.assertIsNotNone(ts_cell.tzinfo)


class TransactionTest(unittest.TestCase):
    """A driver error mid-stream rolls the transaction back and propagates, so
    the CLI exits non-zero rather than reporting success over a half-inserted
    batch -- and the connection is closed either way.
    """

    def test_a_driver_error_rolls_back_and_propagates(self) -> None:
        with jsonl_log([sample_record()]) as path:
            fake = FakeConnection()
            fake.raise_on_executemany = RuntimeError("simulated driver failure")
            with self.assertRaises(RuntimeError):
                run_sync(path, fake)
        self.assertEqual(fake.commit_called, 0)
        self.assertEqual(fake.rollback_called, 1)
        self.assertEqual(fake.close_called, 1)


if __name__ == "__main__":
    unittest.main()
