# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a recovery refuses, and what it leaves the branch standing on.

A resumed collapse asks for its publication exactly as a fresh squash does, so
every refusal a squash owes is one a recovery owes too -- a pull request a
human closed while the process was down, a remote somebody else moved, a tree
that stopped being provably clean. None of them is repaired here.

Which way the branch goes is one rule read from its ends: it may be put back
onto the head the record names only where nothing durable claims the commit on
it. Put back wrongly, the retry finds one commit and reports there is nothing
to squash; left standing wrongly, a human is asked to reconcile a branch that
never needed it.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.late_split import collapses as _collapses
from tests.git.publication import squash_git_support as squash_support, squash_recovery_support as _support
from tests.git.publication.squash_gate_support import (
    SQUASH_PR_NUMBER,
    TRACKED_FILE,
)
from tests.git.publication.squash_recovery_support import SquashRecoveryMixin

# A count no history in these fixtures has, which is what a hand-edited or
# foreign record's own reads back as.
FORGED_COUNT = 999

# A recorded end that is not an object id at all, which is what a hand edit or
# an older writer leaves: whole-looking, and readable for nothing.
NOT_A_COMMIT = "not-a-sha"

# The seam both the planning probes and the recovery's own proof read the
# worktree through, and what it answers when git could not be asked at all.
STATUS_HELPER = "_worktree_status"

UNREADABLE_TREE = _verification_probes._WorktreeStatus(readable=False)

# What each notice about a moved branch says the branch is standing on, which
# is the difference an operator acts on: the recorded head is still under the
# stray work, or it was replaced and lives only in the reflog.
STILL_REACHABLE = "committed on top of it"

REPLACED = "was not built on it"


class RefusedResumeRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A collapse the publication would not be entered on."""

    def test_a_moved_remote_puts_the_branch_back(self) -> None:
        # Nothing names the collapse, so the branch may go back -- and it has
        # to, or the retry finds one commit it would report as nothing to
        # squash while the remote carries somebody else's work.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_after_the_commit(gate)
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = _support.MOVED_HEAD

        squash_run = self._squashes(self._next_tick(gate))

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)

    def test_an_untouched_branch_says_it_is_untouched(self) -> None:
        # The terms go down BEFORE the reset, so a record standing over a
        # branch still carrying every approved commit is the ordinary shape of
        # a tick that died in that window. Reported as a collapse, the park
        # would send an operator looking in the reflog for commits that are at
        # HEAD.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        (self.work / TRACKED_FILE).write_text("loose\n")

        squash_run = self._squashes(self._next_tick(gate))

        self.assertIsNotNone(squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_INTACT)
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)

    def test_a_dirty_tree_leaves_the_record_standing(self) -> None:
        # The preconditions refuse before the record is even read, so the
        # claim survives for the tick that finds the tree settled.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        (self.work / TRACKED_FILE).write_text("loose\n")

        squash_run = self._squashes(self._next_tick(gate))

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))


class MovedBranchRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A branch something moved while the collapse was outstanding.

    The recovery owns the tick from the moment a record goes down, so nothing
    in this workflow resumes a developer or publishes over a branch carrying
    one. A head that moved off the recorded one is therefore work nobody here
    made -- and squashed afresh it would be force-pushed onto the pull request
    as history a reviewer approved. Both shapes keep the claim; the notice is
    what tells them apart, since an operator finds the approved commits under
    the stray work in one and only in the reflog in the other.
    """

    def test_a_buried_record_is_not_squashed_afresh(self) -> None:
        # The reset never ran and something committed over the checkout, so
        # the recorded head is buried under work no reading here accounts for.
        # Dropped, the squash would collapse that work in with the approved
        # commits and publish the lot under a fresh count.
        gate = self._gate_subject()
        self._crashes_before_the_reset(gate)
        self._commits_over(1)
        buried = self._head_sha()
        # The publication would be entered on exactly this head, so nothing
        # downstream would refuse the fresh squash: only the reading of who
        # moved the branch stands between it and a force-push.
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = buried

        squash_run = self._squashes(self._next_tick(gate))

        self.assertFalse(squash_run.success)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), buried)
        pinned = self._pinned(gate)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, pinned)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_COUNT], _support.APPROVED_COMMITS)
        # The approved commits are under the stray work, and both halves of
        # what the caller says have to agree with that: the error names where
        # the branch went, and the reading places it there rather than in a
        # reflog an operator would search past them.
        self.assertIn(STILL_REACHABLE, squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_BURIED)

    def test_a_replaced_head_is_not_buried(self) -> None:
        # The same several commits, and the recorded head is the one thing
        # that tells the two apart: a buried one is still reachable, a
        # replaced one is not. Here the collapse was made and something was
        # committed over it, so squashing afresh would take the collapse with
        # the stray commit while the notice the first one still owes goes with
        # the record.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        self._commits_over(1)
        over = self._head_sha()
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = over

        squash_run = self._squashes(self._next_tick(gate))

        self.assertFalse(squash_run.success)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), over)
        pinned = self._pinned(gate)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, pinned)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_COUNT], _support.APPROVED_COMMITS)
        # And here they are only in the reflog, which is the other notice --
        # the recorded head is not reachable from this branch at all.
        self.assertIn(REPLACED, squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_COLLAPSED)


class UnprovableCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A record whose claims this repository does not bear out.

    A whole-looking record is one somebody could have written, not one this
    host ever produced. Each case below leaves every field the right shape and
    breaks one thing the objects would have to agree with -- and none of them
    may reach a push, because what a push would send is a commit the record
    was never about.

    None of them puts the branch back either. Every other refusal here knows
    what the branch is standing on; this is the answer to not knowing, and a
    reset would be a guess taken with a destructive step.
    """

    def test_an_absent_base_is_never_published(self) -> None:
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_BASE_SHA, _support.ABSENT_HEAD)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), squashed)

    def test_a_forged_count_is_never_reported(self) -> None:
        # The count is the one field of the record that is not an object id,
        # and what it becomes is the number a human is told their history was
        # collapsed from.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_COUNT, FORGED_COUNT)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        self.assertNotEqual(squash_run.count, FORGED_COUNT)
        squash_run.push_mock.assert_not_called()

    def test_an_unrelated_commit_is_never_published(self) -> None:
        # One commit over the base is what a collapse leaves and what a
        # developer's single commit leaves, and only the tree tells them
        # apart: a squash carries the tree of the head it replaced, exactly.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        self._rebuild_single_commit()
        unrelated = self._head_sha()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), unrelated)
        # And the caller is told where that leaves the branch: not on the
        # commits the reviewer approved, so a human is not sent looking for
        # them at HEAD -- and the head the record names is an object this host
        # holds, so the reflog entry the notice sends them to resolves.
        self.assertEqual(squash_run.standing, _support.BRANCH_COLLAPSED)

    def test_a_missing_head_is_never_called_stale(self) -> None:
        # Several commits on the branch say nothing about where the recorded
        # head went. Read as a record the branch has buried, it would be
        # dropped and the branch squashed and force-pushed afresh over a
        # collapse nothing here can account for.
        gate = self._gate_subject()
        self._crashes_before_the_reset(gate)
        self._commits_over(1)
        buried = self._head_sha()
        # The publication would be entered on exactly this head, so nothing
        # downstream would refuse the fresh squash: only the record's own
        # claims stand between it and a force-push.
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = buried
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, _support.ABSENT_HEAD)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), buried)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))

    def test_a_missing_base_is_never_called_stale(self) -> None:
        gate = self._gate_subject()
        self._crashes_before_the_reset(gate)
        self._commits_over(1)
        buried = self._head_sha()
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = buried
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_BASE_SHA, _support.ABSENT_HEAD)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), buried)

    def test_an_unreadable_tree_is_never_published(self) -> None:
        # The planning probes refuse on what git NAMED, so a status that
        # established nothing reads to them as a clean tree. A resumed push
        # has to prove the opposite.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        resumed = self._next_tick(gate)

        with patch.object(
            _verification_probes, STATUS_HELPER,
            MagicMock(return_value=UNREADABLE_TREE),
        ):
            squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)

    def test_an_unreadable_tree_is_never_handed_on(self) -> None:
        # The road that hands the branch BACK to the ordinary squash is the
        # one nothing else would catch: an untouched record is dropped, and
        # with `DECOMPOSE=off` the entry behind it reads no pull request and
        # so proves no tree either -- so the rewrite and the push would go out
        # over a checkout nothing here could describe.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        resumed = self._next_tick(gate)

        with patch.object(
            _verification_probes, STATUS_HELPER,
            MagicMock(return_value=UNREADABLE_TREE),
        ):
            squash_run = self._squashes(resumed, **{_support.DECOMPOSE: False})

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)
        # And the claim is left standing rather than dropped on the way past,
        # which is what says the refusal came from the classification itself.
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))


class ForgedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """Shapes a comparison reads as true and this workflow never produced.

    A squash is exact about two things at once: the object it makes carries
    the tree of the head it replaced, and it has the base it was collapsed
    onto as its one parent. Either alone is something a hand can arrange over
    a history the record was never about.
    """

    def test_a_reparented_tree_is_never_published(self) -> None:
        # The same tree on a base that has since advanced is a commit that
        # REVERTS whatever that base added. A tree comparison alone says it is
        # the collapse; the parent list is what says it was made on some other
        # history, and publishing it would take those files off the pull
        # request under an exemption a human granted a different change.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        forged = self._forges_over_the_base()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), forged)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))

    def test_an_unrelated_base_is_never_published(self) -> None:
        # A walk between two histories that never met reports a number like
        # any other, so a base swapped for one off another history reads as a
        # whole record the moment the count is adjusted to match. The pair has
        # to BE a pair.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()
        resumed = self._next_tick(gate)
        self._records_an_unrelated_base(resumed, accepted)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), squashed)

    def test_a_head_moved_onto_the_collapse_refuses(self) -> None:
        # The record's head edited onto the commit a finished collapse left
        # reads as a rewrite that never happened, and the shortcut for one
        # would drop it and hand on a branch of ONE commit -- which is the
        # nothing-to-squash road reporting success while the remote still
        # carries every commit the record names. Proved first, the same record
        # is refused: the walk between its ends does not come to the number it
        # counts.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, squashed)

        squash_run = self._squashes(resumed)

        self.assertFalse(squash_run.success)
        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), squashed)
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)
        # And the claim is left standing rather than dropped on the way past.
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))

    def _records_an_unrelated_base(self, resumed, head: str) -> None:
        """Swap the recorded base for one this head never grew from.

        The count goes with it, at the number a walk between the two really
        reports -- which is the whole point: it is a number like any other,
        and a record carrying it reads as whole.
        """
        orphan = self._unrelated_history()
        counted = squash_support.run_git(
            "rev-list", "--count", f"{orphan}..{head}", cwd=self.work,
        )
        resumed.state.set(_support.KEY_COLLAPSE_BASE_SHA, orphan)
        resumed.state.set(_support.KEY_COLLAPSE_COUNT, int(counted.strip()))


class DiscardedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A record standing over a branch with nothing left on it.

    The shape the ordinary squash could not be trusted with: it reports
    success without pushing for a branch carrying nothing over its base, and
    the remote still has every commit the record says was collapsed.
    """

    def test_an_emptied_branch_refuses(self) -> None:
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        self._discards_the_branch()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertFalse(squash_run.success)
        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))

    def test_a_half_made_collapse_refuses(self) -> None:
        # The seam between the reset and the commit: HEAD is the base and
        # every collapsed change is staged. The retry finds a tree it cannot
        # prove clean and stops rather than reading an empty branch as one
        # with nothing to squash.
        gate = self._gate_subject()
        self._crashes_before_the_commit(gate)
        self._assert_branch_carries(0)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertFalse(squash_run.success)
        self.assertIsNotNone(squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_COLLAPSED)
        squash_run.push_mock.assert_not_called()
        self.assertIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))


class UnusableCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A claim on the comment this build cannot act on.

    None of these says where the branch is, and that is the point: the record
    is the only account there is of a rewrite, so one that cannot be read
    whole leaves an untouched branch and a collapsed one looking exactly the
    same. A notice that picked either would send an operator to a HEAD or a
    reflog entry nothing here established.
    """

    def test_a_partial_record_refuses(self) -> None:
        # Half a record is still a claim that a collapse is outstanding, and
        # the branch it is about carries the one commit that reads as nothing
        # to squash. Waved past, approved work is handed on unpublished.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        resumed = self._next_tick(gate)
        _collapses.clear_pending_collapse(resumed.state)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, self._base_sha())

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        self.assertFalse(squash_run.success)
        squash_run.push_mock.assert_not_called()
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)

    def test_an_absent_head_leaves_the_branch(self) -> None:
        # The rollback needs the recorded head as an object, and one this
        # repository never had is not a commit anything can be reset onto. The
        # collapse stays where it is and a human is told.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, _support.ABSENT_HEAD)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), squashed)
        # And the notice may not send anybody to it either: what a collapse
        # notice names is the recorded head, and this host holds no object by
        # that id.
        self.assertEqual(squash_run.standing, _support.BRANCH_UNKNOWN)

    def test_an_untouched_branch_is_not_placed(self) -> None:
        # The terms go down BEFORE the reset, so half a record over a branch
        # still carrying every approved commit is an ordinary crash window.
        # Reported as a collapse, the park would tell an operator the branch
        # is not on the approved commits while they are at HEAD, and send
        # them to the reflog for history that never left it.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        resumed = self._next_tick(gate)
        _collapses.clear_pending_collapse(resumed.state)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, accepted)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_UNKNOWN)
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)

    def test_a_malformed_end_places_nothing_either(self) -> None:
        # A whole-looking group whose head is not an object id at all. It
        # claims a collapse just as loudly and can be read for even less, so
        # the branch behind it is as unplaced as the one above.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        resumed = self._next_tick(gate)
        resumed.state.set(_support.KEY_COLLAPSE_HEAD, NOT_A_COMMIT)

        squash_run = self._squashes(resumed)

        self.assertIsNotNone(squash_run.error)
        self.assertEqual(squash_run.standing, _support.BRANCH_UNKNOWN)
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)


if __name__ == "__main__":
    unittest.main()
