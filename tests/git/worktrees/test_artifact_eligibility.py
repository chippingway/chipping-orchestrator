# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which discovered candidates may be reclaimed, over a real host and a double.

The three shapes a scan reports, the claims that keep a candidate whatever the
host says, and the proof each artifact has to give. Driven against real clones,
real branches, real checkouts, and a real bare remote, because what makes a
candidate eligible is what git and that remote answer about it -- a stub of
the probes would only assert the classifier's own table back, and the local
refs an agent can write are exactly what must not be able to answer here.

The issue and its pull requests are the in-memory double, so the ending and
the claims are set where a case needs them rather than reached for over the
network.
"""

from __future__ import annotations

import os
import shutil
import unittest
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.worktrees import eligibility, paths, tip_evidence as _tip_evidence
from orchestrator.git.worktrees.models import (
    BranchTip,
    ProbeAnswer,
    ProvenTip,
    RetentionReason,
)
from tests.git.worktrees import candidate_host_test_support as _candidate_host, eligibility_case as _eligibility_case
from tests.git.worktrees.artifact_test_support import (
    BASE_BRANCH,
    WIDGET_SLUG,
    _legacy_branch,
    _namespaced_branch,
)
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
    OPEN_PR_STATE,
    _candidate,
    _github,
    _pull_request,
    _reasons,
    _terminal_issue,
)
from tests.support.fakes import FakeGitHubClient

PR_NUMBER = 42
OTHER_ISSUE_NUMBER = 315
LOOSE_FILE = "left-behind.txt"
LOOSE_CONTENT = "an agent's unfinished work\n"
IGNORE_FILE = ".gitignore"
HIDDEN_FILE = "secrets.env"
HIDDEN_CONTENT = "TOKEN=an operator's own\n"
TRACKED_FILE = "tracked.txt"
TRACKED_CONTENT = "committed work\n"
# A timestamp no checkout was ever made at, so the entry git cached at
# checkout time no longer matches what it finds on disk.
STALE_STAMP = 1000000000


class ArtifactShapeTest(_eligibility_case._CandidateTestCase):
    """Each shape a scan reports is classified as itself.

    The three a candidate arrives in, and the fourth one it can have turned
    into by the time this pass runs: a branch the scan named and something
    deleted from this clone in between, which is a branch the remote may
    still be carrying.
    """

    def test_every_shape_is_eligible(self) -> None:
        # The three shapes a scan reports -- a checkout on its own, a branch
        # on its own, and an issue carrying both -- over one finished issue
        # whose work the base already holds. None of them holds anything back,
        # and the checkout-only one is proven through what its HEAD stands on
        # rather than through the branch the report leaves out.
        self.landed()
        worktree = self.checkout()

        for artifacts in self.shapes(worktree):
            with self.subTest(shape=tuple(artifacts)):
                verdict = self.classify(**artifacts)

                self.assertEqual(verdict.retentions, ())
                self.assertTrue(verdict.eligible)

    def test_every_shape_hands_over_what_it_cleared(self) -> None:
        # What an eligible verdict is worth to the teardown that spends it:
        # the exact commit each artifact was found standing on, named the way
        # a retention names its own subject. The checkout comes first because
        # that is the order it is taken down in, and a shape the report
        # leaves an artifact out of hands over nothing for it.
        tip = self.landed()
        worktree = self.checkout()
        cleared = (
            (ProvenTip(str(worktree), tip),),
            (ProvenTip(self.branch, tip),),
            (ProvenTip(str(worktree), tip), ProvenTip(self.branch, tip)),
        )

        for artifacts, proven in zip(self.shapes(worktree), cleared):
            with self.subTest(shape=tuple(artifacts)):
                self.assertEqual(self.classify(**artifacts).proven, proven)

    def test_a_branch_only_the_remote_has_is_proven(self) -> None:
        # The window between the scan naming a branch and this pass judging
        # it: something deleted it here in between, and the copy the remote
        # carries is an artifact of this issue exactly as the local one was.
        # What the verdict clears, and hands over, is the commit that copy
        # stands on -- without it the reclamation of the remote branch would
        # be a deletion nobody proved and nothing recorded.
        tip = self.landed()
        self.world.publish(self.clone, self.branch, self.branch)
        _candidate_host._branch_at(self.clone, self.branch)

        verdict = self.classify()

        self.assertTrue(verdict.eligible)
        self.assertEqual(verdict.proven, (ProvenTip(self.branch, tip),))

    def test_a_branch_only_the_remote_has_must_prove(self) -> None:
        # And it owes what any tip owes: this one is ahead of base and on no
        # pull request, so the copy left on the remote keeps the candidate.
        self.world.publish(self.clone, self.branch, self.commit())
        _candidate_host._branch_at(self.clone, self.branch)

        self.assertEqual(
            self.kept(), (RetentionReason.UNACCOUNTED_COMMITS,),
        )

    def test_every_shape_of_a_rejection_agrees(self) -> None:
        # The same three shapes over an issue whose work was published and
        # then closed without merging. Nothing about it is in the base, so
        # what releases it is the pull request carrying its commit -- and the
        # commit is a branch tip whichever artifact the report names it
        # through, so the shape a scan happens to see must not change the
        # verdict.
        self.gh.add_pr(_pull_request(PR_NUMBER, self.branch, self.commit()))
        worktree = self.checkout()

        for artifacts in self.shapes(worktree):
            with self.subTest(shape=tuple(artifacts)):
                self.assertEqual(self.classify(**artifacts).retentions, ())

    def test_a_legacy_branch_is_read_too(self) -> None:
        # An issue in flight when namespacing landed publishes under both
        # names, and each is a branch that has to prove itself: the flat one
        # here still carries work nothing accounts for.
        self.landed()
        legacy = _legacy_branch(ISSUE_NUMBER)
        self.world.commit_on(self.clone, legacy)

        verdict = self.classify(branches=(self.branch, legacy))

        self.assertEqual(
            _reasons(verdict.retentions),
            (RetentionReason.UNACCOUNTED_COMMITS,),
        )
        self.assertEqual(verdict.retentions[0].subject, legacy)


class MigratedCheckoutTest(_eligibility_case._CandidateTestCase):
    """Both checkout layouts of one issue are read, and each on its own.

    A host that was running when the slug went into the path holds two trees
    for the issue it was mid-way through: the flat one it started in and the
    per-repository one the next tick made. They are two directories with two
    HEADs and two reflogs, and a reading that covered one of them would clear
    the issue while the other stayed on disk with whatever it holds.
    """

    def both_layouts(self):
        """This issue's two checkouts, current-first, with base on their commit.

        The flat branch is pointed at the tip the namespaced one already stands
        on, since a tree may not be added on a branch another worktree holds --
        and one commit under two names is what a migration actually left.
        """
        legacy = _legacy_branch(ISSUE_NUMBER)
        tip = self.landed()
        _candidate_host._branch_at(self.clone, legacy, self.branch)
        flat = self.world.checkout_at(
            self.spec, paths._legacy_worktree_path(ISSUE_NUMBER), legacy,
        )
        return tip, (self.checkout(), flat)

    def test_both_checkout_layouts_are_proven(self) -> None:
        # Each tree is an artifact in its own right: the verdict clears both
        # or it clears neither, and it hands over the commit each was found
        # standing on, in the order a teardown takes them down in.
        tip, worktrees = self.both_layouts()

        verdict = self.classify(worktrees=worktrees)

        self.assertTrue(verdict.eligible)
        self.assertEqual(
            verdict.proven,
            tuple(ProvenTip(str(worktree), tip) for worktree in worktrees),
        )

    def test_the_flat_checkout_is_read_on_its_own(self) -> None:
        # What a reading that covered one tree would clear the issue past: the
        # flat one is carrying an agent's unfinished work while the current one
        # is spotless, and the retention names the directory to go and look in.
        _tip, worktrees = self.both_layouts()
        (worktrees[1] / LOOSE_FILE).write_text(LOOSE_CONTENT)

        verdict = self.classify(worktrees=worktrees)

        self.assertEqual(
            _reasons(verdict.retentions), (RetentionReason.WORKTREE_DIRTY,),
        )
        self.assertEqual(verdict.retentions[0].subject, str(worktrees[1]))


class RemoteGateTest(_eligibility_case._CandidateTestCase):
    """What GitHub settles before an artifact on the host is read at all."""

    def test_an_unfinished_issue_is_kept(self) -> None:
        self.landed()
        self.gh = _github(_terminal_issue(closed=False))

        self.assertEqual(self.kept(), (RetentionReason.ISSUE_OPEN,))

    def test_the_artifacts_are_not_read_at_all(self) -> None:
        # The gate settles the verdict, so the git processes a branch proof
        # costs are never spent on an issue that has not ended.
        self.landed()
        self.gh = _github(_terminal_issue(closed=False))

        with patch.object(_tip_evidence, "_local_branch_tip") as tipped:
            self.classify()
            tipped.assert_not_called()

    def test_an_issue_nobody_could_fetch_is_kept(self) -> None:
        self.landed()
        self.gh = FakeGitHubClient(issues=())

        verdict = self.classify()

        self.assertEqual(
            _reasons(verdict.retentions),
            (RetentionReason.ISSUE_UNREADABLE,),
        )
        self.assertEqual(verdict.retentions[0].subject, f"#{ISSUE_NUMBER}")

    def test_a_state_nobody_could_read_is_kept(self) -> None:
        # The recorded pull request and branch live in that comment, so an
        # unreadable state read as an empty one goes looking for neither.
        self.landed()

        with patch.object(
            self.gh, "read_pinned_state", side_effect=RuntimeError("no"),
        ):
            self.assertEqual(
                self.kept(), (RetentionReason.STATE_UNREADABLE,),
            )

    def test_an_open_request_keeps_it_until_it_ends(self) -> None:
        tip = self.landed()
        self.gh.existing_open_pr[self.branch] = _pull_request(
            PR_NUMBER, self.branch, tip, state=OPEN_PR_STATE,
        )

        self.assertEqual(self.kept(), (RetentionReason.OPEN_PULL_REQUEST,))

        self.gh.existing_open_pr.clear()

        self.assertTrue(self.classify().eligible)


class CheckoutStateTest(_eligibility_case._CandidateTestCase):
    """What the checkout itself has to be before it may be removed."""

    def test_what_the_checkout_carries_keeps_it(self) -> None:
        # Two reads because git draws the line between them. A path the
        # repository's own rules hide is not what it calls dirty and not what
        # a removal refuses over, so a tree carrying only that answers clean
        # to every status -- and is still an `.env` somebody left there. They
        # are charged apart for what an operator is sent to look at: `git
        # status` shows them nothing about the first.
        _candidate_host._track_file(self.clone, IGNORE_FILE, f"{HIDDEN_FILE}\n")
        self.landed()
        worktree = self.checkout()
        (worktree / HIDDEN_FILE).write_text(HIDDEN_CONTENT)

        hiding = self.classify(worktree=worktree)

        self.assertEqual(
            _reasons(hiding.retentions), (RetentionReason.WORKTREE_IGNORED,),
        )
        self.assertEqual(hiding.retentions[0].subject, str(worktree))
        # And it hands over nothing: what a retention establishes is that
        # these commits stay, so a proof beside it would be a permission
        # nothing here gave.
        self.assertEqual(hiding.proven, ())

        (worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        self.assertEqual(
            self.kept(worktree=worktree), (RetentionReason.WORKTREE_DIRTY,),
        )

    def test_a_checkout_that_is_not_ours_keeps_it(self) -> None:
        # A repository of somebody else's at the path this issue's checkout
        # belongs at, which every reading short of the shared object store
        # would take for the checkout.
        self.landed()

        self.assertEqual(
            self.kept(worktree=_candidate_host._foreign_checkout(self.spec, ISSUE_NUMBER)),
            (RetentionReason.FOREIGN_CHECKOUT,),
        )

    def test_a_checkout_nobody_could_read_keeps_it(self) -> None:
        # Not established to be ours and not established to be anybody
        # else's, which is a third answer rather than either of the first two.
        self.landed()
        worktree = paths._worktree_path(self.spec, ISSUE_NUMBER)
        worktree.mkdir(parents=True)

        self.assertEqual(
            self.kept(worktree=worktree),
            (RetentionReason.CHECKOUT_UNREADABLE,),
        )

    def test_the_checkout_index_is_not_written(self) -> None:
        # A classification reads and decides and leaves nothing behind, and
        # the status probe is the one read that would break that: git
        # refreshes the index as it reports and writes the new stat data back
        # unless it is told not to. The file is re-stamped first so there IS
        # something to refresh -- with nothing stale, a probe that writes and
        # one that does not leave the same index.
        _candidate_host._track_file(self.clone, TRACKED_FILE, TRACKED_CONTENT)
        self.landed()
        worktree = self.checkout()
        os.utime(worktree / TRACKED_FILE, (STALE_STAMP, STALE_STAMP))
        index = _candidate_host._index_path(worktree)
        before = index.read_bytes()

        self.assertTrue(self.classify(worktree=worktree).eligible)

        self.assertEqual(index.read_bytes(), before)

    def test_a_checkout_with_no_ref_is_kept(self) -> None:
        # A branch deleted out from under a live checkout, which git permits
        # through `update-ref`. Every other reading comes back saying this is
        # the issue's own checkout and that it is carrying nothing loose --
        # and the commit it stands on is held by its HEAD and its reflog
        # alone, so removing it is what would take that commit.
        self.commit()
        worktree = self.checkout()
        _candidate_host._branch_at(self.clone, self.branch)

        self.assertEqual(
            self.kept(worktree=worktree),
            (RetentionReason.CHECKOUT_UNREADABLE,),
        )

    def test_a_checkout_ahead_of_base_is_kept(self) -> None:
        # The checkout owes the proof a branch owes: no branch is reported
        # here, so nothing else is holding the commit. What the reason names
        # is the branch HEAD is on, because that is what the commit is a tip
        # of and what an operator would go and look at -- the candidate the
        # verdict is about carries the checkout path already.
        self.commit()
        worktree = self.checkout()

        verdict = self.classify(worktree=worktree)

        self.assertEqual(
            _reasons(verdict.retentions),
            (RetentionReason.UNACCOUNTED_COMMITS,),
        )
        self.assertEqual(verdict.retentions[0].subject, self.branch)

    def test_both_sides_of_a_candidate_are_read(self) -> None:
        # What an operator is handed is the whole list of what to go and look
        # at, so a dirty checkout does not hide the branch beside it.
        self.commit()
        worktree = self.checkout()
        (worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        self.assertEqual(
            self.kept(worktree=worktree, branches=self.branches),
            (
                RetentionReason.WORKTREE_DIRTY,
                RetentionReason.UNACCOUNTED_COMMITS,
            ),
        )


class BranchTipProofTest(_eligibility_case._CandidateTestCase):
    """What a branch the remote's base does not carry has to prove."""

    def test_a_terminal_request_releases_the_tip(self) -> None:
        # The branch is ahead of base and the remote no longer carries it, so
        # what accounts for the commit is the pull request it went out on --
        # matched by object id, not by the branch's name.
        self.gh.add_pr(_pull_request(PR_NUMBER, self.branch, self.commit()))

        self.assertTrue(self.classify().eligible)

    def test_commits_nothing_accounts_for_are_kept(self) -> None:
        self.commit()

        verdict = self.classify()

        self.assertEqual(
            _reasons(verdict.retentions),
            (RetentionReason.UNACCOUNTED_COMMITS,),
        )
        self.assertEqual(verdict.retentions[0].subject, self.branch)

    def test_a_planted_tracking_ref_releases_nothing(self) -> None:
        # The tampering the remote reads exist for. Every `refs/remotes/...`
        # in this clone is a local ref the per-issue worktrees can write, so
        # an agent points the base mirror and the branch's own mirror at its
        # unpublished tip -- and the remote goes on saying what it holds.
        tip = self.commit()
        _candidate_host._tracking_ref(self.clone, BASE_BRANCH, tip)
        _candidate_host._tracking_ref(self.clone, self.branch, tip)

        self.assertEqual(
            self.kept(), (RetentionReason.UNACCOUNTED_COMMITS,),
        )

    def test_a_remote_that_disagrees_keeps_it(self) -> None:
        # The local branch and the branch the remote carries are on different
        # commits, so whatever a pull request would account for is not the
        # commit being deleted.
        self.gh.add_pr(_pull_request(PR_NUMBER, self.branch, self.commit()))
        self.world.publish(
            self.clone,
            self.branch,
            self.world.commit_on(self.clone, f"{self.branch}-elsewhere"),
        )

        self.assertEqual(self.kept(), (RetentionReason.REMOTE_DIVERGENCE,))

    def test_a_branch_holding_the_head_is_not_reasked(self) -> None:
        # The branch is proven on its own terms and it is what holds the
        # commit the checkout stands on, so the checkout owes nothing
        # further. What that saves is a second round trip: the remote is
        # asked once for the base and once for the branch, and the checkout
        # beside them adds none.
        self.gh.add_pr(_pull_request(PR_NUMBER, self.branch, self.commit()))
        worktree = self.checkout()

        with patch.object(
            _tip_evidence, "_published_tip", wraps=_tip_evidence._published_tip,
        ) as asked:
            verdict = self.classify(
                worktree=worktree, branches=self.branches,
            )

            self.assertEqual(verdict.retentions, ())
            self.assertEqual(asked.call_count, 2)

    def test_a_remote_ahead_of_a_merged_tip_keeps_it(self) -> None:
        # The local tip is in the base, so the ancestry alone would release
        # it -- while the remote branch has been pushed past it and carries
        # work this host has never seen. The reclaim would take that branch
        # down with the rest, so the remote is asked whatever the base says.
        self.landed()
        ahead = f"{self.branch}-ahead"
        self.world.commit_on(self.clone, ahead, start=self.branch)
        self.world.publish(self.clone, self.branch, ahead)

        self.assertEqual(self.kept(), (RetentionReason.REMOTE_DIVERGENCE,))

    def test_a_branch_already_gone_is_nothing(self) -> None:
        # Gone from this clone and never on the remote. There is nothing left
        # to reclaim, and a retention over it is one no operator could ever
        # settle -- and nothing is handed over for it either, since there is
        # no longer a branch holding a commit to clear.
        verdict = self.classify()

        self.assertTrue(verdict.eligible)
        self.assertEqual(verdict.proven, ())


