# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The debt an unmeasured publication records, and the write that pays it.

A candidate that skips the reading freezes no generation for itself, so between
the gate letting it through and the push that carries it there is committed
work on the branch and, without this, nothing on the issue naming it. The
measured road records that debt beside its retirement; these pin down that the
unmeasured roads -- an adjudication's exemption, a supersession the switch let
past -- record it too.

Both sides of the push are here because the windows are different. Before the
settlement write the branch may already be on the remote with nothing saying
so, and the debt is the whole of what a later tick has to go on. After it, the
receipt and the route's own bookkeeping are already durable and only the
caller's tail is missing.

The receipt is what makes the second window easy to miss: it is never cleared,
so a branch that has been on the remote before arrives with it already naming
the commit in hand. It says nothing about the round behind this push, and the
debt recorded ahead of the push is what the settlement reads instead.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.fixtures import _authorized_exemption
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)
from tests.workflow.stages.fixing.test_late_dispatch import (
    _FrozenPairMixin,
)

ISSUE = fixing.ISSUE
PR_NUMBER = fixing.PR_NUMBER
PR_HEAD_SHA = fixing.PR_HEAD_SHA
PUSH_BRANCH = fixing.PUSH_BRANCH
REVIEW_ROUND = fixing.REVIEW_ROUND
PENDING_FIX_AT = fixing.PENDING_FIX_AT
VALIDATING = fixing.VALIDATING
patch = fixing.patch

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
_SizeGateFixtureMixin = support._SizeGateFixtureMixin
config = fixing.config

PUBLICATION_PAID = "_publication_paid"
TICK_DIED = "the tick died around the settlement"

KEY_SPENDS = "late_spends"

# What the in_review fix route leaves `review_round` at: reset to zero, since
# the round before the fix is the one the reviewer approved.
SPENT_ROUND = 0

# What the seed carries before the push, so a round that never reached the
# comment is told from one that did.
UNSPENT_ROUND = 1


class _DiesAroundTheSettlement:
    """A tick that stops on one side or the other of the receipt's write.

    `settling` says whether that write runs first, which is what tells the two
    windows apart: the push has landed either way, and what differs is whether
    anything on the pinned comment says so.
    """

    def __init__(self, *, settling: bool) -> None:
        self._paid = _late_push._publication_paid
        self._settling = settling

    def __call__(self, gate, published, unproven) -> None:
        if self._settling:
            self._paid(gate, published, unproven)
        raise RuntimeError(TICK_DIED)


class UnmeasuredDebtTest(unittest.TestCase, _SizeGateFixtureMixin):
    """What an unmeasured push leaves behind on each side of its own write."""

    def test_the_debt_goes_down_before_the_push(self) -> None:
        # The window the reviewer of a crashed tick has nothing else to read:
        # the branch is on the remote and the settlement never ran. With no
        # generation frozen and no debt recorded, the next tick finds an issue
        # with nothing owed and runs the stage -- spawning an agent over work
        # nobody can say is unpublished. The debt is what it reads instead.
        scenario = self._exempt_publication()

        self._crashes(scenario, settling=False)

        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(pinned[support.KEY_APPROVED_LEASE], PR_HEAD_SHA)

    def test_the_debt_carries_what_the_route_owed(self) -> None:
        # The recovery has no run behind it to re-derive a reviewer round or a
        # consumed fix batch from, so the obligations ride the same write the
        # debt does and are spent by the push that pays it.
        scenario = self._exempt_publication()

        self._crashes(scenario, settling=False)

        self.assertIn(
            [REVIEW_ROUND, SPENT_ROUND], self._pinned(scenario)[KEY_SPENDS],
        )

    def test_the_settlement_closes_the_debt(self) -> None:
        # The far side of the same write: the receipt names what reached the
        # remote, the debt is gone because it is paid, and what the route owed
        # is on the comment rather than waiting for the caller's own write.
        scenario = self._exempt_publication()

        self._crashes(scenario, settling=True)

        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )
        # And the publication it went onto, which neither the commit nor the
        # head it replaced says: without it the recovery behind this has no
        # identity to prove and a branch to search instead.
        self.assertEqual(pinned[support.KEY_RECEIPT_PR], PR_NUMBER)
        self.assertIsNone(pinned[support.KEY_APPROVED_SHA])
        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)
        self.assertIsNone(pinned[PENDING_FIX_AT])

    def test_an_uncrashed_push_hands_the_issue_on(self) -> None:
        # What says the two crashes above are about the window rather than
        # about the publication refusing to finish: unmeasured, pushed, the
        # round closed, and the reviewer given the head it was told about.
        scenario = self._exempt_publication()

        mocks = self._run_fix_round(scenario)

        mocks[support.COUNT_ADDED_LINES].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(self._pinned(scenario)[REVIEW_ROUND], SPENT_ROUND)
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)

    def _crashes(self, scenario, *, settling: bool) -> None:
        """Kill the tick on one side of the write the receipt rides."""
        with patch.object(
            _late_push, PUBLICATION_PAID,
            _DiesAroundTheSettlement(settling=settling),
        ), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario)

    def _exempt_publication(self):
        """A fix round publishing a commit an adjudication already accepted.

        Nothing measures it and no generation is frozen for it, so the debt
        this records is the only account of the work between the gate and the
        push. The pull request is standing somewhere else, which is what makes
        this push an event with a window rather than a republication of one
        the remote already has.

        The receipt already names the commit, because it is never cleared and
        this branch has been on the remote before. On its own it says nothing
        about the round behind THIS push, so a settlement that read it as
        "nothing left to close" would leave that round for the caller's write
        a tick's work later.
        """
        return self._seed_fix_round(**{
            **_authorized_exemption(),
            **support.receipt_group(
                MEASURED_CANDIDATE_SHA,
                lease=PR_HEAD_SHA,
                pull_request=PR_NUMBER,
            ),
            REVIEW_ROUND: UNSPENT_ROUND,
        })


