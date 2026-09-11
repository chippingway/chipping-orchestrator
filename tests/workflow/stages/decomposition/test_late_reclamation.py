# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the snapshot a split preserved may finally be deleted.

The rule is the ref's own: every recorded direct consumer terminal, and the
umbrella's all-children-resolved branch is both the first moment that becomes
true for the children a split created and the last that could act on it.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.models import (
    LatePhase,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_cleanup as _late_cleanup,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import RecordedDelete

_OPAQUE_CONSUMERS = '["?"]'

# The stage key the split transaction writes before its first create,
# spelled here rather than imported: what it is called is the contract a
# record already in flight was written under.
_EXPECTED_CHILDREN = "expected_children_count"

# What one obligation an older or newer binary recorded looks like: a kind
# this one cannot type, preserved verbatim rather than reduced to what it
# understood.
_UNTYPED_KIND = "unknown-to-this-binary"

_STATE_CLOSED = "closed"

_KIND_SNAPSHOT = "snapshot_ref"

# Three refs that are in the namespace, are shaped exactly like this one's, and
# belong to somebody else: another issue's, another cycle of this issue's, and
# another generation of this cycle's. Every one of them names the same commit,
# because a lineage is cut from one candidate.
_FOREIGN_REFS = (
    "refs/orchestrator/late-split/issue-99/cycle-3/gen-1",
    "refs/orchestrator/late-split/issue-41/cycle-4/gen-1",
    "refs/orchestrator/late-split/issue-41/cycle-3/gen-2",
)


class _RealShapedChild:
    """A closed consumer in the shape GitHub actually hands one back.

    A PyGithub issue carries `state` and nothing called `closed`, so the
    double's flag is the one spelling the reclamation never sees in
    production.
    """

    def __init__(self, number: int) -> None:
        self.number = number
        self.state = _STATE_CLOSED


# What the rule reads beside the record: a pinned comment carrying no
# evidence that a split transaction ever started, which is every case here
# but the upgrade one.
_UNSTARTED = PinnedState(state_data={})


class UmbrellaReclamationTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A retained ref is deleted at the terminal, or holds it open."""

    def test_it_deletes_a_ref_its_consumers_left(self) -> None:
        seeded = _retaining()

        deleted = self._walk_with(
            seeded, _snapshot_refs.SnapshotOutcome.DELETED,
        )

        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(deleted.shas, [_support.CANDIDATE_SHA])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertTrue(seeded.parent.closed)

    def test_a_repointed_ref_is_not_reclaimed(self) -> None:
        # Named against the commit the split preserved, so a ref somebody
        # re-pointed is refused rather than deleted -- and the refusal holds
        # the terminal open, because that is a human's to settle.
        seeded = _retaining()

        with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING"):
            self._walk_with(seeded, _snapshot_refs.SnapshotOutcome.MISMATCH)

        self.assertEqual(_support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_FAILED)
        self.assertFalse(seeded.parent.closed)

    def test_an_absent_ref_is_already_reclaimed(self) -> None:
        # The crash between the push that deleted a ref and the write that
        # would have recorded it: absent is success, so the retry settles.
        seeded = _retaining()

        self._walk_with(
            seeded,
            _snapshot_refs.SnapshotOutcome.ABSENT,
            presence=_snapshot_refs.SnapshotOutcome.ABSENT,
        )

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertTrue(seeded.parent.closed)

    def test_a_refused_delete_holds_the_terminal(self) -> None:
        # A permission or ruleset problem an operator has to see.
        seeded = _retaining()

        with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING"):
            self._walk_with(seeded, _snapshot_refs.SnapshotOutcome.REFUSED)

        self.assertEqual(_support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_FAILED)
        self.assertFalse(seeded.parent.closed)

    def test_a_consumer_nobody_recorded_holds_it_open(self) -> None:
        # Fail-closed twice over: a consumer the scan cannot speak for may
        # still be cutting from the ref, so the ref stays -- and a ref that
        # stays holds the terminal, because an umbrella closed over one is an
        # object on the remote nothing would ever come back for.
        seeded = _retaining()
        seeded.github.seed_state(
            _support.PARENT_NUMBER,
            **{
                **seeded.github.pinned_data(_support.PARENT_NUMBER),
                "late_consumers": [_support.CHILD_NUMBER, _support.CHILD_NUMBER + 5],
            },
        )

        with self.assertLogs(_support.WORKFLOW_LOG, level="INFO"):
            deleted = self._walk_with(
                seeded, _snapshot_refs.SnapshotOutcome.DELETED,
            )

        self.assertEqual(deleted.refs, [])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RETAINED,
        )
        self.assertFalse(seeded.parent.closed)

    def test_a_death_post_delete_reconciles(self) -> None:
        # The delete landed and the write that recorded it did not. The
        # decision was recorded BEFORE the delete, so the retry acts on that
        # rather than re-proving a consumer set a human may have changed --
        # and absent is success, so it settles the same entry in one request.
        seeded = _retaining()
        died = RecordedDelete(
            _snapshot_refs.SnapshotOutcome.DELETED,
            raising=KeyboardInterrupt("died"),
        )
        with self.assertRaises(KeyboardInterrupt), died.answering():
            _support.walk_owner(self, seeded)
        self.assertEqual(died.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECLAIMING,
        )
        self.assertFalse(seeded.parent.closed)
        # A human reopening the consumer in that window cannot re-block a
        # reclamation the record already says was ordered.
        seeded.github.get_issue(_support.CHILD_NUMBER).closed = False

        self._walk_with(
            seeded,
            _snapshot_refs.SnapshotOutcome.ABSENT,
            presence=_snapshot_refs.SnapshotOutcome.ABSENT,
        )

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertTrue(seeded.parent.closed)

    def _walk_with(self, seeded, outcome, **answers) -> RecordedDelete:
        """Run the umbrella tick with the remote answering `outcome`."""
        deleted = RecordedDelete(outcome, **answers)
        with deleted.answering():
            _support.walk_owner(self, seeded)
        return deleted


class UnprovableObligationTest(_PatchedWorkflowMixin, unittest.TestCase):
    """Nothing unreadable closes an umbrella, and nothing foreign is deleted.

    Two halves of the same discipline: an obligation this binary cannot read
    holds the terminal open, and a target it cannot prove is this issue's own
    is refused before the remote is touched -- which then holds the terminal
    open too, because a refusal is still an obligation.
    """

    def test_an_opaque_ledger_holds_the_terminal(self) -> None:
        # The entries it could not type are still obligations, and the typed
        # ones beside them are not the whole of what is owed -- so closing on
        # the strength of that projection is the reading the verbatim copy
        # exists to prevent.
        seeded = _support.split_umbrella(LateResourceState.RECONCILED)
        self._seed_resources(seeded.github, [{"kind": _UNTYPED_KIND}])

        _support.walk_owner(self, seeded)

        self.assertFalse(seeded.parent.closed)
        self.assertEqual(seeded.github.deleted_remote_branches, [])

    def test_an_opaque_consumer_list_frees_the_branch(self) -> None:
        # The two ledgers are preserved and written apart, and they stop
        # different things. A consumer list nobody can read is what a
        # snapshot's proof would be taken from -- so the ref stays -- but the
        # branch owes no consumer anything, and freezing it too would leave a
        # superseded branch on the remote for as long as the hand edit stood.
        seeded = _retaining()
        self._seed_resources(seeded.github, consumers=_OPAQUE_CONSUMERS)

        deleted = RecordedDelete(_snapshot_refs.SnapshotOutcome.DELETED)
        with self.assertLogs(_support.WORKFLOW_LOG, level="INFO"), deleted.answering():
            _support.walk_owner(self, seeded)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertEqual(deleted.refs, [])
        self.assertFalse(seeded.parent.closed)

    def test_a_foreign_identity_is_never_deleted(self) -> None:
        # The transport proves the namespace and the commit, and neither is
        # identity: every generation in a lineage was cut from one candidate
        # and names the same SHA, so a hand-edited entry pointing at a
        # sibling's ref would pass both tests and destroy the only copy of
        # exactly what that sibling was told to reuse.
        for foreign in _FOREIGN_REFS:
            with self.subTest(ref=foreign):
                seeded = _retaining()
                github = seeded.github
                self._seed_resources(github, [{
                    "kind": _KIND_SNAPSHOT,
                    "target": foreign,
                    "state": _support.STATE_RETAINED,
                }])
                deleted = RecordedDelete(
                    _snapshot_refs.SnapshotOutcome.DELETED,
                )

                held = deleted.answering()
                with self.assertLogs(_support.WORKFLOW_LOG, level="ERROR"), held:
                    _support.walk_owner(self, seeded)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(_support.resource_states(github)[foreign], _support.STATE_FAILED)
                self.assertFalse(seeded.parent.closed)

    def test_a_damaged_identity_holds_the_terminal(self) -> None:
        # A record whose cycle identity cannot be read still writes what it
        # owes; there is just nothing to correlate a reclamation to and no
        # issue number to prove a branch belongs to this generation.
        seeded = _support.split_umbrella(LateResourceState.PENDING)
        self._seed_resources(seeded.github, damaged=True)

        with self.assertLogs(_support.WORKFLOW_LOG, level="ERROR"):
            _support.walk_owner(self, seeded)

        self.assertFalse(seeded.parent.closed)
        self.assertEqual(seeded.github.deleted_remote_branches, [])

    def test_a_damaged_identity_owing_nothing_closes(self) -> None:
        # Every umbrella the initial decomposer made carries no ledger at all,
        # and answers without a write.
        seeded = _support.split_umbrella(LateResourceState.PENDING)
        self._seed_resources(seeded.github, damaged=True, resources=None)

        _support.walk_owner(self, seeded)

        self.assertTrue(seeded.parent.closed)

    def _seed_resources(
        self, github, resources=(), *, damaged: bool = False, consumers=None,
    ) -> None:
        """Re-seed the parent's ledgers, optionally without a readable identity."""
        pinned = dict(github.pinned_data(_support.PARENT_NUMBER))
        if consumers is not None:
            pinned["late_consumers"] = consumers
        if resources is None:
            pinned.pop("late_resources", None)
        elif resources:
            pinned["late_resources"] = resources
        if damaged:
            pinned.pop("late_cycle_id", None)
        github.seed_state(_support.PARENT_NUMBER, **pinned)


class TerminalConsumerTest(unittest.TestCase):
    """Which readings prove a consumer will never cut from the ref again.

    Asked of the rule directly, because the umbrella's own terminal is only
    ever reached with every child `done`: the other two are what a consumer
    that ended WITHOUT publishing looks like, and the reclamation has to count
    them or a snapshot outlives every lineage one appears in.
    """

    def test_every_way_a_consumer_can_end_counts(self) -> None:
        # All three end the consumer by CLOSING it -- publishing, being
        # rejected, and a human closing it out from under whatever label it
        # was wearing.
        for label in (_support.LABEL_DONE, _support.LABEL_REJECTED, _support.LABEL_IN_REVIEW, None):
            with self.subTest(label=label):
                self.assertTrue(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        _one_consumer(), _support.scan_of(label, closed=True),
                    ),
                )

    def test_a_real_shaped_close_counts(self) -> None:
        # The close is the whole answer, and the only spelling a real issue
        # carries it under is `state`. Asked for the double's flag instead,
        # this consumer reads as live and the ref it holds is never reclaimed.
        scan = _ChildScan(
            children=[_support.CHILD_NUMBER],
            issues={_support.CHILD_NUMBER: _RealShapedChild(_support.CHILD_NUMBER)},
            labels={_support.CHILD_NUMBER: _support.LABEL_IN_REVIEW},
        )

        self.assertTrue(
            _late_cleanup._reclaimable(_UNSTARTED, _one_consumer(), scan),
        )

    def test_a_terminal_label_alone_does_not(self) -> None:
        # Reopening a child leaves `done` / `rejected` exactly where they
        # were, so a reading taken off the label would call a child that is
        # live again terminal and delete the only copy of the work it came
        # back for.
        for label in (_support.LABEL_DONE, _support.LABEL_REJECTED):
            with self.subTest(label=label):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        _one_consumer(), _support.scan_of(label),
                    ),
                )

    def test_a_live_consumer_keeps_the_ref(self) -> None:
        for label in (_support.LABEL_IN_REVIEW, None):
            with self.subTest(label=label):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        _one_consumer(), _support.scan_of(label),
                    ),
                )

    def test_an_opaque_ledger_keeps_the_ref(self) -> None:
        # An entry this binary could not type is still a consumer, and not
        # one it can ask GitHub about.
        opaque = replace(_one_consumer(), opaque_consumers=_OPAQUE_CONSUMERS)

        self.assertFalse(
            _late_cleanup._reclaimable(
                _UNSTARTED, opaque, _support.scan_of(_support.LABEL_DONE),
            ),
        )


