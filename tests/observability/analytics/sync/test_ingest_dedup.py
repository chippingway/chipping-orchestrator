# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a record the database already holds costs before it reaches the wire."""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.sync import records
from tests.observability.analytics.sync.sync_fake_driver import (
    FakeConnection,
    seed_stored_records,
)
from tests.observability.analytics.sync.sync_test_support import (
    jsonl_log,
    run_sync,
    sample_record,
    sample_records,
)

_RECORD_COUNT = 3


def _select_sqls(connection: FakeConnection) -> list[str]:
    """The startup scans the run issued, without the statements around them."""
    return [
        sql
        for sql, _ in connection.select_calls
        if sql.lstrip().upper().startswith("SELECT")
    ]


class PreCheckTest(unittest.TestCase):
    """One scan of the unique `content_hash` index answers for the whole file:
    a record the database already holds is skipped before it costs a
    round-trip, and a hash queued earlier in the same file joins the set the
    lines after it are measured against.
    """

    def test_one_scan_answers_for_the_file(self) -> None:
        # Fan-out per row would defeat the point of reading the index once.
        with jsonl_log(sample_records(_RECORD_COUNT)) as path:
            fake = FakeConnection()
            run_sync(path, fake)
        select_sqls = _select_sqls(fake)
        self.assertEqual(len(select_sqls), 1)
        self.assertIn("SELECT content_hash", select_sqls[0])
        self.assertIn("analytics_events", select_sqls[0])

    def test_stored_hashes_skip_before_the_batch(self) -> None:
        written = sample_records(_RECORD_COUNT)
        with jsonl_log(written) as path:
            fake = FakeConnection()
            seed_stored_records(fake, written[:-1])
            sync_result = run_sync(path, fake)
        self.assertEqual(sync_result.inserted, 1)
        self.assertEqual(sync_result.skipped_duplicate, _RECORD_COUNT - 1)
        self.assertEqual(sync_result.total_lines, len(written))
        # Only the one new record enters the buffer; the pre-skipped rows never
        # reach the wire at all.
        self.assertEqual(len(fake.batches), 1)
        batched_hashes = {row[-1] for row in fake.batches[0][1]}
        self.assertEqual(batched_hashes, {records.content_hash(written[-1])})

    def test_repeated_lines_dedupe_against_each_other(self) -> None:
        # Two identical lines in one file share a hash: the first is queued and
        # adds it to the skip set, so the wire only ever sees one copy.
        repeated = sample_record(issue=1)
        with jsonl_log([repeated, repeated, sample_record(issue=2)]) as path:
            fake = FakeConnection()
            sync_result = run_sync(path, fake)
        self.assertEqual(sync_result.inserted, 2)
        self.assertEqual(sync_result.skipped_duplicate, 1)
        self.assertEqual(sync_result.total_lines, _RECORD_COUNT)
        batched_hashes = [row[-1] for row in fake.batches[0][1]]
        self.assertEqual(len(set(batched_hashes)), len(batched_hashes))

    def test_an_empty_database_pays_the_same_scan(self) -> None:
        written = sample_records(_RECORD_COUNT)
        with jsonl_log(written) as path:
            fake = FakeConnection()
            sync_result = run_sync(path, fake)
        self.assertEqual(len(_select_sqls(fake)), 1)
        self.assertEqual(sync_result.inserted, len(written))
        self.assertEqual(sync_result.skipped_duplicate, 0)


if __name__ == "__main__":
    unittest.main()
