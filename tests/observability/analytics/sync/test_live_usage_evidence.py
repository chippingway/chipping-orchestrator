# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the stored usage evidence reduces to, against a real Postgres.

The hermetic tests hold the sync's cells and the reader's arithmetic to the Python readers; only a real database can
say whether the schema's view and rollup, and the read model's fragments over them, compute what those tests assume.
Each cohort here is read three ways -- off the agent-run view, off the events table, and off the daily rollup -- and
all three have to agree with what `usage.cost_evidence.reduce_costs` folds the same records' costs to, through a
replay, its replay, and a row an earlier sync stored before the evidence columns existed.
"""
from __future__ import annotations

import unittest

from tests.observability.analytics.sync import live_evidence_support as live


class LiveUsageEvidenceTest(unittest.TestCase):
    """Opted into with `ANALYTICS_TEST_DB_URL=<libpq URL>` naming a disposable database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database = live.LiveDatabase.from_environment()

    def setUp(self) -> None:
        self.database.reset()

    def test_three_scans_agree_with_the_fold(self) -> None:
        written, replay = self.database.replay_twice()
        self.assertEqual((replay.inserted, replay.skipped_duplicate), (0, written))
        for issue, cohort in live.COHORTS:
            with self.subTest(issue=issue):
                self.assertEqual(
                    self.database.scan_answers(issue),
                    dict.fromkeys(live.SCAN_TARGETS, live.folded_answer(cohort)),
                )

    def test_an_underived_row_reads_unknown(self) -> None:
        # An earlier sync stored the row with none of the evidence columns: its
        # amount is kept under the `unknown` basis and its total is unknown,
        # whatever its source says.
        self.database.execute(live.UNDERIVED_ROWS)
        self.assertEqual(
            self.database.scan_answers(live.UNDERIVED_ISSUE),
            dict.fromkeys(live.SCAN_TARGETS, live.underived_answer()),
        )

    def test_token_reads_count_each_token_once(self) -> None:
        self.assertEqual(self.database.provider_token_answers(), live.PROVIDER_TOKEN_ANSWERS)


if __name__ == "__main__":
    unittest.main()
