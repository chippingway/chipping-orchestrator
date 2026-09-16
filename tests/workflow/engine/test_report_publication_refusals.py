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

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.support.fakes import FakePR
from tests.workflow.engine import report_transaction_test_support as support

_FETCH_REFUSED = 128

# The two ways a pull request is over, paired with the attribute each one
# is read off. Both retire the transaction rather than holding one for work
# nobody is going to read a report on.
_ENDED = (("merged", True), ("state", "closed"))


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

    def test_repository_casing_is_not_a_difference(self) -> None:
        # Owner and repository names are case-insensitive on GitHub, so a
        # record spelled with different casing names the same repository.
        # Compared exactly it would defer forever over a difference GitHub
        # does not have.
        _record_state.record_pending_report(self.state, self.pending(
            subject=_records.ReportSubject(
                repo_slug=self.gh.repo_slug.upper(),
                pr_number=support.PR_NUMBER,
                branch=support.BRANCH,
                source_sha=support.SOURCE_SHA,
                requirements_revision=self.requirements(),
            ),
        ))

        self.assertFalse(self.reconcile())

        self.assertEqual(len(support.report_comments(self)), 1)
        self.assertIsNone(_record_state.read_pending_report(self.state))

    def _unpublish(self) -> None:
        """Leave the recorded commit on no pull request at all."""
        self.pull_request.commit_shas = ()
        self.pull_request.head.sha = support.MOVED_SHA


class PullRequestIdentityTest(unittest.TestCase, support.ReportTransactionCase):
    """The pull request has to be the recorded one, and still on the commit."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_moved_pull_request_head_stands_down(self) -> None:
        # Carrying the commit is what FOUND the pull request; it is not enough
        # to settle on. A head pushed past the recorded commit leaves that
        # commit in history while the work under review is no longer the work
        # the report describes.
        self.pull_request.head.sha = support.MOVED_SHA

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_a_finished_pull_request_retires_it(self) -> None:
        # A report posted onto a merged thread is a comment nobody reads, and
        # holding one for it forever would strand the issue on work that is
        # over.
        self.pull_request.merged = True

        self.assertFalse(self.reconcile())

        self._assert_retired()

    def test_an_ending_retires_past_failed_reads(self) -> None:
        # The case the ordering exists for. A merge auto-deletes its branch, so
        # the fetch fails and the worktree may be gone with it -- and this guard
        # runs AHEAD of the stage terminal that drains an ended pull request.
        # Any refusal taken before the pull request is read would hold the tick
        # in front of that terminal, and the issue would never finalize.
        for ending, over in _ENDED:
            with self.subTest(ending=ending):
                self.setUp()
                setattr(self.pull_request, ending, over)
                self.checkout.status = _WorktreeStatus(readable=False)
                self.checkout.fetched = _FETCH_REFUSED

                self.assertFalse(self.reconcile())

                self._assert_retired()

    def _assert_retired(self) -> None:
        """Nothing published, nothing owed, and the tick left to the terminal."""
        self.assertEqual(support.report_comments(self), [])
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))


if __name__ == "__main__":
    unittest.main()
