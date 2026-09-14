# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The consumer ledger a cancelled split leaves, and what may read it as final.

The count the transaction writes before its first create is what tells a
partial split from a finished one, and a cancelled loop can never reach it:
the children it did not make are ones nothing is going to make. Left at that,
the ref those children were cut from is one no pass could ever release --
every consumer could end and the proof would still be short of the count -- so
the owner would hold a snapshot, and its terminal with it, forever.

What makes the ledger final rather than short is the cancellation itself:
every exit that reaches it with the mark down is one where the child in hand
was already recorded. Except where an EARLIER attempt could have created one
this walk has not reached, which is the one reading no cancellation may seal
over.

And it is a fact about ONE cycle. The seal is a decomposition key, so the
write that clears late mode leaves it exactly where it was, and the cycle an
operator authorizes next comes up against a register a previous one called
final -- which is why the seal names the cycle it belongs to and is read by
nothing else.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.workflow.late_split import phases as _late_phases, state as _late_state
from orchestrator.workflow.late_split.models import LateResource, LateResourceKind, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_child_records as _late_child_records,
    late_models as _late_models,
    late_sweep as _late_sweep,
    models as _models,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_observation_seams import (
    latches_on_child_read,
)
from tests.workflow.stages.decomposition.late_seam_support import (
    RecordedDelete,
    SnapshotOutcome,
    local_teardown,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    GENERATION_NUMBER,
    LATE_ISSUE_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    KEY_EXPECTED_CHILDREN,
    KEY_RESOURCES,
    KEY_SPLIT_CHILDREN,
    LABEL_REJECTED,
    SNAPSHOT_REF,
    LateSplitCase,
)

_WORKFLOW_LOG = "orchestrator.workflow"

REPO_SLUG = _TEST_SPEC.slug

_KEY_SEALED = "split_ledger_sealed"

_RETAINED = "retained"

# The child a previous attempt of this split already recorded, and the moment
# the cancellation it is read under was taken.
_KNOWN_CHILD = 909

_CANCELLED_AT = "2026-08-24T10:00:00+00:00"

# The fresh attempt an operator authorizes after a cancelled one: the next
# cycle of the same lineage, cut from a ref of its own.
_NEXT_CYCLE = CYCLE_ID + 1

_NEXT_REF = (
    f"refs/orchestrator/late-split/issue-{LATE_ISSUE_NUMBER}"
    f"/cycle-{_NEXT_CYCLE}/gen-{GENERATION_NUMBER}"
)


class _SweptOwnerCase(ObservedCloseCase, LateSplitCase):
    """A cancelled split's owner, closed, swept the way a tick sweeps one."""

    def _swept(self):
        """Run one closed-owner sweep over this cancelled split."""
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), local_teardown():
            _late_sweep._handle_closed_owner_cleanup(
                self.github, _TEST_SPEC, self.issue,
            )
        return remote

    def _resources(self) -> dict:
        """What the owner's ledger now says about each obligation."""
        return {
            entry["target"]: entry["state"]
            for entry in self._pinned()[KEY_RESOURCES]
        }


class SealedLedgerAfterCancellationTest(_SweptOwnerCase, unittest.TestCase):
    """The ref a cancelled split holds is one its own ledger can release.

    The count the transaction wrote before its first create is what tells a
    partial split from a finished one, and a cancelled loop can never reach
    it: the children it did not make are ones nothing is going to make. So the
    loop writes down that its register is FINAL, and the ending judges the
    consumers it actually cut against that -- otherwise the snapshot is held
    and the terminal with it, on a proof no pass could ever complete.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        with self.assertLogs(_WORKFLOW_LOG), latches_on_child_read(
            self.github, REPO_SLUG, self.issue.number,
        ):
            self._transact()
        self.child = self.github.created_child_issues[0]
        self.issue.closed = True

    def test_the_ledger_it_left_is_sealed(self) -> None:
        pinned = self._pinned()

        self.assertTrue(pinned[_KEY_SEALED])
        self.assertEqual(len(pinned[KEY_SPLIT_CHILDREN]), 1)
        self.assertEqual(pinned[KEY_EXPECTED_CHILDREN], len(CHILDREN))

    def test_a_live_consumer_still_holds_the_ref(self) -> None:
        # The seal says the ledger is complete, not that the ref is free: a
        # child still open is a consumer whose reuse the ref exists for.
        with self.assertLogs(_WORKFLOW_LOG):
            deleted = self._swept()

        self.assertEqual(deleted.refs, [])
        self.assertEqual(self._resources()[SNAPSHOT_REF], _RETAINED)

    def test_the_ref_goes_once_that_consumer_ends(self) -> None:
        # And the regression: with the one child this split made terminal,
        # nothing is owed -- so the ref goes and the owner reaches its
        # terminal, where an unsealed ledger would hold both forever.
        with self.assertLogs(_WORKFLOW_LOG):
            self._swept()
        self.child.closed = True

        deleted = self._swept()

        self.assertEqual(deleted.refs, [SNAPSHOT_REF])
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_REJECTED,
        )


class ResumedWalkSealsNothingTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """The one cancellation whose ledger cannot be called final.

    A create is a request and the write recording it is another, so a pass
    that died between them left a child on GitHub with nothing naming it. The
    adoption lookup is what answers that, and until a resumed walk has passed
    the first unrecorded index it has not been asked -- so the ledger stays
    open and the ref stays held on the count, exactly as before.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_a_walk_short_of_the_lookup_seals_nothing(self) -> None:
        context, walk = self._resumed()

        _late_child_records._sealed(context, walk)

        self.assertIsNone(context.state.get(_KEY_SEALED))

    def test_a_walk_past_it_seals(self) -> None:
        # And past it nothing an earlier attempt made is left unnamed: to
        # have created the index after this one, it would have had to record
        # this one, and it did not.
        context, walk = self._resumed()
        walk.past_the_unrecorded()

        with self.assertLogs(_WORKFLOW_LOG):
            _late_child_records._sealed(context, walk)

        self.assertTrue(context.state.get(_KEY_SEALED))

    def _resumed(self):
        """A cancelled cycle, and the resumed walk its loop stopped on."""
        cancelled = replace(
            self.generation.cancel(_CANCELLED_AT), phase=_late_phases.LatePhase.CANCELLING,
        )
        context = _late_models._LateContext(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self.github.read_pinned_state(self.issue),
            generation=cancelled,
        )
        walk = _late_child_records._ChildWalk(
            plan=_models._SplitPlan.start(list(CHILDREN), True),
            known=(_KNOWN_CHILD,),
            snapshot_ref=SNAPSHOT_REF,
            resumed=True,
        )
        return context, walk


