# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pull request a report names answers that report with.

Four things have to be true before one is published: the pull request the record
NAMES is open, in this repository, on the recorded branch, and standing on the
recorded commit. Standing on it is strictly more than carrying it -- a human
pushing to the branch, a rebase, or a squash moves the head while the commit
stays in the thread's history, and the work under review is then no longer the
work the report describes.

The pull request is selected by its number rather than searched for by the
commit, and one case here is the whole reason: a branch can carry several pull
requests standing on one commit, and a search answering with whichever it
reached first would refuse this transaction for the rest of the issue's life.

Every refusal here defers rather than holding, except the one nobody could read
and the one where the work is over. What would clear each of the rest is a route
behind this evidence, so holding would strand the issue in front of its own
remedy; and a thread that has merged or closed needs no report at all, so it
ENDS instead of waiting for one it will never be owed.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from tests.support.fakes import FakePR, FakePRRef, LazyPullRequest
from tests.workflow.engine import report_evidence_test_support as support

# The two reads the CLIENT takes that a lazy repository can refuse, named by the
# owner each is read off. `is_own_repository` can complete the repository and
# `get_pr` is the lookup itself.
_LAZY_CLIENT_READS = ("is_own_repository", "get_pr")

# The reads taken off the pull request that came back, which are requests of
# their own on a worker that has not completed the object: the state `pr_state`
# is derived from, and the head every identity below is read off.
_LAZY_PR_READS = ("state", "head")

# The two ways a pull request is over, paired with the attribute each one is
# read off. Both retire the transaction rather than leaving one owed to work
# nobody is going to read a report on.
_ENDED = (("merged", True), ("state", "closed"))


class ProvedPublicationTest(unittest.TestCase, support.ReportEvidenceCase):
    """The world a transaction is recorded in proves, and carries its thread."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_the_recorded_world_proves(self) -> None:
        # The control every refusal beside this is read against: without it a
        # DEFER could as easily be the fixture as the thing a case moved.
        proved = self.evidence()

        self.assertEqual(proved.verdict, support.PROVED)
        # The pull request travels on the verdict because the next step is a
        # request: re-fetching would be a second moment, and a thread somebody
        # closes between them would be proved open and written to closed.
        self.assertIs(proved.pull_request, self.pull_request)


class PublicationIdentityTest(unittest.TestCase, support.ReportEvidenceCase):
    """The pull request has to be the recorded one, and still on the commit."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_another_repository_defers(self) -> None:
        # A fork carries this repository's ref names over its commits, so every
        # reading below would otherwise be taken against somebody else's thread.
        owed = self.pending(subject=self.subject(repo_slug="someone/else"))

        self.assertEqual(self.publication(owed).verdict, support.DEFER)

    def test_repository_casing_is_not_a_difference(self) -> None:
        # Owner and repository names are case-insensitive on GitHub, so a
        # record spelled with different casing names the same repository.
        # Compared exactly it would defer forever over a difference GitHub
        # does not have.
        owed = self.pending(
            subject=self.subject(repo_slug=self.gh.repo_slug.upper()),
        )

        self.assertEqual(self.publication(owed).verdict, support.PROVED)

    def test_another_branch_defers(self) -> None:
        # A head ref cannot move on GitHub, so a disagreement is a record
        # naming a number and a branch that never went together.
        self.pull_request.head.ref = f"{support.BRANCH}-elsewhere"

        self.assertEqual(self.publication().verdict, support.DEFER)

    def test_a_forked_head_defers(self) -> None:
        # A fork carries this repository's ref names over somebody else's
        # commits, so the branch and the head sha can both agree while the work
        # is not in this repository at all.
        self.pull_request.head.repo.full_name = "someone/else"

        self.assertEqual(self.publication().verdict, support.DEFER)

    def test_a_moved_pull_request_head_defers(self) -> None:
        # Carrying the commit is not enough to publish on. A head pushed past
        # the recorded commit leaves that commit in history while the work
        # under review is no longer the work the report describes.
        self.pull_request.head.sha = support.MOVED_SHA

        self.assertEqual(self.publication().verdict, support.DEFER)


class PullRequestSelectionTest(unittest.TestCase, support.ReportEvidenceCase):
    """The pull request proved is the one the record names, and no other."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_the_recorded_number_selects_the_thread(self) -> None:
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

        proved = self.publication()

        self.assertEqual(proved.verdict, support.PROVED)
        self.assertIs(proved.pull_request, self.pull_request)

    def test_a_client_read_that_did_not_happen_holds(self) -> None:
        # "The pull request is not what the record says" and "nobody could say"
        # are different answers, and only the first may be acted on: read the
        # other way round, a transient failure would retire a transaction over
        # a thread nobody managed to look at.
        for read in _LAZY_CLIENT_READS:
            with self.subTest(read=read), patch.object(
                self.gh, read, side_effect=RuntimeError(support.REFUSED),
            ):
                self.assertEqual(self.publication().verdict, support.HOLD)

    def test_a_lazy_member_that_did_not_happen_holds(self) -> None:
        # Every read of this reading is inside that boundary and not just the
        # lookup. PyGithub hands back a lazy object, so the state and the head
        # are each a request that can fail -- and left outside, either one
        # leaves this evidence by an exception rather than by a verdict.
        for read in _LAZY_PR_READS:
            with self.subTest(read=read):
                self.setUp()
                self.gh.add_pr(
                    LazyPullRequest(self.pull_request, failing=read),
                )

                self.assertEqual(self.publication().verdict, support.HOLD)


class EndedPullRequestTest(unittest.TestCase, support.ReportEvidenceCase):
    """Work that is over ends the reading whatever the rest of it says."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_a_finished_pull_request_ends_the_reading(self) -> None:
        # A report posted onto a merged thread is a comment nobody reads, and
        # waiting for one forever would strand the issue on work that is over.
        for ending, over in _ENDED:
            with self.subTest(ending=ending):
                self.setUp()
                setattr(self.pull_request, ending, over)

                self.assertEqual(self.publication().verdict, support.ENDED)

    def test_an_ending_is_read_before_the_local_world(self) -> None:
        # The case the ordering exists for. A merge auto-deletes its branch, so
        # the fetch fails and the worktree may be gone with it -- and this
        # evidence runs AHEAD of the stage terminal that drains an ended pull
        # request. Any refusal taken before the pull request is read would hold
        # the tick in front of that terminal, and the issue would never
        # finalize.
        for ending, over in _ENDED:
            with self.subTest(ending=ending):
                self.setUp()
                setattr(self.pull_request, ending, over)
                self.checkout.status = _WorktreeStatus(readable=False)
                self.checkout.fetched = support.FETCH_REFUSED

                self.assertEqual(self.evidence().verdict, support.ENDED)

    def test_an_ended_moved_pull_request_still_ends(self) -> None:
        # A search by commit cannot see a thread somebody force-pushed off it,
        # open or closed. Left to that search's refusal an ended one would
        # defer on every tick for the rest of the issue's life over work that
        # is finished -- so the ending is asked of the recorded NUMBER, which
        # is the one thing a moved head cannot take away.
        for ending, over in _ENDED:
            with self.subTest(ending=ending):
                self.setUp()
                self.pull_request.commit_shas = ()
                self.pull_request.head.sha = support.MOVED_SHA
                setattr(self.pull_request, ending, over)

                self.assertEqual(self.publication().verdict, support.ENDED)


if __name__ == "__main__":
    unittest.main()
