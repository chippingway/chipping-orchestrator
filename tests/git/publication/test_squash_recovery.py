# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick coming back to a half-finished squash does with the branch.

A squash collapses the commits a reviewer approved into one object with the
same tree, so the branch it leaves behind is indistinguishable from a branch
nobody ever squashed. Read as the second, the interrupted rotation takes the
nothing-to-squash road and is reported as a success that measured nothing and
pushed nothing -- with approved work reaching the merge button neither counted
nor on the remote.

The record the squash writes before it runs is what tells them apart, and each
case here stops one run at one seam and asks what the tick after it does. The
rewrite is real git against a real bare remote, so the branch every assertion
is about is the branch the recovery really found. What a resume REFUSES is
pinned down beside this, in `test_squash_recovery_refusals.py`.
"""
from __future__ import annotations

import unittest

from tests.git.publication import squash_git_support as squash_support, squash_recovery_support as _support
from tests.git.publication.squash_gate_support import SQUASH_PR_NUMBER
from tests.git.publication.squash_recovery_support import SquashRecoveryMixin


class RecordedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """What a squash says about itself before it destroys the evidence."""

    def test_the_terms_are_durable_before_the_reset(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()

        self._crashes_before_the_reset(gate)

        pinned = self._pinned(gate)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_HEAD], accepted)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_BASE_SHA], self._base_sha())
        self.assertEqual(pinned[_support.KEY_COLLAPSE_COUNT], _support.APPROVED_COMMITS)

    def test_a_landed_push_leaves_the_claim(self) -> None:
        # The push is not the end of the collapse: the count on this record is
        # what the notice behind it is worded from, and the notice, the
        # watermarks, and the relabel are all still ahead. The stage that
        # finishes the handoff is what drops it.
        gate = self._gate_subject()

        squash_run = self._squashes(gate, push_result=self._publishes(gate))

        self.assertTrue(squash_run.success)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, gate.state.data)

    def test_a_refused_push_takes_the_claim_back(self) -> None:
        # The reset puts the branch back on the commits the record says were
        # collapsed, so the claim is false the moment it lands.
        gate = self._gate_subject()
        accepted = self._head_sha()

        squash_run = self._squashes(gate, push_result=False)

        self.assertFalse(squash_run.success)
        self.assertEqual(self._head_sha(), accepted)
        self.assertNotIn(_support.KEY_COLLAPSE_HEAD, self._pinned(gate))
        # The branch is back on the approved commits, so the caller's notice
        # may say so.
        self.assertEqual(squash_run.standing, _support.BRANCH_INTACT)


class StaleCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The one branch a record may simply be dropped over.

    A reset that never ran leaves the checkout on the head the record names,
    over the commits it counted -- the branch the record still describes
    exactly. Nothing was rewritten, so the record goes and the squash reads
    the branch as what it is. Every other shape is a branch something moved,
    and those are refused beside this file.
    """

    def test_an_untouched_branch_is_squashed_afresh(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        self._assert_branch_carries(_support.APPROVED_COMMITS)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs[_support.LEASE], accepted,
        )
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)


class UnpushedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A collapse that landed locally and reached neither gate nor remote.

    Nothing durable names the commit on the branch: no approval, no
    permission, and no receipt. Read without the record, it is one commit and
    the retry reports there is nothing to squash.
    """

    def test_an_unpushed_collapse_is_published(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_support.REVISION], squashed)
        self.assertEqual(pushed[_support.LEASE], accepted)
        # And it is the commit already on the branch that goes out: nothing is
        # collapsed a second time, so the object measured and pushed is the
        # one the interrupted tick made.
        self.assertEqual(self._head_sha(), squashed)
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)


class AuthorizedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A collapse the gate approved and whose push never went out."""

    def test_the_approved_collapse_is_published(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_push(gate)
        squashed = self._head_sha()
        self.assertEqual(self._pinned(gate)[_support.KEY_APPROVED_SHA], squashed)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_support.REVISION], squashed)
        self.assertEqual(pushed[_support.LEASE], accepted)
        self.assertEqual(self._head_sha(), squashed)


class PublishedCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A collapse the remote already carries and the comment does not say so.

    The push landed and the receipt behind it never did, so the pull request
    is standing on the rewritten commit while the record still says a squash
    is outstanding.
    """

    def test_a_landed_collapse_is_a_leased_no_op(self) -> None:
        gate = self._gate_subject()
        self._crashes_after_the_push(gate)
        squashed = self._head_sha()
        self.assertNotIn(_support.KEY_RECEIPT_SHA, self._pinned(gate))

        squash_run = self._squashes(
            self._next_tick(gate), push_result=self._publishes(gate),
        )

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_support.REVISION], squashed)
        # Leased against the commit the pull request already stands on, which
        # is what makes the republication a no-op rather than a rewrite of
        # whatever landed there while this host was down.
        self.assertEqual(pushed[_support.LEASE], squashed)

    def test_a_missed_retry_keeps_a_landed_collapse(self) -> None:
        # The far side of the same window with the retry's own push failing.
        # That push had nothing to send -- the entry froze the pull request
        # standing on this very commit -- so the request missing is a
        # transport failure over work the remote already has. Reset, the
        # checkout would come off a commit the pull request carries, the
        # collapse record and the approval naming it would go with it, and
        # the next tick would find a remote that moved for reasons nothing on
        # the comment explains.
        gate = self._gate_subject()
        self._crashes_after_the_push(gate)
        squashed = self._head_sha()

        squash_run = self._squashes(self._next_tick(gate), push_result=False)

        self.assertIsNotNone(squash_run.error)
        self.assertEqual(self._head_sha(), squashed)
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)
        pinned = self._pinned(gate)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, pinned)
        self.assertEqual(pinned[_support.KEY_APPROVED_SHA], squashed)

    def test_the_receipt_settles_the_debt(self) -> None:
        gate = self._gate_subject()
        self._crashes_after_the_push(gate)
        squashed = self._head_sha()

        resumed = self._next_tick(gate)
        self._squashes(resumed, push_result=self._publishes(gate))

        pinned = self._pinned(resumed)
        self.assertEqual(pinned[_support.KEY_RECEIPT_SHA], squashed)
        self.assertIsNone(pinned.get(_support.KEY_APPROVED_SHA))
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)


class UnfinishedHandoffRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A settled receipt whose handoff and notice never happened.

    The push landed, the receipt is durable, and the write the caller makes
    behind it -- the one that drops the record, seeds the watermarks, and
    moves the label -- was lost. The count the notice is worded from lives
    nowhere but the record by then.
    """

    def test_the_recorded_count_finishes_it(self) -> None:
        gate = self._gate_subject()
        settled = self._squashes(gate, push_result=self._publishes(gate))
        self.assertTrue(settled.success)

        squash_run = self._squashes(
            self._next_tick(gate), push_result=self._publishes(gate),
        )

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        self.assertEqual(squash_run.sha, self._head_sha())

    def test_a_missed_no_op_keeps_the_branch(self) -> None:
        # The push here sends nothing -- the pull request is already standing
        # on the commit -- so a request that fails is a transport failure over
        # work the remote has. Reset, the checkout would come off a commit the
        # pull request carries and the count the notice is still owed would go
        # with the record.
        gate = self._gate_subject()
        self._squashes(gate, push_result=self._publishes(gate))
        squashed = self._head_sha()
        resumed = self._next_tick(gate)

        squash_run = self._squashes(resumed, push_result=False)

        self.assertIsNotNone(squash_run.error)
        self.assertEqual(self._head_sha(), squashed)
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)
        pinned = self._pinned(resumed)
        self.assertIn(_support.KEY_COLLAPSE_HEAD, pinned)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_COUNT], _support.APPROVED_COMMITS)

    def test_the_collapse_is_not_made_again(self) -> None:
        gate = self._gate_subject()
        self._squashes(gate, push_result=self._publishes(gate))
        squashed = self._head_sha()

        self._squashes(self._next_tick(gate), push_result=self._publishes(gate))

        self.assertEqual(self._head_sha(), squashed)
        self._assert_branch_carries(_support.COLLAPSED_COMMITS)


class SwitchedOffCollapseRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """What `SQUASH_ON_APPROVAL=off` does and does not decline.

    The switch answers whether a NEW collapse is made. One an earlier tick
    already made is not a squash it can decline -- the commits are gone from
    the branch and the remote either has the object that replaced them or does
    not -- so an install that flips the switch between the rewrite and the
    push must finish it rather than abandon approved work off the pull
    request.
    """

    def test_nothing_recorded_is_left_alone(self) -> None:
        gate = self._gate_subject()

        squash_run = self._squashes(gate, **{_support.SQUASH_ON_APPROVAL: False})

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, 0)
        squash_run.push_mock.assert_not_called()
        self._assert_branch_carries(_support.APPROVED_COMMITS)
        self.assertNotIn(_support.KEY_COLLAPSE_HEAD, gate.state.data)

    def test_a_moved_remote_still_refuses(self) -> None:
        # The record engaged the recovery, which found the reset never ran and
        # dropped it. With the switch off there is no rewrite behind that drop
        # to enter the publication, so without the reading here the tick hands
        # `documenting` a branch whose remote moved out from under it and the
        # only evidence a squash was ever begun is already gone.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)
        gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = _support.MOVED_HEAD

        squash_run = self._squashes(
            self._next_tick(gate), **{_support.SQUASH_ON_APPROVAL: False},
        )

        self.assertFalse(squash_run.success)
        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(_support.APPROVED_COMMITS)

    def test_a_standing_remote_is_handed_on(self) -> None:
        # And the reading is only a reading: a publication still where this
        # branch left it hands on exactly as it always did, with nothing
        # collapsed and nothing pushed.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)

        squash_run = self._squashes(
            self._next_tick(gate), **{_support.SQUASH_ON_APPROVAL: False},
        )

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, 0)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), accepted)

    def test_a_recorded_collapse_is_still_finished(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()

        squash_run = self._squashes(
            self._next_tick(gate), **{_support.SQUASH_ON_APPROVAL: False},
        )

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, _support.APPROVED_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_support.REVISION], squashed)
        self.assertEqual(pushed[_support.LEASE], accepted)


if __name__ == "__main__":
    unittest.main()