class SecondCycleAfterASealedOneTest(_SweptOwnerCase, unittest.TestCase):
    """Two cancellations on one issue, and the seal the first left behind.

    Nothing that ends a generation drops the seal: it is a decomposition key,
    so the write that clears late mode leaves it exactly where it was. The
    cycle an operator authorizes next therefore begins against a register a
    previous one called FINAL -- and its own split, stopped mid-loop on a
    resumed walk that may seal nothing of its own, would have that stale word
    release the ref its unrecorded children were cut from.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        with self.assertLogs(_WORKFLOW_LOG), latches_on_child_read(
            self.github, REPO_SLUG, self.issue.number,
        ):
            self._transact()
        self.child = self.github.created_child_issues[0]
        self.issue.closed = True
        self.sealed = self._pinned()[_KEY_SEALED]
        self._next_cycle()

    def test_the_seal_names_the_cycle_that_wrote_it(self) -> None:
        self.assertEqual(self.sealed, self.generation.cycle_id)

    def test_it_survives_the_write_ending_that_cycle(self) -> None:
        # Why the scoping is load-bearing rather than belt-and-braces: the
        # key outlives the generation it was written for, so the next cycle
        # reads it whether or not anything meant it to.
        self.assertEqual(self._pinned()[_KEY_SEALED], self.sealed)

    def test_the_later_cycle_keeps_its_own_ref(self) -> None:
        deleted = self._swept()

        self.assertEqual(deleted.refs, [])
        self.assertEqual(self._resources()[_NEXT_REF], _RETAINED)

    def test_the_owner_takes_no_terminal_over_it(self) -> None:
        # And the ref held is a terminal held: an owner that left the sweep
        # over a partial register is one nothing would ever come back to.
        self._swept()

        self.assertNotEqual(
            self.github.workflow_label(self.issue), LABEL_REJECTED,
        )

    def _next_cycle(self) -> None:
        """Put the fresh attempt on the record, cancelled mid-loop.

        Stopped on a RESUMED walk, which is the one cancellation that seals
        nothing of its own -- so the count written before its first create is
        the whole of what says its register is short, and the seal the
        previous cycle left is the only thing that could contradict it.

        One consumer recorded against a count of two, and it has ended: the
        per-consumer proof passes, and whether the ref may go is entirely the
        question of whether the register is whole.
        """
        consumer = self.child.number
        self.child.closed = True
        state = self.github.read_pinned_state(self.issue)
        _late_state.write_late_generation(state, replace(
            self.generation.cancel(_CANCELLED_AT),
            cycle_id=_NEXT_CYCLE,
            phase=_late_phases.LatePhase.SPLITTING,
            resources=(),
            consumers=(),
            split_children=(),
        ).with_consumers(
            (consumer,),
        ).with_split_children((consumer,)).with_resource(LateResource(
            kind=LateResourceKind.SNAPSHOT_REF,
            target=_NEXT_REF,
            resource_state=LateResourceState.RETAINED,
        )))
        self.github.seed_state(self.issue.number, **state.data)


if __name__ == "__main__":
    unittest.main()
