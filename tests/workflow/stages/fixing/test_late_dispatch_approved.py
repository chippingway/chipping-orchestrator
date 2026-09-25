# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push an approving tick could not land, finished by the next one.

The write that approves a small candidate retires the generation it was frozen
under, deliberately and before the push it licenses runs. A push that then
MISSES leaves three things behind and no tick able to use them: an approval
naming the commit, the route bookkeeping that approval carried past its own
retirement, and a park whose stage short-circuits on it before any handler
reads a thing.

So the reconciliation ahead of every handler is what finishes all three. It
publishes the commit the approval names, closes what the caller's own tail
would have closed, and releases the park the failed push left -- and where the
push misses again it does none of that and says nothing, because a mention
nobody can answer any faster is churn and a rewritten reason is a transient
park turned into one only a human clears.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.support.publication import LandingPush
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)
from tests.workflow.stages.fixing.test_late_dispatch import (
    _FrozenPairMixin,
)
from tests.workflow.stages.fixing.test_late_dispatch_spends import (
    CONSUMED_BATCH,
    ROUND_SPENT,
    _DiesPastTheReceipt,
    _pinned,
)
from tests.workflow.stages.fixing.test_published_gate_receipts import (
    _CrashesOnceTheReceiptIsWritten,
)

ISSUE = fixing.ISSUE
PUSH_BRANCH = fixing.PUSH_BRANCH
AWAITING_HUMAN = fixing.AWAITING_HUMAN
PARK_REASON = fixing.PARK_REASON
PARK_PUSH_FAILED = fixing.PARK_PUSH_FAILED

MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
KEY_APPROVED_SHA = support.KEY_APPROVED_SHA
KEY_APPROVED_LEASE = support.KEY_APPROVED_LEASE
KEY_RECEIPT_SHA = support.KEY_RECEIPT_SHA
PARK_CANDIDATE_MOVED = support.PARK_CANDIDATE_MOVED

KEY_REVIEW_ROUND = "review_round"
KEY_PENDING_FIX_AT = "pending_fix_at"
KEY_PENDING_COMMENT = "pending_fix_reviewer_comment_id"

# The world the retry ticks below read once their push has landed: the
# checkout standing on the commit that went out, and the remote carrying it.
# Stated rather than defaulted because these ticks are asked to prove it --
# the stage behind the retry re-reads the branch before it hands anything on
# -- and a world that never modelled the push's effect on the remote would
# answer that question with a refusal the retry has already healed.
_PUBLISHED_WORLD = MappingProxyType({
    "head_shas": (MEASURED_CANDIDATE_SHA,),
    "fetched_branch_tip": MEASURED_CANDIDATE_SHA,
})

PUBLICATION_PAID = "_publication_paid"
WRITE_PINNED_STATE = "write_pinned_state"
# A checkout that could not name its own head at all, which the post-push
# proof refuses on exactly as it refuses one that moved.
CANDIDATE_UNREADABLE = MeasurementFailure.CANDIDATE_UNREADABLE

# A tree clean when the push is decided and dirty on the far side of it,
# and one still dirty when the tick after the crash reads it. Clean FOUR
# times before the push: a reported round asks the checkout for itself, the
# branch-placement probe asks again, and the publication road proves it once
# more before it pushes -- all three before the gate does, since a tree this
# host proves is carrying something is a refusal no road here publishes over
# and the terminal park is that round's own.
STRAY_FILE = "stray.py"
_CLEAN = support._WorktreeStatus(readable=True, paths=())
_DIRTY = support._WorktreeStatus(readable=True, paths=(STRAY_FILE,))
_DIRTIED = (_CLEAN, _CLEAN, _CLEAN, _CLEAN, _DIRTY)
_STILL_DIRTY = (_DIRTY,)
RUN_AGENT = "run_agent"
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"


# What a run resumed on an existing session names it by.
_RESUMED_SESSION = "resume_session_id"


def _resumed_sessions(mocks) -> list:
    """The sessions an agent was resumed on, in the order they ran."""
    return [
        called.kwargs[_RESUMED_SESSION]
        for called in mocks[RUN_AGENT].call_args_list
        if called.kwargs.get(_RESUMED_SESSION)
    ]


