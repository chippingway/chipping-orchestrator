# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a snapshot owner a human closed still owes, and who comes back for it.

An issue closed on `decomposing` or `umbrella` is outside every other pass, so
the cleanup sweep is the only thing that ever asks about its ledger again. The
real handler is driven in every case, because half of what is under test is
what the pass does NOT do: it never activates a child and never spawns. The
one label it does write is the `rejected` a fully settled cycle earns, which
is the ending rather than a route -- what that ending consists of is pinned in
`test_late_cancellation.py` beside the owner that decides it.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.late_split import restart as _restart, state as _late_state
from orchestrator.workflow.late_split.models import (
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    GENERATION_NUMBER,
    late_generation,
)

_WARNING = "WARNING"

_OPAQUE_RESOURCES = '[{"kind": "unknown-to-this-binary"}]'

_OPAQUE_CONSUMERS = '["?"]'

_DELETED = _snapshot_refs.SnapshotOutcome.DELETED

_ABSENT = _snapshot_refs.SnapshotOutcome.ABSENT

# The generation the consumer minted when it split in turn, and the child it
# is still holding that snapshot for.
_NESTED_REF = "refs/orchestrator/late-split/issue-411/cycle-3/gen-2"

_GRANDCHILD_NUMBER = 4111

_ANCESTRY_REF = "late_ancestry_snapshot_ref"

# The one ref every case here is about, as the remote records being asked
# for it.
_TAKEN = (_support.SNAPSHOT_REF,)


def _closed(
    owed: LateResourceState,
    snapshot: LateResourceState,
    *,
    child_label: str = _support.LABEL_DONE,
    child_closed: bool = True,
    phase: LatePhase = LatePhase.CLEANING_UP,
):
    """A closed snapshot owner, and the consumer disposition under test."""
    return _support.split_umbrella(
        owed,
        snapshot=snapshot,
        child_label=child_label,
        owner=OwnerSeed(
            label=_support.DECOMPOSING,
            closed=True,
            child_closed=child_closed,
            phase=phase,
        ),
    )


def _seed_nested_generation(seeded) -> None:
    """Give the consumer a split of its own, still holding its own ref."""
    child = seeded.github.get_issue(_support.CHILD_NUMBER)
    child_state = seeded.github.read_pinned_state(child)
    _late_state.write_late_generation(child_state, late_generation(
        threshold=None,
        additions=None,
        resources=(),
        current_issue=_support.CHILD_NUMBER,
        generation=GENERATION_NUMBER + 1,
    ).with_consumers((_GRANDCHILD_NUMBER,)).with_resource(LateResource(
        kind=LateResourceKind.SNAPSHOT_REF,
        target=_NESTED_REF,
        resource_state=LateResourceState.RETAINED,
    )))
    seeded.github.seed_state(_support.CHILD_NUMBER, **child_state.data)


