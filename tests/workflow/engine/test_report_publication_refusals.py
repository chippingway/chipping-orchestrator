# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pull request and the publication receipt refuse a report over.

A report is a claim about work this orchestrator published, so two things have
to be true before one is posted: the pull request the record NAMES is open in
this repository, on the recorded branch, and standing on the recorded commit;
and the code-publication receipt vouches for that commit having reached that
pull request. Standing on the commit says it is THERE and nothing about how it
got there, which is why the receipt is asked beside it rather than instead of
it.

The pull request is selected by its number rather than searched for by the
commit, and one case here is the whole reason: a branch can carry several pull
requests standing on one commit, and a search answering with whichever it
reached first would refuse this transaction for the rest of the issue's life.

Every refusal here stands down rather than holding, except the one nobody could
read. What would clear each of them is a route BEHIND this guard -- the
publication gate that pushes the commit, the drift resume that answers an edited
issue -- so holding would strand the issue in front of its own remedy.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.engine import report_transaction_test_support as support

_FETCH_REFUSED = 128

# What a pull request read GitHub would not answer raises.
_REFUSED = "GitHub did not answer the read"

# Every read the pull-request evidence takes that a lazy client can refuse,
# named by the owner the call site reads it off. `is_own_repository` can
# complete the repository, `get_pr` is the fetch itself, and `pr_state` stands
# for the members read off the object that comes back.
_LAZY_READS = (
    ("is_own_repository", lambda case: case.gh),
    ("get_pr", lambda case: case.gh),
    ("pr_state", lambda _case: _pr_reads),
)

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


class PullRequestSelectionTest(unittest.TestCase, support.ReportTransactionCase):
    """The pull request proved is the one the record names, and no other."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_another_pull_request_is_not_selected(self) -> None:
        # Several pull requests can stand on one branch carrying one commit --
        # a replacement opened beside the original, a second thread raised
        # against another base. A search answering with whichever it reached
        # first would refuse this transaction forever while the pull request
        # the record NAMES sits open on the very commit the report is about.
        ahead = FakePR(
            number=support.OTHER_PR_NUMBER,
            head_branch=support.BRANCH,
            head=FakePRRef(sha=support.SOURCE_SHA),
            commit_shas=(support.SOURCE_SHA,),
        )
        # Held AHEAD of the recorded pull request, since what a search by
        # commit answers with is whichever it reaches first.
        self.gh.pulls.clear()
        self.gh.add_pr(ahead)
        self.gh.add_pr(self.pull_request)

        self.assertFalse(self.reconcile())

        support.assert_one_report(self)
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertEqual(
            _settlement.read_current_report(self.state).subject.pr_number,
            support.PR_NUMBER,
        )

    def test_a_read_that_did_not_happen_holds(self) -> None:
        # "The pull request is not what the record says" and "nobody could say"
        # are different answers, and only the first may be acted on: read the
        # other way round, a transient failure would retire a transaction over
        # a thread nobody managed to look at.
        #
        # Every read of this reading is inside that boundary and not just the
        # fetch. The client resolves its repository lazily, and the members
        # read off a pull request are lazy too, so on a worker that has not
        # completed the object each of them is a request that can fail. Left
        # outside, any one of them leaves the guard by an exception rather than
        # by a verdict -- through the dispatcher and out of the tick.
        for read, owner in _LAZY_READS:
            with self.subTest(read=read):
                self.setUp()

                with patch.object(
                    owner(self), read, side_effect=RuntimeError(_REFUSED),
                ):
                    self.assertTrue(self.reconcile())

                support.assert_still_owed(self)

    def test_another_branch_stands_down(self) -> None:
        # A head ref cannot move on GitHub, so a disagreement is a record
        # naming a number and a branch that never went together.
        self.pull_request.head.ref = f"{support.BRANCH}-elsewhere"

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_a_forked_head_stands_down(self) -> None:
        # A fork carries this repository's ref names over somebody else's
        # commits, so the branch and the head sha can both agree while the work
        # is not in this repository at all.
        self.pull_request.head.repo.full_name = "someone/else"

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)


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

    def test_an_ended_moved_pull_request_retires(self) -> None:
        # The lookup finds a pull request BY the commit, so a recorded thread
        # somebody force-pushed off it is invisible to that search whether it
        # is open or closed. Left to the search's own refusal, an ended one
        # would stand down on every tick for the rest of the issue's life over
        # work that is finished -- so the ending is asked of the recorded
        # NUMBER, which is the one thing a moved head cannot take away.
        for ending, over in _ENDED:
            with self.subTest(ending=ending):
                self.setUp()
                self.pull_request.commit_shas = ()
                self.pull_request.head.sha = support.MOVED_SHA
                setattr(self.pull_request, ending, over)

                self.assertFalse(self.reconcile())

                self._assert_retired()

    def _assert_retired(self) -> None:
        """Nothing published, nothing owed, and the tick left to the terminal."""
        self.assertEqual(support.report_comments(self), [])
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))


if __name__ == "__main__":
    unittest.main()