class SwitchedOffDebtTest(unittest.TestCase, _SizeGateFixtureMixin):
    """The same debt where the switch keeps the candidate out of the gate.

    Nothing freezes a publication there: no pull request is read and this
    owner establishes no head of its own. The push still MOVES one all the
    same -- the caller read the head it is replacing and the force-push is
    pinned to it -- so the window between that push and the receipt is the
    window every other unmeasured publication has, and the debt is recorded
    against the caller's own lease. What `DECOMPOSE=off` decides is the
    measurement; the account of what a push is putting where is not its to
    turn off.
    """

    def test_the_debt_goes_down_before_the_push(self) -> None:
        scenario = self._seed_fix_round(**{REVIEW_ROUND: UNSPENT_ROUND})

        with patch.object(config, support.DECOMPOSE, False):
            self._crashes(scenario, settling=False)

        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(pinned[support.KEY_APPROVED_LEASE], PR_HEAD_SHA)
        self.assertIn([REVIEW_ROUND, SPENT_ROUND], pinned[KEY_SPENDS])

    def test_the_switch_still_reads_nothing(self) -> None:
        # What says the debt is not the gate creeping back in: no pull request
        # is measured, and the push goes out named against the checkout and
        # pinned to the head the round began at.
        scenario = self._seed_fix_round(**{REVIEW_ROUND: UNSPENT_ROUND})

        with patch.object(config, support.DECOMPOSE, False):
            mocks = self._run_fix_round(scenario)

        mocks[support.COUNT_ADDED_LINES].assert_not_called()
        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], PR_HEAD_SHA)

    _crashes = UnmeasuredDebtTest._crashes


class UnmeasuredDebtRetryTest(
    unittest.TestCase, _SizeGateFixtureMixin, _FrozenPairMixin,
):
    """The tick after the one that pushed and recorded nothing else."""

    def test_the_retry_publishes_it_first(self) -> None:
        # The reconciliation ahead of every handler finds the debt and
        # republishes the same commit against the same head -- BEFORE the
        # stage runs, which is the whole point: without it the stage reads an
        # issue that has published nothing, resumes a developer over the head
        # the pull request already has, and hands the gate a commit whose two
        # readings of that publication no longer agree.
        scenario = self._crashed_before_the_settlement()

        mocks = self._route_to_the_stage(
            scenario.github, scenario.github.get_issue(ISSUE),
        )

        first = mocks[PUSH_BRANCH].call_args_list[0]
        self.assertEqual(first.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(first.kwargs[LEASE], PR_HEAD_SHA)

    def test_the_retry_closes_what_the_debt_carried(self) -> None:
        # And the recovery closes it: the receipt names what reached the
        # remote, the debt is gone, and the round the dead tick spent is
        # counted once rather than left for a stage that cannot re-derive it.
        scenario = self._crashed_before_the_settlement()

        self._route_to_the_stage(
            scenario.github, scenario.github.get_issue(ISSUE),
        )

        pinned = self._pinned(scenario)
        self.assertEqual(
            pinned[support.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertIsNone(pinned[support.KEY_APPROVED_SHA])
        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)

    def _crashed_before_the_settlement(self):
        """One tick that pushed and died before it recorded anything."""
        scenario = self._exempt_publication()
        self._crashes(scenario, settling=False)
        return scenario

    _crashes = UnmeasuredDebtTest._crashes
    _exempt_publication = UnmeasuredDebtTest._exempt_publication


if __name__ == "__main__":
    unittest.main()
