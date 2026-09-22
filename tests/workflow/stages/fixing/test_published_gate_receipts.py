# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The debt a gated push owes, and the window between it and the record.

Every gated push leaves two things behind: a receipt naming what reached the
remote, and no debt. Both go down in one durable write, because the effect is
already out -- and a process can die anywhere after it. What these pin down is
that window from both ends: the approval a failed push keeps and the head it
is pinned to, the receipt a crash lost being settled by the pull request that
is already standing on the commit, a receipt honoured only while the
publication it names still stands, and the checkout proved again on the far
side of the push.
"""
from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)

AT_THE_CEILING = support.AT_THE_CEILING
BASE_OBJECT_PRESENT = support.BASE_OBJECT_PRESENT
CEILING = support.CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
FREEZE_BASE_COMMIT = support.FREEZE_BASE_COMMIT
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
MEASURED_BASE_SHA = support.MEASURED_BASE_SHA
MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA

# A checkout clean where the round proves it and where the gate freezes it,
# carrying work by the proof past the push. Twice clean before that push
# because a reported round asks the checkout for itself ahead of the gate: a
# tree this host proves is carrying something is the refusal its report's own
# terminal park is for, and no road here publishes over one.
_DIRTIED_AROUND_THE_PUSH = (
    support._WorktreeStatus(readable=True, paths=()),
    support._WorktreeStatus(readable=True, paths=()),
    support._WorktreeStatus(readable=True, paths=("stray.py",)),
)
PAST_THE_CEILING = support.PAST_THE_CEILING
UNDER_THE_CEILING = support.UNDER_THE_CEILING
_SizeGateFixtureMixin = support._SizeGateFixtureMixin
recorded_generation = support.recorded_generation

FIXING = fixing.FIXING
ISSUE = fixing.ISSUE
PR_HEAD_SHA = fixing.PR_HEAD_SHA
PR_NUMBER = fixing.PR_NUMBER
PUSH_BRANCH = fixing.PUSH_BRANCH
SHA_BEFORE = fixing.SHA_BEFORE
STAGE_FIXING = fixing.STAGE_FIXING
VALIDATING = fixing.VALIDATING
config = fixing.config
patch = fixing.patch

_HELD = (ISSUE, LABEL_DECOMPOSING)
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"
WRITE_PINNED_STATE = "write_pinned_state"
WRITE_REJECTED = "pinned write rejected"
SET_WORKFLOW_LABEL = "set_workflow_label"
RELABEL_REJECTED = "label write rejected"
# A second pull request on the same branch, for the record frozen on the
# first: the same head can be the tip of both.
OTHER_PR_NUMBER = PR_NUMBER + 1
# A path no checkout is at, for the host the frozen pair was not made on.
ABSENT_WORKTREE = fixing.Path("/tmp/orchestrator-absent-checkout")
REVIEW_ROUND = fixing.REVIEW_ROUND
PENDING_FIX_AT = fixing.PENDING_FIX_AT

class _CrashesOnceTheReceiptIsWritten:
    """A pinned write that dies on the first write past the landed receipt.

    Armed off what the write CARRIES rather than off how many came before it:
    a tick freezes, retires, and approves before it pushes, so counting writes
    would fail one of those and never reach the window this is about. The
    receipt itself lands, and the write the caller takes after it does not --
    which is the crash the receipt exists to survive.
    """

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped
        self._paid = False

    def __call__(self, issue, state, **options):
        if self._paid:
            raise RuntimeError(WRITE_REJECTED)
        self._paid = (
            state.get(support.KEY_RECEIPT_SHA) == MEASURED_CANDIDATE_SHA
        )
        return self._wrapped(issue, state, **options)


class ApprovedRetryTest(unittest.TestCase, _SizeGateFixtureMixin):
    """The retry after a failed push pins to what the approval was frozen at."""

    def test_a_failed_push_keeps_the_head_it_froze(self) -> None:
        # The approval outlives the generation that froze the pull request's
        # head, so the head has to outlive it too: without that the retry has
        # only the head it can read NOW to pin to.
        scenario = self._seed_fix_round()

        self._run_fix_round(scenario, push_branch=False)

        pinned = scenario.github.pinned_data(ISSUE)
        self.assertEqual(pinned[support.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[support.KEY_APPROVED_LEASE], PR_HEAD_SHA)

    def test_a_landed_push_pays_the_debt_durably(self) -> None:
        # The branch is on the remote and the caller has work left before its
        # own pinned write. A process that died in that window would leave a
        # paid debt pinned for good -- nothing revisits it, and the pre-tick
        # base refresh reads it as a branch frozen out of the sync.
        scenario = self._seed_fix_round()
        github = scenario.github
        crashing = _CrashesOnceTheReceiptIsWritten(github.write_pinned_state)

        with patch.object(github, WRITE_PINNED_STATE, crashing), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario)

        pinned = github.pinned_data(ISSUE)
        self.assertIsNone(pinned.get(support.KEY_APPROVED_SHA))
        self.assertIsNone(pinned.get(support.KEY_APPROVED_LEASE))
        # And the commit that landed is named, so the tick that comes back
        # can tell a push it already made from one it still owes.
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )

    def test_the_tick_after_the_crash_hands_it_on(self) -> None:
        # What the receipt buys: the pull request is standing on the commit
        # the dead tick pushed, and this one re-reads the same checkout. With
        # no receipt the candidate would be measured again -- and a ceiling
        # that moved, or a `single` verdict since, would route a pull request
        # that ALREADY carries the work to `decomposing`. What still goes out
        # is the leased no-op: nothing to send, and the only atomic proof that
        # the publication is still the one that was frozen.
        scenario = self._seed_fix_round(**{
            support.KEY_RECEIPT_SHA: MEASURED_CANDIDATE_SHA,
            # And the head that push replaced, which is what dates the receipt
            # to the attempt this round is finishing rather than to one of the
            # rounds before it.
            support.KEY_RECEIPT_LEASE: PR_HEAD_SHA,
            # And the publication it went onto, which neither of those says: a
            # branch pushed from that head onto a pull request since closed
            # and replaced would answer for both.
            support.KEY_RECEIPT_PR: PR_NUMBER,
        })
        scenario.github.get_pr(PR_NUMBER).head.sha = MEASURED_CANDIDATE_SHA

        with patch.object(config, support.MAX_ADDED_LINES, 0):
            mocks = self._run_fix_round(scenario)

        self._assert_unmeasured(mocks)
        self._assert_settled_publication(mocks)
        self.assertNotIn(
            (ISSUE, LABEL_DECOMPOSING), scenario.github.label_history,
        )
        # The round finished, so the reviewer gets the head it was told about.
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)

    def test_a_debt_with_no_lease_refuses(self) -> None:
        # Half an approval is no approval. The lease is the whole of what
        # keeps the retry off a pull request somebody moved, and the head read
        # NOW is exactly the move it exists to catch -- so an approval whose
        # lease never landed is refused rather than pinned to the present.
        scenario = self._seed_fix_round(
            **{support.KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA},
        )

        mocks = self._run_fix_round(scenario)

        self._assert_held(scenario, mocks)
        self._assert_parked(scenario)

    def test_a_hand_edited_lease_refuses(self) -> None:
        # Read fail-closed like every other late commit field: a lease that is
        # not a whole object id is no lease, not a shortened one to pass on to
        # git.
        scenario = self._seed_fix_round(**dict(
            self._approved(), **{support.KEY_APPROVED_LEASE: PR_HEAD_SHA[:8]},
        ))

        mocks = self._run_fix_round(scenario)

        self._assert_unpushed(mocks)
        self._assert_parked(scenario)

    def test_the_retry_refuses_a_head_that_moved(self) -> None:
        # The round names the head it began at, and by the time the entry is
        # frozen the pull request is standing somewhere else -- and somewhere
        # this issue never put it. That is somebody else's push landing while
        # the agent was out, so the tick stops at the entry: nothing is
        # measured, nothing goes out, and the approval is left for a human to
        # reconcile rather than force-overwriting whoever landed in between.
        scenario = self._seed_fix_round(**self._approved())
        scenario.github.get_pr(PR_NUMBER).head.sha = support.MOVED_HEAD

        mocks = self._run_fix_round(scenario)

        self._assert_unmeasured(mocks)
        self._assert_held(scenario, mocks)
        self._assert_parked(scenario)

    def _approved(self) -> dict:
        """The pinned pair a failed push leaves: the debt and its lease."""
        return {
            support.KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            support.KEY_APPROVED_LEASE: PR_HEAD_SHA,
        }


class _RejectsTheReceiptWrite:
    """A pinned write that dies on the receipt the landed push leaves.

    The first write past the effect, and the one the crash window is about:
    the branch is on the remote and the pinned comment still says the commit
    is owed, leased to a head the remote has moved off.
    """

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped

    def __call__(self, issue, state, **options):
        if state.get(support.KEY_RECEIPT_SHA) == MEASURED_CANDIDATE_SHA:
            raise RuntimeError(WRITE_REJECTED)
        return self._wrapped(issue, state, **options)


class LostReceiptTest(unittest.TestCase, _SizeGateFixtureMixin):
    """What the remote says when the record of a push never landed."""

    def test_a_rejected_receipt_keeps_the_debt(self) -> None:
        # The window itself: the push went out and the write that would have
        # said so did not, so the pinned comment still owes a publication for
        # a commit the remote already has, pinned to a head it has moved off.
        scenario = self._seed_fix_round()
        github = scenario.github
        rejecting = _RejectsTheReceiptWrite(github.write_pinned_state)

        with patch.object(github, WRITE_PINNED_STATE, rejecting), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario)

        pinned = github.pinned_data(ISSUE)
        self.assertEqual(pinned[support.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertNotIn(support.KEY_RECEIPT_SHA, pinned)

    def test_the_tick_after_it_reconciles_the_debt(self) -> None:
        # What settles that window is the REMOTE, not the record: the pull
        # request is standing on the commit the debt is for, so the push it
        # licenses has nothing left to send. Left unsettled, `late_approved_sha`
        # freezes this branch out of the pre-tick base refresh for the rest of
        # its life -- nothing measures the commit again, so nothing else ever
        # drops it.
        scenario = self._landed_but_unrecorded()

        mocks = self._run_fix_round(scenario)

        self._assert_settled_publication(mocks)
        pinned = self._pinned(scenario)
        self.assertIsNone(pinned.get(support.KEY_APPROVED_SHA))
        self.assertIsNone(pinned.get(support.KEY_APPROVED_LEASE))
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )

    def test_the_reconciled_round_hands_the_fix_on(self) -> None:
        # And it is a finished round rather than a park: the reviewer is owed
        # a look at a head the pull request really is standing on.
        scenario = self._landed_but_unrecorded()

        self._run_fix_round(scenario)

        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)

    def test_a_lease_it_cannot_read_is_reconciled_too(self) -> None:
        # The lease requirement is about a push that has to be PINNED, and
        # there is no push here to pin: the remote already carries the commit.
        # Parking for a lease nothing needs would leave the debt standing for
        # exactly the reason it must not.
        scenario = self._landed_but_unrecorded(lease=None)

        mocks = self._run_fix_round(scenario)

        # Pinned to the head the pull request is on rather than to the one the
        # record could not show, which is the head no push needs any more.
        self._assert_settled_publication(mocks)
        self.assertIsNone(self._pinned(scenario).get(support.KEY_APPROVED_SHA))

    def _landed_but_unrecorded(self, *, lease: str | None = PR_HEAD_SHA):
        """The durable state a rejected receipt write leaves behind."""
        scenario = self._seed_fix_round(**{
            support.KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            support.KEY_APPROVED_LEASE: lease,
        })
        # The dead tick's push landed, so this is where the remote is.
        scenario.github.get_pr(PR_NUMBER).head.sha = MEASURED_CANDIDATE_SHA
        return scenario


class SettledPublicationRaceTest(unittest.TestCase, _SizeGateFixtureMixin):
    """The window a publication the remote already carries still has open.

    Nothing is left to send, but everything this tick knows about the pull
    request is a reading it froze: the branch can move under it, and so can
    the checkout every stage behind the gate works from. The no-op is leased
    and the checkout is proved for exactly those two.
    """

    def test_a_publication_that_moved_stops_the_tick(self) -> None:
        # The lease is what asks the remote, atomically, whether the frozen
        # publication is still the one the pull request has. Refused, the debt
        # stays owed and nothing is handed on -- settled and relabelled here,
        # the reviewer would vote on a head somebody else put there.
        scenario = self._landed_but_unrecorded()

        mocks = self._run_fix_round(scenario, push_branch=False)

        self._assert_settled_publication(mocks)
        self.assertNotIn(
            (ISSUE, VALIDATING), scenario.github.label_history,
        )
        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertNotIn(support.KEY_RECEIPT_SHA, pinned)

    def test_a_checkout_that_moved_holds_the_handoff(self) -> None:
        # The publication stands -- the remote was proved to carry it -- and
        # the CHECKOUT is what every stage behind this gate reads. Handed on,
        # the reviewer reads a head ahead of the published branch as unpushed
        # work and the docs pass commits on top of it.
        scenario = self._landed_but_unrecorded()

        mocks = self._run_fix_round(
            scenario,
            candidate_commit=(
                support.FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
                support.FrozenCommit(sha=support.MOVED_AFTER_PUSH),
            ),
        )

        self._assert_settled_publication(mocks)
        self._assert_the_handoff_stopped(scenario)

    def test_a_tree_dirtied_under_it_holds(self) -> None:
        # The other half of the same proof: uncommitted work beside the
        # published commit is content the pull request does not carry, and the
        # reviewer reads the tree directly.
        scenario = self._landed_but_unrecorded()

        mocks = self._run_fix_round(
            scenario, tree_states=_DIRTIED_AROUND_THE_PUSH,
        )

        self._assert_settled_publication(mocks)
        self._assert_the_handoff_stopped(scenario)

    def _assert_the_handoff_stopped(self, scenario) -> None:
        """The receipt is durable and the issue goes no further."""
        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixing.PARK_REASON], support.PARK_CANDIDATE_MOVED,
        )
        self.assertNotIn((ISSUE, VALIDATING), scenario.github.label_history)

    _landed_but_unrecorded = LostReceiptTest._landed_but_unrecorded


class MovedPublicationReceiptTest(unittest.TestCase, _SizeGateFixtureMixin):
    """A receipt is honoured only while the publication it names stands."""

    def test_a_remote_that_moved_off_it_stops(self) -> None:
        # The receipt is a local note about a push; what it is evidence FOR is
        # that the pull request carries the commit. Somebody pushed over it
        # between the receipt and this tick, and the head the round began at
        # is what says so -- so nothing is measured and nothing goes out,
        # rather than a force-push putting the branch back where the receipt
        # remembers it and dropping whoever landed.
        scenario = self._moved_off_the_receipt()

        mocks = self._run_fix_round(scenario)

        self._assert_unmeasured(mocks)
        self._assert_held(scenario, mocks)
        self._assert_parked(scenario)

    def test_the_receipt_is_left_for_the_repair(self) -> None:
        # Nothing about the record is rewritten on the way out: what reached
        # the remote is still what reached it, and which of the two heads is
        # the one to keep is a human's call rather than this tick's.
        scenario = self._moved_off_the_receipt()

        self._run_fix_round(scenario)

        self.assertEqual(
            self._pinned(scenario)[support.KEY_RECEIPT_SHA],
            MEASURED_CANDIDATE_SHA,
        )

    def _moved_off_the_receipt(self):
        """A receipt naming this commit, and a pull request past it."""
        scenario = self._seed_fix_round(
            **{support.KEY_RECEIPT_SHA: MEASURED_CANDIDATE_SHA},
        )
        scenario.github.get_pr(PR_NUMBER).head.sha = support.MOVED_HEAD
        return scenario


class CheckoutRaceTest(unittest.TestCase, _SizeGateFixtureMixin):
    """The window past the push, where the effect is out and the tree is not.

    The push is a request and the worktree is writable while it runs. What
    went out is the commit that was named, so the branch is right; what is
    wrong is the checkout, and the checkout is what every stage behind the
    gate reads.
    """

    def test_a_head_that_moved_during_the_push_holds(self) -> None:
        scenario = self._seed_fix_round()

        mocks = self._run_fix_round(
            scenario,
            candidate_commit=(
                support.FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
                support.FrozenCommit(sha=support.MOVED_AFTER_PUSH),
            ),
        )

        self._assert_pushed_once(mocks)
        self._assert_publication_stands(scenario, support.PARK_CANDIDATE_MOVED)

    def test_a_tree_dirtied_during_the_push_holds(self) -> None:
        scenario = self._seed_fix_round()

        mocks = self._run_fix_round(
            scenario, tree_states=_DIRTIED_AROUND_THE_PUSH,
        )

        self._assert_pushed_once(mocks)
        self._assert_publication_stands(scenario, support.PARK_CANDIDATE_MOVED)

    def _assert_publication_stands(self, scenario, reason: str) -> None:
        """The push kept its receipt; only the handoff stopped."""
        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(pinned[fixing.PARK_REASON], reason)
        self.assertNotIn((ISSUE, VALIDATING), scenario.github.label_history)
