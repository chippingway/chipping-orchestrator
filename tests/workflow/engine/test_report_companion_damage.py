# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a damaged settled record, or another route's park, does to a transaction.

The current report and the handoff are both things a settlement WRITES OVER, so
reading a damaged one as an absence is worse than reading no record at all: the
next transaction replaces it the moment it settles -- after its report has been
posted, which is when the evidence an operator would have repaired it from is
gone. Both are therefore asked for their presence before anything is proved.

The park is the mirror of the same care. The pinned flags are single, so a park
this owner takes over one another route already holds replaces an obligation a
stage is still waiting on -- and the retirement behind this owner would then
clear `awaiting_human` for a question nobody answered. Standing down costs
nothing: the issue is already held awaiting a human, which is what this park
would have asked for.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.workflow.engine import report_transaction_test_support as support

_AGENT_TIMEOUT = "agent_timeout"


class CompanionDamageTest(unittest.TestCase, support.ReportTransactionCase):
    """A settled record that is claimed and unreadable stops the tick."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_damaged_current_report_is_preserved(self) -> None:
        # Read as an absence it would be silently replaced by this settlement,
        # after the report had already been posted.
        unreadable = {"revision": 1}
        self.state.set(_records.CURRENT_REPORT, unreadable)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(_records.CURRENT_REPORT), unreadable)
        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)

    def test_a_damaged_handoff_is_preserved(self) -> None:
        # Read as an absence it would be a completed transaction nobody can
        # recognize, and its report would be published a second time.
        damaged = {"receipt": support.RECEIPT}
        self.state.set(_records.REPORT_HANDOFF, damaged)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(_records.REPORT_HANDOFF), damaged)
        support.assert_nothing_published(self)

    def test_a_handoff_with_no_current_report_parks(self) -> None:
        # The two are written in ONE write, so a handoff without a current
        # report is a settlement that never happened. Believed on the receipt
        # alone it would drop this record while the pull request carries
        # nothing -- the outcome the whole transaction exists to prevent.
        _settlement.record_handoff(self.state, _records.ReportHandoff(
            receipt=support.RECEIPT,
            pr_number=support.PR_NUMBER,
            report_revision=1,
            source_sha=support.SOURCE_SHA,
        ))

        self.assertTrue(self.reconcile())

        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)


class ForeignParkTest(unittest.TestCase, support.ReportTransactionCase):
    """A park another route took is never replaced by this owner's."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_foreign_park_is_not_overwritten(self) -> None:
        # Overwritten, the stage waiting on `agent_timeout` loses its
        # obligation -- and the retirement behind this owner would then clear
        # `awaiting_human` for a question nobody answered.
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, _AGENT_TIMEOUT)
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
        posted = len(self.gh.posted_comments)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(support.PARK_REASON), _AGENT_TIMEOUT)
        self.assertTrue(self.state.get(support.AWAITING_HUMAN))
        self.assertEqual(len(self.gh.posted_comments), posted)
        self.assertTrue(_record_state.carries_pending_report(self.state))


if __name__ == "__main__":
    unittest.main()