class ReceiptCarriedRoundTest(unittest.TestCase, _FrozenPairMixin):
    """The window between a landed push and the write its caller still owes.

    The relabel is already out and the caller has a pinned write left to make;
    past the receipt there is no approval and no generation, so nothing on the
    comment could tell a later tick what the route was part-way through. So
    the round and the batch ride the receipt's own write -- and the tick that
    comes back reads a publication the pull request already carries, counts
    nothing more, and replays no feedback.

    The rounds here republish a commit an earlier one stranded under a reply
    that wrote no report, because that is the road where the route's
    bookkeeping is the gate's to carry: a round that REPORTS freezes the same
    pair onto that report's record, for the write that publishes it.
    """

    def test_the_receipt_carries_the_round_it_landed(self) -> None:
        # The window the reviewer's own chain runs through: the push lands and
        # the caller's write -- the relabel's own -- never does. Past that
        # write there is no approval and no generation, so nothing on the
        # comment could tell a later tick what the route still owed. Carried
        # by the receipt instead, the round and the batch are already down
        # when the crash happens.
        scenario = self._seed_fix_round(**CONSUMED_BATCH)
        github = scenario.github
        crashing = _CrashesOnceTheReceiptIsWritten(github.write_pinned_state)

        with patch.object(github, WRITE_PINNED_STATE, crashing), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario)

        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_FIX_AT])
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])

    def test_the_tick_after_that_crash_counts_nothing(self) -> None:
        # And the chain's other half: the tick that comes back reads a
        # publication the pull request already carries, so it sends nothing
        # new and counts no second round for the one fix that landed. Counted
        # twice, `MAX_REVIEW_ROUNDS` stops meaning what it says on exactly the
        # issues a crash has been through.
        github = self._crashed_past_the_receipt()
        landed = _pinned(github)[KEY_REVIEW_ROUND]

        self._run_the_stage(github)

        self.assertEqual(_pinned(github)[KEY_REVIEW_ROUND], landed)

    def test_the_tick_after_that_crash_reruns_no_dev(self) -> None:
        # The bookmarks the crashed tick consumed went down with its receipt,
        # so the route behind this one finds no batch to replay: what runs is
        # the reviewer over the head that landed, not the developer over
        # feedback it has already answered.
        crashed = self._crashed_past_the_receipt()

        mocks = self._run_the_stage(crashed)

        self.assertEqual(_resumed_sessions(mocks), [])
        replayed = _pinned(crashed)
        self.assertIsNone(replayed[KEY_PENDING_FIX_AT])
        self.assertIsNone(replayed[KEY_PENDING_COMMENT])
        self.assertIsNone(replayed[KEY_APPROVED_SHA])

    def _crashed_past_the_receipt(self):
        """The comment a tick that died on the write past its receipt left."""
        scenario = self._seed_fix_round(**CONSUMED_BATCH)
        github = scenario.github
        crashing = _CrashesOnceTheReceiptIsWritten(github.write_pinned_state)

        with patch.object(github, WRITE_PINNED_STATE, crashing), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario)
        return github

    def _run_the_stage(self, github):
        """One dispatched tick, with the real fixing handler behind it."""
        return self._route_to_the_stage(github, github.get_issue(ISSUE))

    _seed_fix_round = support._SizeGateFixtureMixin._seed_fix_round
    _run_fix_round = support._SizeGateFixtureMixin._run_stranded_round
    _seed = support._SizeGateFixtureMixin._seed
    _open_pr = support._SizeGateFixtureMixin._open_pr


class _RacedCheckoutMixin(_FrozenPairMixin):
    """One push that landed onto a checkout something moved under it."""

    def _raced(self, *, crashing: bool = False, **run_options):
        """A push that landed onto a checkout something moved under it."""
        scenario = self._seed_fix_round()
        github = scenario.github
        # The push lands, so the pull request stands on what it published and
        # the retry reads a publication that is over.
        run_options["push_branch"] = LandingPush(github, fixing.PR_NUMBER)
        if not crashing:
            self._run_fix_round(scenario, **run_options)
            return github
        stopped = _CrashesOnceTheReceiptIsWritten(github.write_pinned_state)
        with patch.object(github, WRITE_PINNED_STATE, stopped), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario, **run_options)
        return github

    def _run_the_stage(self, github, **run_options):
        """One dispatched tick, with the real fixing handler behind it."""
        return self._route_to_the_stage(
            github, github.get_issue(ISSUE), **run_options,
        )

    _seed_fix_round = support._SizeGateFixtureMixin._seed_fix_round
    _run_fix_round = support._SizeGateFixtureMixin._run_fix_round
    _seed = support._SizeGateFixtureMixin._seed
    _open_pr = support._SizeGateFixtureMixin._open_pr


