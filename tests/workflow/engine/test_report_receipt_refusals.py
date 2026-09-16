# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the code-publication receipt refuses a report over.

A report is a claim about work this orchestrator published, and the pull request
carrying the commit says it is THERE and nothing about how it got there. So the
receipt is asked beside it -- as one GROUP first, because `_record_publication`
writes all three members on every receipt and clears all three on none, and read
member by member a partial group answers "no receipt" and would defer forever
instead of naming the field a human has to repair.

A wholly absent receipt is not damage: it is an issue that has published nothing
yet, and what it waits for is the publication gate behind this guard.

The requirements the run was handed are proved on the same road and close it, so
the reading that computes them is here too. It walks the issue's comments, which
is a request -- and one that raised would leave this guard by an exception
rather than by a verdict, so it holds like every other missing read.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_record_state as _record_state,
)
from tests.workflow.engine import report_transaction_test_support as support

# What a read GitHub would not answer raises.
_REFUSED = "GitHub did not answer the read"


class ReceiptRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """Completion needs confirmed repository publication, not just a commit."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_wholly_absent_receipt_stands_down(self) -> None:
        # An issue that has published nothing has nothing to be partial
        # about; what it is waiting for is the publication gate behind this
        # guard.
        for member in (
            support.PUBLISHED_SHA, support.PUBLISHED_PR, support.PUBLISHED_LEASE,
        ):
            self.state.data.pop(member, None)

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_a_partial_receipt_holds(self) -> None:
        # `_record_publication` writes all three members on every receipt, so
        # a group claiming a pull request with no commit beside it is one
        # nothing here produced -- and read member by member it would answer
        # "no receipt" and defer forever instead of naming what to repair.
        self.state.set(support.PUBLISHED_SHA, None)

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_receipt_elsewhere_stands_down(self) -> None:
        self.state.set(support.PUBLISHED_PR, support.OTHER_PR_NUMBER)

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_edited_requirements_stand_down(self) -> None:
        # Publishing now would put a report answering the old requirements onto
        # the pull request stamped with the revision it was written against.
        self.issue.body = "the human rewrote the requirements"

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_unreadable_requirements_read_holds(self) -> None:
        # Computing the revision walks the issue's comments, which is a request
        # like every other reading here. Raised, it would leave the guard by an
        # exception rather than by a verdict -- through the dispatcher and out
        # of the tick -- and an edit nobody could look for is not an issue
        # whose requirements are unchanged.
        with patch.object(
            _content_hash, "_compute_user_content_hash",
            side_effect=RuntimeError(_REFUSED),
        ):
            self.assertTrue(self.reconcile())

        support.assert_still_owed(self)

    def test_an_issue_owing_nothing_costs_nothing(self) -> None:
        # A settled transaction leaves the key holding `null`, so this is also
        # every issue that has ever published a report.
        _record_state.clear_pending_report(self.state)
        writes = self.gh.write_state_calls

        self.assertFalse(self.reconcile())

        self.assertEqual(support.report_comments(self), [])
        self.assertEqual(self.gh.write_state_calls, writes)


if __name__ == "__main__":
    unittest.main()
