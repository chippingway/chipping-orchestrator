# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late generation record answers about itself, and how it changes."""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.config import settings as config
from orchestrator.workflow.late_split.formats import InvalidLateValue
from orchestrator.workflow.late_split.models import (
    MAX_LINEAGE_DEPTH,
    LateGeneration,
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from tests.workflow.late_split import generation_test_support as _support

_BRANCH = "orchestrator/issue-1"
_OTHER_BRANCH = "orchestrator/issue-2"
_LATER_STAMP = "2026-08-21T11:00:00+00:00"

# The boundaries a split transaction owns, spelled out here rather than
# imported: what they are is the contract, and a member quietly added to
# or dropped from the runtime set has to fail this rather than follow it.
_IN_FLIGHT = (
    LatePhase.SNAPSHOTTING, LatePhase.SPLITTING, LatePhase.SUPERSEDING,
)


def _generation(**fields) -> LateGeneration:
    return LateGeneration(
        cycle_id=1, current_issue=_support.CURRENT_ISSUE, **fields,
    )


class PresenceTest(unittest.TestCase):
    """The cycle identity is what tells a late issue from a legacy one."""

    def test_default_record_is_absent(self) -> None:
        self.assertFalse(LateGeneration().is_present)

    def test_a_recorded_cycle_is_present(self) -> None:
        self.assertTrue(_generation().is_present)


class MeasurementTest(unittest.TestCase):
    """What a record answers about a measurement, or about holding none.

    The gate trips strictly past the threshold the candidate was measured
    against; a candidate the adjudication turned into children is owed no
    reading at all, and the record says so by carrying no count -- which is
    also what a tick that died between the freeze and the diff leaves.

    The boundaries that answer are spelled out here for the reason the
    in-flight set is: what they are is the contract, and a phase quietly
    joining or leaving the runtime set has to fail this rather than follow it.
    """

    def test_threshold_comparison_is_strict(self) -> None:
        threshold = _support.THRESHOLD
        cases = (
            (threshold - 1, False), (threshold, False), (threshold + 1, True),
        )
        for additions, oversized in cases:
            with self.subTest(additions=additions):
                measured = _generation(threshold=threshold, additions=additions)
                self.assertEqual(measured.is_oversized, oversized)

    def test_the_configured_ceiling_is_a_ceiling(self) -> None:
        # `MAX_ADDED_LINES` is what an operator tunes and what a generation
        # records, and a candidate landing exactly on it publishes as one
        # change: the trigger is strictly past the value, so retuning the
        # setting cannot move it by a line.
        ceiling = config.MAX_ADDED_LINES
        for additions, oversized in ((ceiling, False), (ceiling + 1, True)):
            with self.subTest(additions=additions):
                measured = _generation(threshold=ceiling, additions=additions)
                self.assertEqual(measured.is_oversized, oversized)

    def test_a_split_past_its_ref_owes_no_reading(self) -> None:
        for phase in (
            LatePhase.SPLITTING, LatePhase.SUPERSEDING, LatePhase.CLEANING_UP,
        ):
            with self.subTest(phase=phase):
                self.assertTrue(_generation(phase=phase).split_has_settled)

    def test_a_measurable_candidate_still_owes_one(self) -> None:
        # `snapshotting` cuts the ref and creates no child, and a record at
        # any boundary before it still carries the reading that sent it to the
        # adjudication -- so calling either one settled would say something
        # untrue about a generation whose count is on the comment.
        for phase in (
            None,
            LatePhase.MEASURING,
            LatePhase.HOLDING_PLAN_PR,
            LatePhase.ADJUDICATING,
            LatePhase.OWNER_CHECK,
            LatePhase.SNAPSHOTTING,
        ):
            with self.subTest(phase=phase):
                self.assertFalse(_generation(phase=phase).split_has_settled)

    def test_a_recorded_child_answers_alone(self) -> None:
        # The register is what the transaction writes down as it creates them
        # and what the retirement keeps, so it answers for a record a retry
        # left wearing the boundary it started from.
        self.assertTrue(
            _generation(
                phase=LatePhase.SNAPSHOTTING, split_children=(7,),
            ).split_has_settled,
        )

    def test_an_unmeasured_candidate_is_not_oversized(self) -> None:
        # A missing measurement is a typed failure to reconcile, never a
        # small candidate that may publish.
        for fields in (
            {"threshold": _support.THRESHOLD},
            {"additions": _support.ADDITIONS},
            {},
        ):
            with self.subTest(fields=sorted(fields)):
                self.assertFalse(_generation(**fields).is_oversized)


class LineageBoundTest(unittest.TestCase):
    """Splitting stops at the bound, and reads fail closed outside it."""

    def test_depth_below_the_bound_may_split(self) -> None:
        for depth in range(MAX_LINEAGE_DEPTH):
            with self.subTest(depth=depth):
                self.assertTrue(_generation(lineage_depth=depth).may_split)

    def test_the_bound_and_beyond_may_not_split(self) -> None:
        # A hand-edited pinned comment is the reason the high case exists:
        # refusing is what the cap is for, and an absurd depth is not proof
        # that a fourth generation is safe. Neither is an unknown one -- a
        # lineage that cannot say how deep it is cannot show it has room, and
        # reading that as the root's 0 is exactly how a damaged field would
        # buy a generation past the bound.
        for depth in (MAX_LINEAGE_DEPTH, MAX_LINEAGE_DEPTH + 6, -1, None, 2.5):
            with self.subTest(depth=depth):
                self.assertFalse(_generation(lineage_depth=depth).may_split)


class ResourceLedgerTest(unittest.TestCase):
    """The ledger records one entry per resource, however often it is written."""

    def test_repeating_a_resource_updates_its_entry(self) -> None:
        pending = LateResource(
            kind=LateResourceKind.SNAPSHOT_REF, target=_support.SNAPSHOT_REF,
        )
        reconciled = LateResource(
            kind=LateResourceKind.SNAPSHOT_REF,
            target=_support.SNAPSHOT_REF,
            resource_state=LateResourceState.RECONCILED,
        )
        recorded = _generation().with_resource(pending).with_resource(reconciled)
        self.assertEqual(recorded.resources, (reconciled,))

    def test_a_different_target_is_its_own_entry(self) -> None:
        first = LateResource(
            kind=LateResourceKind.BRANCH, target=_BRANCH,
        )
        second = LateResource(
            kind=LateResourceKind.BRANCH, target=_OTHER_BRANCH,
        )
        recorded = _generation().with_resource(first).with_resource(second)
        self.assertEqual(recorded.resources, (first, second))

    def test_only_an_issue_number_is_a_consumer(self) -> None:
        # The ledger decides whether a snapshot may be reclaimed, so a value
        # nobody can ask GitHub about may not be converted into one.
        for damaged in (True, 2.5, "7", 0, -3):
            with self.subTest(damaged=damaged), self.assertRaises(InvalidLateValue):
                _generation().with_consumers((damaged,))

    def test_consumers_are_deduplicated_and_ordered(self) -> None:
        # The reclamation sweep walks this ledger, so a child recorded twice
        # would be asked about twice.
        recorded = _generation().with_consumers((7, 3)).with_consumers((3, 5))
        self.assertEqual(recorded.consumers, (3, 5, 7))


class OpaqueLedgerTest(unittest.TestCase):
    """An obligation this binary cannot type is one nothing may read past."""

    def test_a_typed_record_owes_nothing_opaque(self) -> None:
        self.assertFalse(_generation().has_opaque_ledger)

    def test_either_ledger_makes_the_record_opaque(self) -> None:
        for held in ("opaque_resources", "opaque_consumers"):
            with self.subTest(ledger=held):
                self.assertTrue(
                    _generation(**{held: "[1]"}).has_opaque_ledger,
                )


class BoundaryTest(unittest.TestCase):
    """How a record's boundary moves, and the two rules that stop it wrongly.

    A boundary moves forwards freely and never backwards out of a split, and
    a cancellation keeps the one it interrupted. Both exist for the same
    window: a child is created before the write that records it, so a loop
    that died between the two leaves an empty ledger and a real issue on
    GitHub, and the phase is the whole account of what happened. Every retry
    ABOVE the transaction names a boundary of its own -- the plan-PR hold on
    every tick, a spawn, the owner read each completion claims -- and any of
    them landing on that record would erase it.
    """

    def test_a_transaction_boundary_is_never_rewound(self) -> None:
        earlier = (
            LatePhase.MEASURING,
            LatePhase.HOLDING_PLAN_PR,
            LatePhase.ADJUDICATING,
            LatePhase.OWNER_CHECK,
        )
        for standing in _IN_FLIGHT:
            for phase in earlier:
                with self.subTest(standing=standing, phase=phase):
                    kept = _generation(phase=standing).at_phase(phase)

                    self.assertEqual(kept.phase, standing)

    def test_every_other_move_is_taken(self) -> None:
        # Forwards out of a transaction, and anywhere at all from a boundary
        # no transaction owns -- which is every ordinary tick.
        moves = (
            (LatePhase.SPLITTING, LatePhase.SUPERSEDING),
            (LatePhase.SUPERSEDING, LatePhase.CLEANING_UP),
            (LatePhase.SPLITTING, LatePhase.CANCELLING),
            (LatePhase.ADJUDICATING, LatePhase.OWNER_CHECK),
            (None, LatePhase.MEASURING),
        )
        for standing, phase in moves:
            with self.subTest(standing=standing, phase=phase):
                moved = _generation(phase=standing).at_phase(phase)

                self.assertEqual(moved.phase, phase)

    def test_a_second_cancel_keeps_the_first_stamp(self) -> None:
        cancelled = _generation().cancel(_support.CANCELLED_AT)
        again = cancelled.cancel(_LATER_STAMP)
        self.assertTrue(again.cancelled)
        self.assertEqual(again.cancelled_at, cancelled.cancelled_at)

    def test_it_keeps_the_boundary_it_interrupted(self) -> None:
        # `phase` is about to name the cancellation itself, and the boundary
        # it replaces is what says whether the consumer ledger accounts for
        # every child cut from this generation's snapshot.
        splitting = _generation(phase=LatePhase.SPLITTING)

        cancelled = splitting.cancel(_support.CANCELLED_AT)

        self.assertEqual(cancelled.cancelled_phase, LatePhase.SPLITTING)

    def test_a_re_mark_never_moves_that_boundary(self) -> None:
        # A record already carrying the mark is one a later observation is
        # repeating, and by then `phase` names the cancellation -- which
        # proves nothing about the loop and must not replace what does.
        cancelled = _generation(phase=LatePhase.CLEANING_UP).cancel(
            _support.CANCELLED_AT,
        )

        again = replace(cancelled, phase=LatePhase.CANCELLING).cancel(
            _LATER_STAMP,
        )

        self.assertEqual(again.cancelled_phase, LatePhase.CLEANING_UP)


if __name__ == "__main__":
    unittest.main()