class RestoredCheckoutRetryTest(unittest.TestCase, _RacedCheckoutMixin):
    """The tick after a checkout race, once the worktree is back.

    A push that landed onto a checkout something moved or dirtied leaves the
    publication standing and the HANDOFF stopped: the branch is on the remote,
    the label has not moved, and the issue is parked naming the commit the
    checkout has to go back to. What finishes it is this reconciliation --
    which needs the record to be a whole approval, since a commit with no head
    to pin it against is not a debt it can pay but a claim it refuses as
    damage, under a reason only a human clears.
    """

    def test_a_moved_checkout_finishes_once_restored(self) -> None:
        # The documented retry: put the checkout back and the branch publishes
        # on the next poll with nothing re-run. Recorded as half an approval
        # instead, the tick that comes back reads the record as damage and
        # replaces the recoverable park with one that waits for a human.
        github = self._raced(candidate_commit=(
            support.FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
            support.FrozenCommit(sha=support.MOVED_AFTER_PUSH),
        ))

        self._run_the_stage(github, **_PUBLISHED_WORLD)

        self._assert_finished(github)

    def test_a_dirty_checkout_finishes_once_restored(self) -> None:
        # The other half of the same proof. Uncommitted work beside the
        # published commit stops the handoff the same way, and a tree that is
        # clean again is the same repair.
        github = self._raced(tree_states=_DIRTIED)

        self._run_the_stage(github, **_PUBLISHED_WORLD)

        self._assert_finished(github)

    def test_a_race_records_a_debt_and_not_damage(self) -> None:
        # What the retry turns on, read off the comment the raced tick left:
        # the pair a reconciliation may act on, under the park an operator can
        # answer by restoring the worktree.
        raced = _pinned(self._raced(tree_states=_DIRTIED))

        self.assertEqual(raced[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(raced[KEY_APPROVED_LEASE], MEASURED_CANDIDATE_SHA)
        self.assertEqual(raced[PARK_REASON], PARK_CANDIDATE_MOVED)

    def _assert_finished(self, github) -> None:
        """The debt is paid, the park released, and the handler run behind."""
        finished = github.pinned_data(ISSUE)
        self.assertIsNone(finished[KEY_APPROVED_SHA])
        self.assertIsNone(finished[KEY_APPROVED_LEASE])
        self.assertEqual(finished[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertFalse(finished[AWAITING_HUMAN])
        self.assertIsNone(finished[PARK_REASON])
        self.assertIn((ISSUE, fixing.VALIDATING), github.label_history)


class ApprovedRetryEndToEndTest(unittest.TestCase, _FrozenPairMixin):
    """A push the approving tick could not land, finished by the next one.

    The write that approves a small candidate retires the generation it was
    frozen under and the push it licenses runs after -- so a push that misses
    leaves an approval, a park, and a caller that returns to a stage whose
    first act is to short-circuit on that park. Nothing behind that tick goes
    back for what its route was part-way through, which is why the approval
    carries it and the retry that lands the commit closes it.

    The rounds here republish a commit an earlier one stranded under a reply
    that wrote no report, because that is the road where the route's
    bookkeeping is the gate's to carry: a round that REPORTS freezes the same
    pair onto that report's record, for the write that publishes it.
    """

    def test_the_retry_closes_the_round_it_owed(self) -> None:
        # The round this fix spends and the batch it consumed were frozen with
        # the pair and would have been closed by the caller's own tail. That
        # tail never ran: its push failed. Left uncounted, the in_review
        # re-entry behind this correlates the same triggering comments again
        # and reruns a developer over feedback that was already answered.
        github = self._approved_but_unpushed()

        self._run_the_stage(github)

        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_FIX_AT])
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])

    def test_the_retry_releases_the_park_it_healed(self) -> None:
        # The park says a push failed, and this tick is that push succeeding.
        # Left standing, the stage below short-circuits on it every poll and
        # the issue waits on a human for a failure that has already healed.
        github = self._approved_but_unpushed()

        self._run_the_stage(github, **_PUBLISHED_WORLD)

        pinned = _pinned(github)
        self.assertFalse(pinned[AWAITING_HUMAN])
        self.assertIsNone(pinned[PARK_REASON])
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)

    def test_the_retry_publishes_what_was_approved(self) -> None:
        # Named against the commit the approval is for and pinned to the head
        # it was measured over, since nothing measures it a second time.
        github = self._approved_but_unpushed()

        mocks = self._run_the_stage(github)

        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], fixing.PR_HEAD_SHA)

    def test_a_second_miss_leaves_the_park_alone(self) -> None:
        # A push that keeps missing is the ordinary way to reach this twice.
        # A fresh mention there is one nobody can answer any faster, and
        # rewriting the reason would replace a transient park the stage
        # recoveries retry with one only a human clears.
        github = self._approved_but_unpushed()
        announced = len(github.get_issue(ISSUE).comments)

        dispatched, mocks = self._route(
            github, github.get_issue(ISSUE), push_branch=False,
        )

        dispatched.assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(github.get_issue(ISSUE).comments), announced)
        pinned = _pinned(github)
        self.assertEqual(pinned[PARK_REASON], PARK_PUSH_FAILED)
        self.assertEqual(pinned[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def test_a_crash_past_the_receipt_still_closes(self) -> None:
        # The retry has no caller behind it either, so what it owes rides the
        # receipt's own write: a process dying between the two would come back
        # to a published commit, a paid debt, and a round nothing says was
        # owed.
        github = self._approved_but_unpushed()

        with patch.object(
            _late_push, PUBLICATION_PAID, _DiesPastTheReceipt(),
        ), self.assertRaises(RuntimeError):
            self._run_the_stage(github)

        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertFalse(pinned[AWAITING_HUMAN])

    def _approved_but_unpushed(self):
        """The pinned comment a fix round whose push missed leaves behind."""
        scenario = self._seed_fix_round(**CONSUMED_BATCH)
        self._run_fix_round(scenario, push_branch=False)
        pinned = _pinned(scenario.github)
        self.assertEqual(pinned[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[PARK_REASON], PARK_PUSH_FAILED)
        return scenario.github

    def _run_the_stage(self, github, **run_options):
        """One dispatched tick, with the real fixing handler behind it."""
        return self._route_to_the_stage(
            github, github.get_issue(ISSUE), **run_options,
        )

    _seed_fix_round = support._SizeGateFixtureMixin._seed_fix_round
    _run_fix_round = support._SizeGateFixtureMixin._run_stranded_round
    _seed = support._SizeGateFixtureMixin._seed
    _open_pr = support._SizeGateFixtureMixin._open_pr


if __name__ == "__main__":
    unittest.main()


class RacedCheckoutCrashTest(unittest.TestCase, _RacedCheckoutMixin):
    """The crash boundary the post-push proof has to survive.

    The push has landed and the checkout it left is not what went out, so the
    handoff is owed a proof -- and a process dying the moment the receipt is
    durable is what decides whether anything on the comment says so. Written
    one write behind that receipt, this crash takes the claim with it: the
    retry reads a dirty worktree as no stranded fix and relabels to
    `validating`, handing a reviewer a checkout nobody read. Riding the
    receipt's own write, the two land together or not at all.
    """

    def test_a_crash_past_the_receipt_keeps_the_claim(self) -> None:
        # The crash boundary the proof has to survive. The push has landed and
        # the checkout it left is not what went out, so the handoff is owed a
        # proof -- and a process dying the moment the receipt is durable is
        # what decides whether anything on the comment says so. Written one
        # write behind that receipt, this crash takes the claim with it: the
        # retry reads a dirty worktree as no stranded fix and relabels to
        # `validating`, handing a reviewer a checkout nobody read. Riding the
        # receipt's own write, the two land together or not at all.
        raced = _pinned(self._raced(crashing=True, tree_states=_DIRTIED))

        self.assertEqual(raced[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(raced[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(raced[KEY_APPROVED_LEASE], MEASURED_CANDIDATE_SHA)

    def test_a_crash_past_an_unreadable_head_keeps_it(self) -> None:
        # The other evidence the same proof refuses on: a checkout that could
        # not name its own head at all. It owes the same claim, and the same
        # crash must not be what loses it.
        raced = _pinned(self._raced(crashing=True, candidate_commit=(
            support.FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
            support.FrozenCommit(failure=CANDIDATE_UNREADABLE),
        )))

        self.assertEqual(raced[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(raced[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def test_the_retry_hands_nothing_on(self) -> None:
        # And what the claim buys. The tick that comes back republishes as the
        # leased no-op the remote already carries, re-proves a checkout that is
        # still dirty, and stops there. With nothing owed it would run the
        # stage instead and the reviewer would get the branch.
        crashed = self._raced(crashing=True, tree_states=_DIRTIED)

        self._run_the_stage(crashed, tree_states=_STILL_DIRTY)

        self.assertNotIn((ISSUE, fixing.VALIDATING), crashed.label_history)
        self.assertEqual(
            _pinned(crashed)[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )
