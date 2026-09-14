# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a process that is gone observed, and this one has to finish.

A latch is memory. It covers every observation the process holding it makes --
the run in flight asks it before every step the remote keeps -- and it covers
nothing at all once that process dies. So the poll that latches a close also
writes it down, as a marked comment on the issue thread: append-only, which is
the whole reason it is a comment rather than a pinned write, since the pinned
comment is written whole and a second writer racing the worker that owns the
issue would drop whatever that worker recorded in between.

What the tick after a restart therefore finds is an issue a human reopened, a
record still saying the cycle is live, nothing in memory -- and a thread that
remembers. Adopting that receipt is the whole of this module, along with the
two things that keep the adoption from costing more than it is worth: it is
scoped to the cycle it was written for, and the thread is walked once per
owner per process.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.observation_support import ObservedCloseCase, receipt_for
from tests.workflow.stages.decomposition.late_cleanup_support import (
    CYCLE_ID,
    PARENT_NUMBER,
    STATE_RECONCILED,
    SUPERSEDED_BRANCH,
    OwnerSeed,
    SeededUmbrella,
    resource_states,
    split_umbrella,
)
from tests.workflow.stages.decomposition.late_route_support import (
    routed_owner,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS

_WORKFLOW_LOG = "orchestrator.workflow"

_RETIRED = ((PARENT_NUMBER, WorkflowLabel.REJECTED),)

# What the fake answers with when the request behind a listing fails outright.
_OUTAGE = ConnectionError("github unreachable")


class InheritedCloseTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """What the process after a restart has instead of the latch.

    The whole race, end to end and across a process boundary: a poll observed
    the close and wrote the receipt, a human reopened the issue, and the
    process died before any pass reconciled it. The fresh one wakes to an open
    issue whose own record still says the cycle is live -- and to a thread
    that remembers.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_no_handler_runs_over_an_adopted_close(self) -> None:
        seeded = self._observed_and_reopened()

        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        dispatched.assert_not_called()
        self.assertTrue(_record(seeded)[KEYS.cancelled])

    def test_the_ending_runs_from_the_adopted_mark(self) -> None:
        seeded = self._observed_and_reopened()

        with self.assertLogs(_WORKFLOW_LOG):
            routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [SUPERSEDED_BRANCH],
        )
        self.assertEqual(
            resource_states(seeded.github)[SUPERSEDED_BRANCH],
            STATE_RECONCILED,
        )
        self.assertEqual(tuple(seeded.github.label_history), _RETIRED)

    def _observed_and_reopened(self) -> SeededUmbrella:
        """A live cycle a dead process observed closed, reopened since."""
        seeded = _live_owner()
        seeded.github.comment(
            seeded.parent, receipt_for(PARENT_NUMBER, CYCLE_ID),
        )
        return seeded


class InheritedCloseCostTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """What keeps the recovery from costing more than it recovers.

    A receipt is scoped to the cycle it was written for, and the thread it
    sits on is walked once per owner per process. Without the first, a close
    observed before a restart would end the fresh cycle an operator
    authorized afterwards; without the second, every late owner would pay a
    thread walk every tick for a reading only a dead process could have left.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_a_thread_with_no_receipt_dispatches(self) -> None:
        # The baseline the adoption is measured against, and the reason the
        # scan may be spent at all: an owner nobody observed closed is
        # ordinary work.
        seeded = _live_owner()

        dispatched = routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        dispatched.assert_called_once()
        self.assertFalse(_record(seeded).get(KEYS.cancelled))

    def test_another_cycle_s_receipt_is_not_this(self) -> None:
        # An operator authorizes a restart by taking `rejected` off, and the
        # attempt that follows mints a fresh cycle. A receipt scoped to the
        # cycle it was written for is what keeps the old close from ending
        # the new one.
        seeded = _live_owner()
        seeded.github.comment(
            seeded.parent, receipt_for(PARENT_NUMBER, CYCLE_ID + 1),
        )

        dispatched = routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        dispatched.assert_called_once()
        self.assertFalse(_record(seeded).get(KEYS.cancelled))

    def test_the_thread_is_walked_once_per_process(self) -> None:
        # What keeps the recovery off the wire in the steady state: what it
        # looks for is an observation a DEAD process was holding, and every
        # observation this one makes is in the latch, which costs nothing.
        seeded = _live_owner()
        walked = _CountedComments(seeded.github)

        with walked.counting():
            routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)
            first = walked.calls
            routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        self.assertEqual(first, 1)
        self.assertEqual(walked.calls, 1)


def _live_owner() -> SeededUmbrella:
    """An open owner whose record says its cycle is still running."""
    return split_umbrella(
        LateResourceState.PENDING,
        owner=OwnerSeed(
            label=WorkflowLabel.DECOMPOSING,
            closed=False,
            cancelled=False,
            child=False,
        ),
    )


def _record(seeded: SeededUmbrella) -> dict:
    """What this owner's own pinned comment says right now."""
    return seeded.github.pinned_data(PARENT_NUMBER)


class FailedReceiptScanTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """A scan that could not be taken has to be taken again.

    The claim is what stops the walk repeating every tick, and it is only
    honest once the walk has answered. A listing that raises established
    nothing, so a claim left standing over it would send every later tick
    straight past the receipt and on to the live stage handler -- which is
    the one thing the receipt exists to prevent.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _live_owner()
        self.seeded.github.comment(
            self.seeded.parent, receipt_for(PARENT_NUMBER, CYCLE_ID),
        )

    def test_the_failed_tick_dispatches_nothing(self) -> None:
        with self.assertRaises(ConnectionError):
            self._routed(outage=True)

        self.assertFalse(_record(self.seeded).get(KEYS.cancelled))

    def test_the_next_tick_takes_the_scan_again(self) -> None:
        with self.assertRaises(ConnectionError):
            self._routed(outage=True)

        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = self._routed()

        dispatched.assert_not_called()
        self.assertTrue(_record(self.seeded)[KEYS.cancelled])

    def _routed(self, *, outage: bool = False) -> Mock:
        """Route this owner, the thread walk answering or refusing."""
        if not outage:
            return routed_owner(
                self, self.seeded, WorkflowLabel.DECOMPOSING,
            )
        with patch.object(
            self.seeded.github, "comments_after", side_effect=_OUTAGE,
        ):
            return routed_owner(
                self, self.seeded, WorkflowLabel.DECOMPOSING,
            )


class _CountedComments:
    """Count the thread walks the receipt scan makes, and pass them through."""

    def __init__(self, github) -> None:
        self._github = github
        self._listing = github.comments_after
        self.calls = 0

    def __call__(self, issue, after_id):
        """Answer one listing, and remember that it was asked for."""
        self.calls += 1
        return self._listing(issue, after_id)

    def counting(self):
        """Put this in front of every thread walk the guard takes."""
        return patch.object(
            self._github, "comments_after", side_effect=self,
        )


if __name__ == "__main__":
    unittest.main()
