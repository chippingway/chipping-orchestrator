# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the code-publication receipt and the requirements answer a report with.

A report is a claim about work this orchestrator published, and a pull request
standing on the commit says it is THERE and nothing about how it got there. So
the receipt is asked beside it -- as one GROUP first, because `_record_
publication` writes all three members on every receipt and clears all three on
none, and read member by member a partial group answers "no receipt" and would
defer forever instead of naming the field a human has to repair.

A wholly absent receipt is not damage: it is an issue that has published nothing
yet, and what it waits for is the publication gate behind this evidence.

The requirements the run was handed are proved on the same road and close it, so
the reading that computes them is here too. It walks the issue's comments, which
is a request -- and one that raised would leave this evidence by an exception
rather than by a verdict, so it holds like every other missing read.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import content_hash as _content_hash
from tests.workflow.engine import report_evidence_test_support as support


class ReceiptEvidenceTest(unittest.TestCase, support.ReportEvidenceCase):
    """Proof needs a confirmed publication, not just a commit on a thread."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_a_wholly_absent_receipt_defers(self) -> None:
        # An issue that has published nothing has nothing to be partial
        # about; what it is waiting for is the publication gate behind this
        # evidence.
        for member in (
            support.PUBLISHED_SHA, support.PUBLISHED_PR, support.PUBLISHED_LEASE,
        ):
            self.state.data.pop(member, None)

        self.assertEqual(self.evidence().verdict, support.DEFER)

    def test_a_partial_receipt_holds(self) -> None:
        # `_record_publication` writes all three members on every receipt, so
        # a group claiming a pull request with no commit beside it is one
        # nothing here produced -- and read member by member it would answer
        # "no receipt" and defer forever instead of naming what to repair.
        self.state.set(support.PUBLISHED_SHA, None)

        self.assertEqual(self.evidence().verdict, support.HOLD)

    def test_a_receipt_naming_another_commit_defers(self) -> None:
        self.state.set(support.PUBLISHED_SHA, support.MOVED_SHA)

        self.assertEqual(self.evidence().verdict, support.DEFER)

    def test_a_receipt_elsewhere_defers(self) -> None:
        self.state.set(support.PUBLISHED_PR, support.OTHER_PR_NUMBER)

        self.assertEqual(self.evidence().verdict, support.DEFER)

    def test_edited_requirements_defer(self) -> None:
        # Publishing now would put a report answering the old requirements onto
        # the pull request stamped with the revision it was written against.
        # The record is frozen first, which is the shape production has: the
        # revision it carries is the one the run was handed, and the edit lands
        # while the publication is outstanding.
        owed = self.pending()
        self.issue.body = "the human rewrote the requirements"

        self.assertEqual(self.evidence(owed).verdict, support.DEFER)

    def test_an_unreadable_requirements_read_holds(self) -> None:
        # Computing the revision walks the issue's comments, which is a request
        # like every other reading here. Raised, it would leave this evidence by
        # an exception rather than by a verdict -- through the dispatcher and
        # out of the tick -- and an edit nobody could look for is not an issue
        # whose requirements are unchanged.
        owed = self.pending()

        with patch.object(
            _content_hash, "_compute_user_content_hash",
            side_effect=RuntimeError(support.REFUSED),
        ):
            self.assertEqual(self.evidence(owed).verdict, support.HOLD)


if __name__ == "__main__":
    unittest.main()
