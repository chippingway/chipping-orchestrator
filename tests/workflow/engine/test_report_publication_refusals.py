# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pull request and the publication receipt refuse a report over.

A report is a claim about work this orchestrator published, so two things have
to be true before one is posted: the pull request the record names is the one
that carries the commit and is still open, and the code-publication receipt
vouches for that commit having reached that pull request. Carrying the commit
says it is THERE and nothing about how it got there, which is why the receipt is
asked beside it rather than instead of it.

Every refusal here stands down rather than holding, except the one nobody could
read. What would clear each of them is a route BEHIND this guard -- the
publication gate that pushes the commit, the drift resume that answers an edited
issue -- so holding would strand the issue in front of its own remedy.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.support.fakes import FakePR
from tests.workflow.engine import report_transaction_test_support as support


class PublicationRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """A pull request that is not the recorded one completes nothing."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_an_unpublished_commit_stands_down(self) -> None:
        # The publication gate behind this guard is what pushes it, so holding
        # here would strand the issue in front of its own remedy.
        self._unpublish()

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_another_pull_request_stands_down(self) -> None:
        # A replacement somebody opened after closing the original carries the
        # commit just as well, and is not the publication this report is about.
        self._unpublish()
        self.gh.add_pr(FakePR(
            number=support.OTHER_PR_NUMBER,
            head_branch=support.BRANCH,
            commit_shas=(support.SOURCE_SHA,),
        ))

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_unreadable_lookup_holds(self) -> None:
        # "No pull request carries this" and "nobody could say" are different
        # answers, and only the first means the commit still needs publishing.
        self.gh.unreadable_pr_lookups.add(support.BRANCH)

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_another_repository_stands_down(self) -> None:
        _record_state.record_pending_report(self.state, self.pending(
            subject=_records.ReportSubject(
                repo_slug="someone/else",
                pr_number=support.PR_NUMBER,
                branch=support.BRANCH,
                source_sha=support.SOURCE_SHA,
                requirements_revision=self.requirements(),
            ),
        ))

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_a_finished_pull_request_retires_it(self) -> None:
        # A report posted onto a merged thread is a comment nobody reads, and
        # holding one for it forever would strand the issue on work that is
        # over.
        self.pull_request.merged = True

        self.assertFalse(self.reconcile())

        self.assertEqual(support.report_comments(self), [])
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))

    def _unpublish(self) -> None:
        """Leave the recorded commit on no pull request at all."""
        self.pull_request.commit_shas = ()
        self.pull_request.head.sha = support.MOVED_SHA


class ReceiptRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """Completion needs confirmed repository publication, not just a commit."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_no_publication_receipt_stands_down(self) -> None:
        self.state.set(support.PUBLISHED_SHA, None)

        self.assertFalse(self.reconcile())
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