class UnreadableReadTest(_eligibility_case._CandidateTestCase):
    """Every question about the artifacts that could not be put keeps them."""

    def test_a_git_read_that_never_ran_keeps_it(self) -> None:
        self.commit()

        with patch.object(
            commands, "_git_hardened", side_effect=OSError("no git here"),
        ):
            self.assertEqual(
                self.kept(), (RetentionReason.BRANCH_UNREADABLE,),
            )

    def test_a_tree_that_will_not_resolve_keeps_it(self) -> None:
        # The checkout is established as this issue's own from reads that
        # take the path as it is; the status read that follows resolves it,
        # and a symlink loop raises out of `Path.resolve` on Python 3.12
        # rather than answering. Between the two reads the tree belongs to an
        # agent, so the classification has to answer for the candidate rather
        # than end the pass every other candidate is in.
        self.landed()
        worktree = self.checkout()

        with patch.object(
            commands,
            "_work_tree_arg",
            side_effect=RuntimeError("Symlink loop from the checkout"),
        ):
            self.assertEqual(
                self.kept(worktree=worktree),
                (RetentionReason.WORKTREE_UNREADABLE,),
            )

    def test_a_remote_that_will_not_answer_keeps_it(self) -> None:
        # Nothing about this branch was established on the remote, and the
        # remote is what a reclaim asks before it measures anything: an
        # unasked question is not the same as a branch the remote does not
        # carry, which is the answer that lets one through.
        self.commit()
        self.world.unreachable(self.spec)

        self.assertEqual(self.kept(), (RetentionReason.REMOTE_UNREADABLE,))

    def test_a_base_that_cannot_be_measured_keeps_it(self) -> None:
        # The remote named a base and answered about the branch, and the
        # comparison between the two is still one this clone could not take
        # -- a base commit it has never fetched is exactly that.
        self.commit()

        with patch.object(
            _tip_evidence, "_base_contains", return_value=ProbeAnswer.UNREADABLE,
        ):
            self.assertEqual(
                self.kept(), (RetentionReason.BASE_UNREADABLE,),
            )

    def test_a_transport_that_raised_keeps_it(self) -> None:
        # The remote is asked through a read that spawns processes: it
        # answers `None` for the failures it recognizes and raises for the
        # ones underneath -- no git to spawn, an askpass the host would not
        # let it write. Left to escape, one candidate's unlucky tick would
        # take the whole pass down with it.
        self.commit()

        with patch.object(
            branch_transport,
            "_remote_branch_tip",
            side_effect=OSError("no git here"),
        ):
            self.assertEqual(
                self.kept(), (RetentionReason.REMOTE_UNREADABLE,),
            )

    def test_a_clone_that_vanished_keeps_it(self) -> None:
        # The same failure arrived at from the host: the clone is gone by the
        # time this candidate is reached, so every read of it fails in its
        # spawn. The verdict is still a verdict, and the branch read -- the
        # first question asked of the clone -- is what it names.
        self.commit()
        shutil.rmtree(self.clone)

        self.assertEqual(self.kept(), (RetentionReason.BRANCH_UNREADABLE,))

    def test_a_branch_read_that_failed_keeps_it(self) -> None:
        # The base answered and this branch did not, which is the one shape
        # that separates the two reads: the candidate is measurable and its
        # publication is still unknown.
        self.commit()
        base = _tip_evidence._published_tip(self.spec, BASE_BRANCH)

        with patch.object(
            _tip_evidence,
            "_published_tip",
            side_effect=lambda _spec, branch: (
                base if branch == BASE_BRANCH
                else BranchTip(answer=ProbeAnswer.UNREADABLE)
            ),
        ):
            self.assertEqual(
                self.kept(), (RetentionReason.REMOTE_UNREADABLE,),
            )


class ClassifiedCandidatesTest(_eligibility_case._CandidateTestCase):
    """Every candidate one repository's scan reported gets its own verdict."""

    def test_the_retained_come_back_with_the_rest(self) -> None:
        # A caller holding only the eligible ones cannot tell an issue it may
        # not touch from one this pass never reached.
        self.landed()
        other_branch = _namespaced_branch(WIDGET_SLUG, OTHER_ISSUE_NUMBER)
        self.world.commit_on(self.clone, other_branch)
        self.gh.add_issue(_terminal_issue(OTHER_ISSUE_NUMBER))
        candidates = (
            _candidate(self.spec, ISSUE_NUMBER, branches=self.branches),
            _candidate(
                self.spec, OTHER_ISSUE_NUMBER, branches=(other_branch,),
            ),
        )

        verdicts = eligibility._classified_candidates(self.gh, candidates)

        self.assertEqual(
            tuple(verdict.artifacts.issue_number for verdict in verdicts),
            (ISSUE_NUMBER, OTHER_ISSUE_NUMBER),
        )
        self.assertEqual(
            tuple(verdict.eligible for verdict in verdicts), (True, False),
        )


if __name__ == "__main__":
    unittest.main()