class ClosedOwnerSweepTest(_PatchedWorkflowMixin, unittest.TestCase):
    """The ledger is settled; nothing else about the issue is touched."""

    def test_it_reclaims_what_a_closed_owner_left(self) -> None:
        # Both halves in one pass, and nothing beyond the ledger: the close
        # is a human decision, so the only label written is the terminal that
        # says the cycle ended, nothing is posted anywhere, and the consumer
        # is read to prove the ref may go and touched in no other way.
        seeded = _closed(
            LateResourceState.PENDING, LateResourceState.RETAINED,
        )
        github = seeded.github

        deleted = seeded.swept(self, _DELETED)

        self.assertEqual(tuple(deleted.refs), _TAKEN)
        self.assertEqual(deleted.shas, [CANDIDATE_SHA])
        self.assertEqual(github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH])
        self.assertEqual(
            _support.resource_states(github),
            {
                _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
                _support.SNAPSHOT_REF: _support.STATE_RECONCILED,
            },
        )
        self.assertEqual(
            github.label_history, [(_support.PARENT_NUMBER, _support.LABEL_REJECTED)],
        )
        self.assertEqual(github.posted_comments, [])

    def test_a_close_is_read_anew_every_pass(self) -> None:
        # The label a running child wears is not terminal, so a manual close
        # is the whole answer -- and it is not latched. The same ledger with
        # the same consumer reopened keeps the ref, because what decides is
        # the reading taken on the visit that would delete it.
        for child_closed, asked in ((True, [_support.SNAPSHOT_REF]), (False, [])):
            with self.subTest(child_closed=child_closed):
                seeded = _closed(
                    LateResourceState.RECONCILED,
                    LateResourceState.RETAINED,
                    child_label=_support.LABEL_IN_REVIEW,
                    child_closed=child_closed,
                )

                deleted = seeded.swept(self, _DELETED)

                self.assertEqual(deleted.refs, asked)

    def test_a_nested_child_that_published_counts(self) -> None:
        # The consumer split again and is still holding a snapshot of its own
        # for a grandchild nothing here can see. It reached `done` only by
        # publishing, which is what proves its whole subtree is past needing
        # the ANCESTOR ref -- so this owner reclaims its own and leaves the
        # nested ledger exactly where it found it.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )
        _seed_nested_generation(seeded)

        deleted = seeded.swept(self, _DELETED)

        self.assertEqual(tuple(deleted.refs), _TAKEN)
        self.assertEqual(
            {
                entry["target"]: entry["state"]
                for entry in
                seeded.github.pinned_data(_support.CHILD_NUMBER)["late_resources"]
            },
            {_NESTED_REF: _support.STATE_RETAINED},
        )

    def test_an_unreadable_consumer_owes_the_ref(self) -> None:
        # Fail per consumer, not per pass: the ref stays because nothing
        # proved the consumer done, while the branch -- which owes no consumer
        # anything -- is reclaimed on this very visit.
        seeded = _closed(
            LateResourceState.PENDING, LateResourceState.RETAINED,
        )
        seeded.github.get_issue = MagicMock(side_effect=RuntimeError("boom"))

        with self.assertLogs(_support.WORKFLOW_LOG, level="ERROR"):
            deleted = seeded.swept(self, _DELETED)

        self.assertEqual(deleted.refs, [])
        self.assertEqual(
            _support.resource_states(seeded.github),
            {
                _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
                _support.SNAPSHOT_REF: _support.STATE_RETAINED,
            },
        )

    def test_a_reclaimed_ref_tells_nobody(self) -> None:
        # A cancelled cycle owes its children nothing, the receipt a live
        # split leaves included: they are issues a human's close stranded
        # rather than work this orchestrator is still driving. Nothing about
        # the ref goes unsaid -- the transport drops this host's mirror before
        # it touches the remote, so a child reopened afterwards is stopped and
        # told by its own guard, off the pointer this pass leaves standing.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )

        deleted = seeded.swept(self, _DELETED)

        self.assertEqual(tuple(deleted.refs), _TAKEN)
        self.assertEqual(seeded.github.posted_comments, [])
        self.assertEqual(
            seeded.github.pinned_data(_support.CHILD_NUMBER)[_ANCESTRY_REF],
            _support.SNAPSHOT_REF,
        )

    def test_a_refused_delete_is_asked_again(self) -> None:
        # A permission or ruleset problem an operator has to see: the entry
        # reads `failed`, the typed failure reaches the sinks, and the next
        # sweep retries the same ref rather than writing it off.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            seeded.swept(self, _snapshot_refs.SnapshotOutcome.REFUSED)

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_FAILED,
        )
        reported = [
            event for event in seeded.github.recorded_events
            if event.get("failure") == "snapshot_delete_failed"
        ]
        self.assertEqual(len(reported), 1)
        # Read off the issue rather than named by the caller, so a record says
        # where the reclamation happened -- here the state this owner was
        # closed on, not the umbrella terminal the other entry runs from.
        self.assertEqual(reported[0]["stage"], "decomposing")

        retried = seeded.swept(self, _DELETED)

        self.assertEqual(tuple(retried.refs), _TAKEN)
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )


    def test_a_standing_refusal_records_once(self) -> None:
        # The retry is every visit; the record of it is not. The decision is
        # already durable on the entry, so the retry does not put
        # `reclaiming` back over the `failed` it left -- which is what would
        # otherwise alternate the recorded state and report a transition on
        # every other visit that nothing actually transitioned.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )
        refused = _snapshot_refs.SnapshotOutcome.REFUSED

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            seeded.swept(self, refused)
            written = seeded.github.write_state_calls
            asked = seeded.swept(self, refused)
            seeded.swept(self, refused)

        self.assertEqual(tuple(asked.refs), _TAKEN)
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_FAILED,
        )
        self.assertEqual(seeded.github.write_state_calls, written)
        self.assertEqual(
            len([
                event for event in seeded.github.recorded_events
                if event.get("event") == _support.EVENT_LATE_CLEANUP
            ]),
            1,
        )


