# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reclamation has to prove, and what it leaves on the children.

Two halves of one transaction. A delete is ordered on the record before it is
carried out, so a retry can finish one the remote already took -- but that
record buys the retry nothing about a ref the remote still has, which a child
reopened since may still be cutting from. And a delete that lands is not over
until every child cut from the ref has been told, because there may be no
later pass: an umbrella that settles everything closes as `done`, and nothing
revisits a `done` issue.

Told is a COMMENT and nothing else. This owner may not write a consumer's
pinned comment -- that is written whole by whoever writes it, and a handler of
the child's own would lose or undo whatever landed second. A comment is
appended, so nobody can lose it, and what acts on it is the child's own guard,
evaluated on the child's own dispatch (`test_late_reuse.py`).

Driven through the umbrella's real terminal, which is the entry that reaches
both on the ordinary path.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.late_split.models import LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_cleanup as _late_cleanup,
)
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    GENERATION_NUMBER,
)

_DELETED = _snapshot_refs.SnapshotOutcome.DELETED

_ABSENT = _snapshot_refs.SnapshotOutcome.ABSENT

_WORKFLOW_LOG = "orchestrator.workflow"

_ANCESTRY_REF = "late_ancestry_snapshot_ref"

_ANCESTRY_SHA = "late_ancestry_snapshot_sha"

_PARKED = "awaiting_human"

# The decision-recording step, captured before any case replaces it.
_REAL_ORDERED = _late_cleanup._ordered

def _reclaiming():
    """An umbrella whose branch is settled and whose ref is about to go."""
    return _support.split_umbrella(
        LateResourceState.RECONCILED,
        snapshot=LateResourceState.RETAINED,
        owner=OwnerSeed(),
    )


def _reopened(ordered: LateResourceState):
    """An owner whose ref is already ordered, whose one child is open again."""
    return _support.split_umbrella(
        LateResourceState.RECONCILED,
        snapshot=ordered,
        owner=OwnerSeed(child_closed=False),
    )


def _walk_with(case, seeded, outcome, **answers) -> RecordedDelete:
    """Run the umbrella terminal with the remote answering `outcome`."""
    deleted = RecordedDelete(outcome, **answers)
    with deleted.answering():
        _support.walk_owner(case, seeded)
    return deleted


class _ReleaseCase(_PatchedWorkflowMixin):
    """What every case here asks of the one consumer afterwards."""

    def assert_told_once(self, seeded) -> None:
        """The child was told once, and its own record was not touched.

        Both halves matter. The sentence has to reach it, and the pinned
        comment has to be exactly as its own handlers left it -- an owner that
        wrote there would be racing a writer it cannot see.
        """
        self.assertEqual(len(self.told(seeded)), 1)
        self.assert_untouched(seeded)

    def assert_untouched(self, seeded) -> None:
        """The child's pinned comment is as the split left it."""
        child_state = seeded.github.pinned_data(_support.CHILD_NUMBER)
        self.assertEqual(child_state[_ANCESTRY_REF], _support.SNAPSHOT_REF)
        self.assertIn(_ANCESTRY_SHA, child_state)
        self.assertFalse(child_state.get(_PARKED))

    def reopening_on_order(self, seeded):
        """Reopen the consumer the instant the decision is recorded.

        The window the race lives in, injected at the one statement that opens
        it: by then the pass has qualified the ref against the scan it started
        with, and the write that records the decision is a request of its own
        for a human to act during.
        """
        return patch.object(
            _late_cleanup, "_ordered", partial(self._order_then_reopen, seeded),
        )

    def told(self, seeded) -> list:
        """Every comment this pass has posted on the one consumer."""
        return [
            body for number, body in seeded.github.posted_comments
            if number == _support.CHILD_NUMBER
        ]


    def _order_then_reopen(self, seeded, walk, generation, ref):
        """Record the decision as the owner does, then reopen the child."""
        recorded = _REAL_ORDERED(walk, generation, ref)
        seeded.github.get_issue(_support.CHILD_NUMBER).closed = False
        return recorded


class ToldConsumerTest(_ReleaseCase, unittest.TestCase):
    """A child cut from a reclaimed ref is told, and nothing else is done."""

    def test_a_reclaimed_ref_is_said_once(self) -> None:
        seeded = _reclaiming()

        _walk_with(self, seeded, _DELETED)

        self.assert_told_once(seeded)
        self.assertIn(str(_support.PARENT_NUMBER), self.told(seeded)[0])

    def test_the_receipt_names_this_reclamation(self) -> None:
        # Scoped to the owner, the cycle, and the generation, so a consumer of
        # a later reclamation is not read as told by an earlier one's receipt.
        seeded = _reclaiming()

        _walk_with(self, seeded, _DELETED)

        self.assertIn(
            f"owner={_support.PARENT_NUMBER} cycle={CYCLE_ID} "
            f"generation={GENERATION_NUMBER}",
            self.told(seeded)[0],
        )

    def test_a_refused_delete_tells_nobody(self) -> None:
        # The sentence would be a lie and the dropped pointer a loss: the ref
        # is still on the remote, and the umbrella stays open retrying it.
        seeded = _reclaiming()

        with self.assertLogs(_WORKFLOW_LOG, level="WARNING"):
            _walk_with(self, seeded, _snapshot_refs.SnapshotOutcome.REFUSED)

        self.assert_untouched(seeded)
        self.assertEqual(self.told(seeded), [])
        self.assertFalse(seeded.parent.closed)