class WholeLedgerRuleTest(unittest.TestCase):
    """Whether the ledger names every child, asked before who among them ended.

    Every proof beside this one walks the recorded consumers, so it is only as
    complete as that list. The record's own phase is what says whether the
    list is the whole account of who was cut from the ref.
    """

    def test_no_consumer_before_a_split_is_taken(self) -> None:
        # An empty list is a FACT here, not a gap. The ref is retained before
        # the first child exists, so an owner a human closed in that interval
        # owns a ref nothing was ever cut from -- and reading it as "nobody
        # has written the list yet" left one nothing would ever reclaim, swept
        # on every cadence forever.
        self.assertTrue(
            _late_cleanup._reclaimable(
                _UNSTARTED, _support.late_generation(), _support.scan_of(_support.LABEL_DONE),
            ),
        )

    def test_a_split_still_in_its_loop_keeps_it(self) -> None:
        # The create precedes the write that records it, so while `splitting`
        # stands the list may be short by a child that already exists on
        # GitHub. The LENGTH of it decides nothing: a list of ended consumers
        # says as little about the child it has not reached as an empty one.
        for recorded in ((), (_support.CHILD_NUMBER,)):
            with self.subTest(recorded=recorded):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        _support.late_generation(
                            phase=LatePhase.SPLITTING, consumers=recorded,
                        ),
                        _support.scan_of(_support.LABEL_DONE, closed=True),
                    ),
                )

    def test_a_phase_that_proves_nothing_keeps_it(self) -> None:
        # The ways a cycle leaves the loop without finishing it, and a phase
        # this binary cannot type at all. None of them says the ledger is the
        # whole account of who was cut from the ref.
        unproven = (LatePhase.CANCELLING, LatePhase.RESTARTING, None)
        for phase in unproven:
            with self.subTest(phase=phase):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        replace(_one_consumer(), phase=phase),
                        _support.scan_of(_support.LABEL_DONE),
                    ),
                )

    def test_a_pre_split_phase_is_held_to_the_record(self) -> None:
        # A phase is not only written forwards. Every completed run claims
        # `owner_check`, writing it OVER whatever boundary it interrupted, so
        # a transaction re-entered after a crash reads as pre-split with a
        # half-filled ledger standing behind it. Believing the phase there
        # would delete the ref out from under whichever child the loop had
        # already created -- so a record naming a child is not pre-split,
        # whatever it is labelled.
        early = (LatePhase.OWNER_CHECK, LatePhase.SNAPSHOTTING)
        for phase in early:
            with self.subTest(phase=phase):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        replace(_one_consumer(), phase=phase),
                        _support.scan_of(_support.LABEL_DONE, closed=True),
                    ),
                )
                self.assertTrue(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        _support.late_generation(phase=phase), _support.scan_of(_support.LABEL_DONE),
                    ),
                )

    def test_a_count_upgrades_a_record_written_before(self) -> None:
        # What a binary that rewound the phase left behind, and the reason
        # this question is not asked of the phase alone. The transaction puts
        # its expected count down in the same write as `splitting`, ahead of
        # its first create, and nothing that moved the phase over it moved
        # that -- so a record wearing a pre-split boundary with an empty
        # ledger beside a standing count is a split that started, and its ref
        # is kept whatever the boundary now says.
        started = PinnedState(state_data={_EXPECTED_CHILDREN: 2})
        for phase in (LatePhase.OWNER_CHECK, LatePhase.SNAPSHOTTING):
            with self.subTest(phase=phase):
                self.assertFalse(
                    _late_cleanup._reclaimable(
                        started,
                        _support.late_generation(phase=phase),
                        _support.scan_of(_support.LABEL_DONE),
                    ),
                )

    def test_a_finished_split_is_asked_as_before(self) -> None:
        # Either side of the loop the list is whole, so the per-consumer proof
        # is the whole question again.
        whole = (LatePhase.SUPERSEDING, LatePhase.CLEANING_UP)
        for phase in whole:
            with self.subTest(phase=phase):
                self.assertTrue(
                    _late_cleanup._reclaimable(
                        _UNSTARTED,
                        replace(_one_consumer(), phase=phase),
                        _support.scan_of(_support.LABEL_DONE, closed=True),
                    ),
                )


def _retaining() -> tuple:
    """An umbrella whose branch is owed and whose ref is still held."""
    return _support.split_umbrella(
        LateResourceState.PENDING, snapshot=LateResourceState.RETAINED,
    )


def _one_consumer():
    """A generation recording exactly the child the scan speaks for.

    On the phase a finished split leaves, because that is what an owner with
    a consumer to prove anything about really carries: every child created
    and every one recorded, so the ledger is the whole list.
    """
    return _support.late_generation(
        phase=LatePhase.CLEANING_UP,
    ).with_consumers((_support.CHILD_NUMBER,))



if __name__ == "__main__":
    unittest.main()