class WholeLedgerTest(_PatchedWorkflowMixin, unittest.TestCase):
    """Whether the ledger names every child cut from the ref, before who ended.

    The sweep is the only thing that ever looks at a closed owner again, so
    both answers are final. An empty list read as a gap left a ref nothing
    would ever reclaim; a list read as complete while the split was still
    filling it would take one out from under a child nobody had recorded yet.
    The record's own phase is what tells the two apart.
    """

    def test_a_ref_nothing_was_cut_from_is_reclaimed(self) -> None:
        seeded = self._orphan(LatePhase.SNAPSHOTTING)

        deleted = self._swept(seeded)

        self.assertEqual(tuple(deleted.refs), _TAKEN)
        self.assertEqual(self._ref_state(seeded.github), _support.STATE_RECONCILED)

    def test_it_settles_the_owner_for_good(self) -> None:
        # What being stuck cost: the sweep came back on every cadence with a
        # ref it would never take. Once the entry reconciles the owner leaves
        # the sweep on the terminal, and a pass driven at it anyway asks the
        # remote nothing, writes nothing, and does not re-apply the label --
        # and nobody was told, because there is nobody.
        seeded = self._orphan(LatePhase.SNAPSHOTTING)
        self._swept(seeded)
        settled = seeded.github.write_state_calls

        again = self._swept(seeded)

        self.assertEqual(again.refs, [])
        self.assertEqual(seeded.github.write_state_calls, settled)
        self.assertEqual(seeded.github.posted_comments, [])
        self.assertEqual(
            seeded.github.label_history, [(_support.PARENT_NUMBER, _support.LABEL_REJECTED)],
        )

    def test_a_ledger_the_split_may_lead_is_kept(self) -> None:
        # The window with NOTHING recorded, which is the one the ledger
        # cannot speak to at all: `splitting` goes down before the first
        # create, so a loop that died between creating its first child and
        # recording it leaves an empty list beside a real issue on GitHub.
        #
        # The phase says so on a record this binary wrote, which is why the
        # owner-check claim may not write over it. On one an EARLIER binary
        # left, the claim already did -- and what upgrades it is the count the
        # transaction put down in that same write, which nothing moved.
        upgraded = {_support.EXPECTED_CHILDREN: 2}
        for phase, evidence in (
            (LatePhase.SPLITTING, {}), (LatePhase.OWNER_CHECK, upgraded),
        ):
            with self.subTest(phase=phase):
                seeded = self._orphan(phase)
                seeded.github.seed_state(
                    _support.PARENT_NUMBER,
                    **{
                        **seeded.github.pinned_data(_support.PARENT_NUMBER),
                        **evidence,
                    },
                )
                _support.seed_unrecorded_child(seeded.github)

                deleted = self._swept(seeded)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(
                    self._ref_state(seeded.github), _support.STATE_RETAINED,
                )
                self.assertEqual(seeded.github.label_history, [])
                self.assertFalse(
                    seeded.github.get_issue(_support.UNRECORDED_CHILD).closed,
                )

    def test_a_part_written_ledger_is_kept(self) -> None:
        # The same window with the list NOT empty, which is the shape that
        # looks provable and is not: the split recorded its first child, died
        # before recording its second, and the owner and the first child have
        # both closed since. Every consumer the ledger names has ended, so a
        # proof walking that list alone would take the ref -- out from under a
        # child it never read, never told, and could still be resumed.
        #
        # `owner_check` is the same window wearing an earlier phase. The next
        # tick came back through the post-agent owner read, which writes that
        # phase OVER the `splitting` it interrupted, and the close that landed
        # during it kept exactly what the read had left. Only the record can
        # say the loop was in flight, so only the record is believed.
        for phase in (LatePhase.SPLITTING, LatePhase.OWNER_CHECK):
            with self.subTest(phase=phase):
                seeded = _closed(
                    LateResourceState.RECONCILED,
                    LateResourceState.RETAINED,
                    phase=phase,
                )
                _support.seed_unrecorded_child(seeded.github)

                deleted = self._swept(seeded)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(
                    self._ref_state(seeded.github), _support.STATE_RETAINED,
                )
                self.assertEqual(seeded.github.posted_comments, [])
                self.assertFalse(
                    seeded.github.get_issue(_support.UNRECORDED_CHILD).closed,
                )

    def _orphan(self, phase: LatePhase):
        """A closed owner holding a ref, with no child recorded or made."""
        return _support.split_umbrella(
            LateResourceState.RECONCILED,
            snapshot=LateResourceState.RETAINED,
            owner=OwnerSeed(
                label=_support.DECOMPOSING, closed=True, child=False, phase=phase,
            ),
        )

    def _swept(self, seeded) -> RecordedDelete:
        """One sweep, with the remote taking whatever it is asked for."""
        return seeded.swept(self)

    def _ref_state(self, github) -> str:
        """What the owner's ledger now says about the one ref it held."""
        return _support.resource_states(github)[_support.SNAPSHOT_REF]