class ReopenedAfterDeletionTest(_ReleaseCase, unittest.TestCase):
    """A child that comes back once its ref is gone is told before it can.

    The two ways it can happen. On the ordinary path the umbrella settles
    everything and closes as `done`, so nothing will ever visit that owner
    again -- the child has to have been told already. And on the crash path
    the delete lands while the record of it does not, so the retry has to
    finish the job against an owner whose consumer is live again.
    """

    def test_a_reopen_after_completion_was_told(self) -> None:
        # The umbrella settled everything and closed as `done`, so nothing will
        # ever visit that owner again. What the child has is the receipt, said
        # while it was still closed -- and what stops it resuming is its own
        # guard, which `test_late_reuse.py` drives through the dispatcher.
        seeded = _reclaiming()
        _walk_with(self, seeded, _DELETED)
        self.assertTrue(seeded.parent.closed)

        seeded.github.get_issue(_support.CHILD_NUMBER).closed = False

        self.assert_told_once(seeded)

    def test_a_death_before_the_record_still_tells(self) -> None:
        # The delete landed and nothing recorded it. The decision was written
        # first, so the retry finishes it against a ref the remote no longer
        # has -- and it is the retry that tells the child, now open again.
        seeded = _reclaiming()
        died = RecordedDelete(_DELETED, raising=KeyboardInterrupt("died"))
        with self.assertRaises(KeyboardInterrupt), died.answering():
            _support.walk_owner(self, seeded)
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECLAIMING,
        )
        self.assertEqual(self.told(seeded), [])
        seeded.github.get_issue(_support.CHILD_NUMBER).closed = False

        _walk_with(self, seeded, _ABSENT, presence=_ABSENT)

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assert_told_once(seeded)

    def test_the_child_is_told_once(self) -> None:
        # The dropped pointer is what bounds the sentence: a retry that has to
        # repeat the release finds a child that names no ref and says nothing.
        seeded = _reclaiming()
        _walk_with(self, seeded, _DELETED)
        told = self.told(seeded)

        _walk_with(self, seeded, _ABSENT)

        self.assertEqual(self.told(seeded), told)
        self.assertEqual(len(told), 1)


class OrderedRetryTest(_ReleaseCase, unittest.TestCase):
    """A decision already recorded still answers to the ref in front of it.

    `reclaiming` and `failed` both say the consumers were proved once, and
    that proof is what a retry cannot reproduce. It buys the retry exactly one
    thing: permission to finish a delete the remote has already taken. A ref
    the remote still holds is a ref a reopened child may still be cutting
    from, and no record of a past decision outranks that.
    """

    def test_a_surviving_ref_re_proves_consumers(self) -> None:
        # The two ways an ordered entry survives its own delete: a crash
        # before the push reached the remote, and a push it refused. Either
        # way the ref is there and the one consumer is open again.
        ordered_states = (
            LateResourceState.RECLAIMING, LateResourceState.FAILED,
        )
        for ordered in ordered_states:
            with self.subTest(ordered=ordered):
                seeded = _reopened(ordered)

                deleted = _walk_with(self, seeded, _DELETED)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(deleted.observed, [_support.SNAPSHOT_REF])
                self.assertEqual(
                    _support.resource_states(seeded.github)[_support.SNAPSHOT_REF],
                    str(ordered),
                )
                self.assertFalse(seeded.parent.closed)
                self.assert_untouched(seeded)

    def test_a_ref_the_remote_lost_is_finished(self) -> None:
        # The same entry, and the only reading that lets the retry act: the
        # delete it records already landed, so what is left is the release it
        # never reached -- and the reopened child is who it is for.
        seeded = _reopened(LateResourceState.RECLAIMING)

        deleted = _walk_with(self, seeded, _ABSENT, presence=_ABSENT)

        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assert_told_once(seeded)

    def test_a_reopen_inside_the_window_keeps_it(self) -> None:
        # The consumer was ended when the pass qualified the ref and is open
        # again by the time the decision is recorded. The reading taken
        # immediately before the delete is the one that decides, so nothing is
        # asked of the remote and the child keeps what it was cut from.
        seeded = _reclaiming()

        with self.reopening_on_order(seeded), self.assertLogs(_WORKFLOW_LOG, level="INFO"):
            deleted = _walk_with(self, seeded, _DELETED)

        self.assertEqual(deleted.refs, [])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECLAIMING,
        )
        self.assertFalse(seeded.parent.closed)
        self.assert_untouched(seeded)

    def test_a_delete_that_raises_is_typed(self) -> None:
        # The transport answers every refusal it can name; one it cannot must
        # not escape a caller that has to record the attempt, or the entry
        # reads owed with no typed failure for an operator to find it by.
        seeded = _reclaiming()

        with self.assertLogs(_WORKFLOW_LOG, level="ERROR"):
            _walk_with(self, seeded, _DELETED, raising=RuntimeError("boom"))

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_FAILED,
        )
        self.assertIn(
            "snapshot_delete_failed",
            [event.get("failure") for event in seeded.github.recorded_events],
        )
        self.assertFalse(seeded.parent.closed)
        self.assertEqual(self.told(seeded), [])


if __name__ == "__main__":
    unittest.main()