class FinishedLoopTest(_PatchedWorkflowMixin, unittest.TestCase):
    """More than one boundary is two answers, and the record tells them apart.

    `splitting` goes down before the first create AND again beside every child
    recorded, the last one included -- so a crash between that final write and
    the announcement leaves a COMPLETE ledger wearing a mid-loop boundary. A
    transaction retried after a park is the same question one step earlier: it
    rewrites `snapshotting` over whatever boundary it had reached, so a
    finished split comes back wearing the one it started from.

    Reading either phase alone retains the ref for good and holds the terminal
    with it, because nothing revisits a cancelled owner to move it on. What
    separates them is the count the transaction put down ahead of its first
    create, against the register it appends to as each child is recorded, and
    it is asked of every boundary rather than of one.
    """

    def test_a_complete_ledger_is_whole_at_either(self) -> None:
        # `snapshotting` is the retry window: the split finished, the tick
        # died before the announcement, the next one re-entered and re-proved
        # the ref it already had -- and a close landed there.
        for phase in (LatePhase.SPLITTING, LatePhase.SNAPSHOTTING):
            with self.subTest(phase=phase):
                seeded = self._finished_loop(phase)

                deleted = seeded.swept(self)

                self.assertEqual(self._reclaimed(deleted), _TAKEN)
                self.assertEqual(
                    tuple(seeded.github.label_history),
                    ((_support.PARENT_NUMBER, _support.LABEL_REJECTED),),
                )

    def test_a_short_register_keeps_the_ref(self) -> None:
        # The same retry window with one child of two recorded, which is the
        # shape the count exists to catch: a real issue exists that the
        # consumer ledger cannot speak for, so the ref stays and the terminal
        # is held with it.
        seeded = self._finished_loop(LatePhase.SNAPSHOTTING, expected=2)

        deleted = seeded.swept(self)

        self.assertEqual(self._reclaimed(deleted), ())
        self.assertEqual(tuple(seeded.github.label_history), ())

    def _reclaimed(self, deleted) -> tuple:
        """Which refs the remote was actually asked to drop."""
        return tuple(deleted.refs)

    def _finished_loop(self, phase: LatePhase, expected: int = 1):
        """A closed owner whose one child is created, recorded, and ended."""
        seeded = _closed(
            LateResourceState.RECONCILED,
            LateResourceState.RETAINED,
            phase=phase,
        )
        seeded.github.seed_state(
            _support.PARENT_NUMBER,
            **{
                **seeded.github.pinned_data(_support.PARENT_NUMBER),
                _support.EXPECTED_CHILDREN: expected,
            },
        )
        return seeded


class UntouchedConsumerTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A cancelled cycle reclaims its ref and reaches no child doing it.

    The receipt a reclamation leaves is what a live split owes the children it
    is still responsible for, and a cycle a close ended is responsible for
    none of them: they are real issues carrying real slices of somebody's
    work, and what happens to them next is a human's decision. So the entry
    reconciles on the delete alone, and nothing about a consumer -- its state,
    its label, its thread -- is written by this pass. The umbrella's own
    terminal is where the receipt still applies (`test_late_release.py`).
    """

    def test_it_reconciles_on_the_delete_alone(self) -> None:
        # The consumer is still READ -- proving every one of them ended is
        # what lets the ref go at all -- and that reading is the whole of
        # what it costs the child.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )

        deleted = self._sweep(seeded)

        self.assertEqual(tuple(deleted.refs), _TAKEN)
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertEqual(seeded.github.posted_comments, [])

    def test_a_child_of_any_label_is_left_alone(self) -> None:
        # The two pre-PR states a human can close an issue on are swept by
        # nothing, so a consumer left on one never becomes terminal. It is
        # still ended -- so the ref goes -- and it is still untouched, on
        # every label a stranded child can be wearing.
        for child_label in (_support.LABEL_READY, _support.LABEL_BLOCKED, _support.LABEL_IN_REVIEW):
            with self.subTest(child_label=child_label):
                seeded = _closed(
                    LateResourceState.RECONCILED,
                    LateResourceState.RETAINED,
                    child_label=child_label,
                )

                recorded = dict(seeded.github.pinned_data(_support.CHILD_NUMBER))

                deleted = self._sweep(seeded)

                self.assertEqual(tuple(deleted.refs), _TAKEN)
                self.assertEqual(seeded.github.posted_comments, [])
                self.assertEqual(
                    seeded.github.pinned_data(_support.CHILD_NUMBER), recorded,
                )

    def test_an_unreadable_child_still_holds_the_ref(self) -> None:
        # Nothing about the receipt changes what a consumer has to PROVE: one
        # this pass could not read is one it cannot show has ended, so the ref
        # stays and no delete is spent.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RETAINED,
        )
        seeded.github.get_issue = MagicMock(side_effect=RuntimeError("boom"))

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            deleted = self._sweep(seeded)

        self.assertEqual(deleted.refs, [])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RETAINED,
        )

    def test_an_ordered_ref_already_gone_finishes(self) -> None:
        # The crash between the push that took the ref and the write that
        # would have recorded it. The decision stands on the record, the ref
        # is gone, and finishing it costs one read and no consumer at all.
        seeded = _closed(
            LateResourceState.RECONCILED, LateResourceState.RECLAIMING,
        )

        self._sweep(seeded, _ABSENT)

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertEqual(seeded.github.posted_comments, [])

    def _sweep(self, seeded, outcome=_DELETED) -> RecordedDelete:
        """Sweep this owner, with the read-only ask agreeing with `outcome`."""
        return seeded.swept(self, outcome, presence=outcome)


class SpentLedgerTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A sweep costs what is left to settle, and nothing when that is none.

    The pass runs on every closed owner on the two cleanup labels, for as long
    as they carry one, so what it spends on an owner with nothing left to do
    is what decides whether the sweep is affordable at all.
    """

    def test_a_settled_ledger_costs_one_ending_only(self) -> None:
        # An owner whose every reclaimable obligation is already reconciled
        # owes the pass only the ending: the cancellation mark, the child
        # receipts it says nothing further is owed on, and the terminal that
        # takes the issue out of the sweep. No consumer is read to establish
        # any of it, and a second pass writes nothing at all.
        seeded = _support.split_umbrella(
            LateResourceState.RECONCILED,
            owner=OwnerSeed(label=_support.DECOMPOSING, closed=True),
        )

        self._asks_nothing(seeded)
        written = seeded.github.write_state_calls

        self.assertEqual(
            _support.resource_states(seeded.github, _support.CHILD_KIND),
            {str(_support.CHILD_NUMBER): _support.STATE_RECONCILED},
        )
        # And what that discharge is FOR: `rejected` authorizes a restart,
        # which projects a fresh cycle only over a ledger with nothing
        # unreconciled on it -- so a receipt left `pending` would retire an
        # owner whose restart then refuses for good.
        self.assertTrue(_restart.obligations_settled(
            _late_state.read_late_generation(
                seeded.github.read_pinned_state(seeded.parent),
            ),
        ))
        self.assertEqual(
            seeded.github.label_history, [(_support.PARENT_NUMBER, _support.LABEL_REJECTED)],
        )

        self._asks_nothing(seeded)

        self.assertEqual(seeded.github.write_state_calls, written)

    def test_an_opaque_ledger_stops_the_pass(self) -> None:
        # An entry this binary cannot type is an obligation too, so nothing on
        # the ledger may be reclaimed around it -- which makes every reading
        # this pass could take one it may not act on.
        seeded = _closed(
            LateResourceState.PENDING, LateResourceState.RETAINED,
        )
        github = seeded.github
        github.seed_state(
            _support.PARENT_NUMBER,
            **{
                **github.pinned_data(_support.PARENT_NUMBER),
                "late_resources": _OPAQUE_RESOURCES,
            },
        )
        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            self._asks_nothing(seeded)

        self.assertEqual(github.deleted_remote_branches, [])

    def test_an_opaque_consumer_list_frees_the_branch(self) -> None:
        # The two ledgers stop different things, and a sweep that folded them
        # together would stop coming back for a branch because somebody
        # hand-edited a list of issue numbers.
        seeded = _closed(
            LateResourceState.PENDING, LateResourceState.RETAINED,
        )
        github = seeded.github
        github.seed_state(
            _support.PARENT_NUMBER,
            **{
                **github.pinned_data(_support.PARENT_NUMBER),
                "late_consumers": _OPAQUE_CONSUMERS,
            },
        )

        deleted = seeded.swept(self)

        self.assertEqual(
            github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertEqual(deleted.refs, [])
        self.assertEqual(
            _support.resource_states(github),
            {
                _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
                _support.SNAPSHOT_REF: _support.STATE_RETAINED,
            },
        )

    def _asks_nothing(self, seeded) -> None:
        """Sweep an owner that must cost neither a read nor a delete."""
        seeded.github.get_issue = MagicMock(side_effect=AssertionError)

        deleted = seeded.swept(self, _DELETED)

        self.assertEqual(deleted.refs, [])


if __name__ == "__main__":
    unittest.main()
