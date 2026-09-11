# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ending an owner observed closed earns, and what it may not skip.

A human can close a late-split owner at any point of its reconciliation, so
what these cases pin is the ordering and the idempotence rather than the
reclamation rules -- a branch, a ref, and the consumers a ref is proved
against are settled by the umbrella's own rules and are covered where those
live. What belongs to a cancellation alone: the mark that goes down before any
external call and never moves, the held plan pull request it closes over one
notice, the children it must not touch, and the terminal it may write only
once the remote is holding nothing.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import (
    LatePhase,
    LateResourceState,
)
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cancel_support import (
    ClosedOwnerCase,
)
from tests.workflow.stages.decomposition.late_cleanup_support import (
    OwnerSeed,
    RecordedDelete,
    SeededUmbrella,
    SnapshotOutcome,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
)

_DELETED = SnapshotOutcome.DELETED

_EVENT_CANCELLATION = "late_cancellation"

_EVENT_CLEANUP = "late_cleanup"

_EVENT_FAILURE = "late_failure"

_PR_RECONCILE_FAILED = "pr_reconcile_failed"

_PLAN_PR_TARGET = str(PLAN_PR_NUMBER)

_PLAN_PR_KIND = "plan_pr"

_CHILD_KIND = "child"

_CANCELLED_HEADING = "**Cancelled.**"

_MARKER = f"<!--orchestrator-late-cancellation:issue={_support.PARENT_NUMBER}"

_WORKFLOW_LOG = "orchestrator.workflow"

_DECOMPOSING_STAGE = "decomposing"

_PR_OPEN = "open"

_PR_CLOSED = "closed"

_SET_LABEL = "set_workflow_label"

_OPAQUE_RESOURCES = '[{"kind": "unknown-to-this-binary"}]'

# A pull request number the hold's own record no longer names, which is
# what makes an entry under it invisible to everything keyed to that field.
_ORPHANED_PR = "99"

_RETIRED = ((_support.PARENT_NUMBER, _support.LABEL_REJECTED),)

# The moment the post-agent owner read marked a close it caught during a
# run, which the sweep behind it settles from rather than replaces.
_GUARD_STAMP = "2026-08-20T09:00:00+00:00"


def _unstarted_owner(*, recorded: bool = True) -> SeededUmbrella:
    """A closed owner whose cycle never put anything on the remote.

    `recorded=False` is the issue beside it that never entered the late gate
    at all, which wears one of the same two swept labels and owns no cycle.
    """
    return _support.split_umbrella(
        None,
        owner=OwnerSeed(
            label=_support.DECOMPOSING,
            closed=True,
            recorded=recorded,
            child=False,
            phase=LatePhase.MEASURING,
        ),
    )


class _MarkWatchingDelete(RecordedDelete):
    """A remote that says what the pinned comment held when it was asked.

    The ordering a cancellation rests on is not observable from the record
    afterwards -- the mark and the reclamation are both there by the end of
    the pass. What tells them apart is when the mark became durable, so it is
    read at the one moment it could still be too late.
    """

    def __init__(self, outcome, github, **answers) -> None:
        super().__init__(outcome, **answers)
        self._github = github
        self.marks: list[object] = []

    def __call__(self, *call_args, **call_options):
        self.marks.append(
            self._github.pinned_data(_support.PARENT_NUMBER).get(KEYS.cancelled),
        )
        return super().__call__(*call_args, **call_options)


class CancellationMarkTest(ClosedOwnerCase, unittest.TestCase):
    """The mark is the first thing that happens and the last thing to move.

    It is what every gate below reads to refuse a spawn, an adjudication, a
    relabel, or another child, and it is what a crashed pass resumes from --
    so it goes down before the first external call and stays exactly where
    the first observation put it.
    """

    def test_the_mark_lands_before_the_delete(self) -> None:
        seeded = self._closed_owner()
        watched = _MarkWatchingDelete(_DELETED, seeded.github)

        seeded.swept_by(self, watched)

        self.assertEqual(watched.marks, [True])

    def test_it_keeps_the_boundary_it_interrupted(self) -> None:
        # `cancelling` is a boundary of its own and overwrites the one it
        # found, so the phase the cleanup rules read is kept beside the stamp.
        seeded = self._closed_owner(phase=LatePhase.SPLITTING)

        self._swept(seeded)

        pinned = self._pinned(seeded)
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertTrue(pinned.get(KEYS.cancelled_at))
        self.assertEqual(pinned.get(KEYS.phase), LatePhase.CANCELLING)
        self.assertEqual(
            pinned.get(KEYS.cancelled_phase), LatePhase.SPLITTING,
        )

    def test_it_is_marked_and_reported_once(self) -> None:
        # Bounded: the record rides the write that makes the mark true, so an
        # owner the sweep keeps coming back to does not put one cancellation
        # per cadence on both sinks.
        seeded = self._closed_owner(owed=LateResourceState.PENDING)
        seeded.github._pull_state._delete_remote_branch_returns_ok = False

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)
            stamped = self._pinned(seeded).get(KEYS.cancelled_at)
            self._swept(seeded)

        self.assertEqual(
            len(self._events_named(seeded, _EVENT_CANCELLATION)), 1,
        )
        self.assertEqual(self._pinned(seeded).get(KEYS.cancelled_at), stamped)

    def test_a_run_time_close_is_settled_not_redone(self) -> None:
        # The other observer: a close caught mid-run is marked by the
        # post-agent owner read, and the sweep behind it settles what that
        # mark left rather than opening a second cancellation over it.
        seeded = self._closed_owner()
        state = seeded.github.read_pinned_state(seeded.parent)
        _late_state.write_late_generation(state, replace(
            _late_state.read_late_generation(state).cancel(_GUARD_STAMP),
            phase=LatePhase.CANCELLING,
        ))
        seeded.github.seed_state(_support.PARENT_NUMBER, **state.data)

        taken = self._swept(seeded)

        self.assertEqual(taken.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            self._pinned(seeded).get(KEYS.cancelled_at), _GUARD_STAMP,
        )
        self.assertEqual(self._events_named(seeded, _EVENT_CANCELLATION), [])

    def test_an_unrecorded_owner_is_untouched(self) -> None:
        # Every umbrella the initial decomposer ever made is a closed issue on
        # one of the two swept labels, so a pass that marked or retired on the
        # label alone would rewrite the terminal of issues no late cycle
        # touched.
        seeded = _unstarted_owner(recorded=False)

        self._swept(seeded)

        self.assertEqual(seeded.github.write_state_calls, 0)
        self.assertEqual(self._labels(seeded), [])

    def test_a_reopen_never_moves_the_first_mark(self) -> None:
        # Irreversible within the cycle: a human who reopens the issue gets a
        # fresh cycle rather than this one resumed, so nothing a later
        # observation does may move when the obligation was taken on.
        seeded = self._closed_owner()
        self._swept(seeded)
        first = self._pinned(seeded)
        seeded.parent.closed = False

        self._swept(seeded)
        seeded.parent.closed = True
        self._swept(seeded)

        pinned = self._pinned(seeded)
        self.assertEqual(
            pinned.get(KEYS.cancelled_at), first.get(KEYS.cancelled_at),
        )
        self.assertEqual(
            pinned.get(KEYS.cancelled_phase), first.get(KEYS.cancelled_phase),
        )
        self.assertEqual(
            len(self._events_named(seeded, _EVENT_CANCELLATION)), 1,
        )


class HeldPlanPrTest(ClosedOwnerCase, unittest.TestCase):
    """The one obligation a cancellation owns that no other pass settles.

    A cycle that reached the size gate through a design discussion can be
    holding a pull request under a "do not merge" notice. Every path that
    reaches an umbrella superseded it on the way, so a cancelled cycle is the
    only shape where one is still open and still held.
    """

    def test_it_restores_says_why_and_closes(self) -> None:
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)
        github = seeded.github

        self._swept(seeded)

        self.assertEqual(
            github.edited_pr_bodies, [(PLAN_PR_NUMBER, PLAN_PR_BODY)],
        )
        posted = github.posted_pr_comments
        self.assertEqual([number for number, _ in posted], [PLAN_PR_NUMBER])
        self.assertIn(_CANCELLED_HEADING, posted[0][1])
        self.assertIn(_MARKER, posted[0][1])
        self.assertEqual(github.pulls[PLAN_PR_NUMBER].state, _PR_CLOSED)

    def test_what_it_did_reaches_both_sinks(self) -> None:
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)

        self._swept(seeded)

        reported = self._events_named(
            seeded, _EVENT_CLEANUP, _PLAN_PR_KIND,
        )
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0].get("outcome"), _support.STATE_RECONCILED)
        self.assertEqual(reported[0].get("stage"), _DECOMPOSING_STAGE)
        self.assertEqual(
            self._states(seeded)[_PLAN_PR_TARGET], _support.STATE_RECONCILED,
        )

    def test_a_settled_plan_pr_is_told_only_once(self) -> None:
        # Re-asked on every visit, because its state is a human's to change --
        # and silent on the visits that change nothing: the notice is gated on
        # this cycle's marker already on the thread, and an entry saying what
        # it already said is neither written again nor reported again.
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)
        self._swept(seeded)
        written = seeded.github.write_state_calls

        self._swept(seeded)

        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(seeded.github.write_state_calls, written)
        self.assertEqual(
            len(self._events_named(seeded, _EVENT_CLEANUP, _PLAN_PR_KIND)),
            1,
        )

    def test_a_hold_that_will_not_lift_stops_it(self) -> None:
        # The preserved description is the only copy of what the hold
        # replaced, so a pull request closed while the hold is still on it is
        # a human's words replaced for good.
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)
        seeded.github.edit_pr_body = MagicMock(side_effect=RuntimeError)

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        github = seeded.github
        self.assertEqual(github.posted_pr_comments, [])
        self.assertEqual(github.pulls[PLAN_PR_NUMBER].state, _PR_OPEN)
        self.assertEqual(self._states(seeded)[_PLAN_PR_TARGET], _support.STATE_FAILED)

    def test_a_refused_close_is_reported(self) -> None:
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)
        seeded.github._pull_state._unsupersedable_prs.add(PLAN_PR_NUMBER)
        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        self.assertEqual(self._states(seeded)[_PLAN_PR_TARGET], _support.STATE_FAILED)
        self.assertEqual(
            [
                record["failure"]
                for record in self._events_named(seeded, _EVENT_FAILURE)
            ],
            [_PR_RECONCILE_FAILED],
        )
        self.assertEqual(self._labels(seeded), [])

    def test_a_refused_close_is_asked_again(self) -> None:
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded)
        seeded.github._pull_state._unsupersedable_prs.add(PLAN_PR_NUMBER)
        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)
        seeded.github._pull_state._unsupersedable_prs.clear()

        self._swept(seeded)

        self.assertEqual(
            self._states(seeded)[_PLAN_PR_TARGET], _support.STATE_RECONCILED,
        )
        self.assertEqual(tuple(self._labels(seeded)), _RETIRED)

    def test_a_hold_it_cannot_prove_is_never_closed(self) -> None:
        # A number with no preserved description is a damaged record, not a
        # partial one: the two are written as one thing. The release in front
        # of the close refuses it silently, having no copy to put back, so
        # closing behind that would end a pull request nothing here ever
        # marked -- somebody else's change, for a number a human typed.
        seeded = self._closed_owner(snapshot=None)
        self._holding_plan_pr(seeded, preserved=False)

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        github = seeded.github
        self.assertEqual(github.pulls[PLAN_PR_NUMBER].state, _PR_OPEN)
        self.assertEqual(github.posted_pr_comments, [])
        self.assertEqual(self._labels(seeded), [])


class BoundaryTest(ClosedOwnerCase, unittest.TestCase):
    """What a close costs depends only on how far the cycle actually got.

    The ledgers say what exists, so a cycle cancelled before a side effect
    owes nothing for it and one cancelled after owes exactly what it created
    -- and the boundary the cancellation kept is what keeps that answer
    available once the phase field names the cancellation instead.
    """

    def test_a_cycle_that_owes_nothing_just_ends(self) -> None:
        seeded = _unstarted_owner()

        deleted = self._swept(seeded)

        self.assertEqual(deleted.refs, [])
        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertEqual(tuple(self._labels(seeded)), _RETIRED)

    def test_a_split_in_flight_keeps_its_ref(self) -> None:
        # The split creates a child and records it in two writes, so the
        # consumer ledger may be one short of an issue that already exists --
        # and a cancellation is exactly when nothing is coming back to prove
        # it whole.
        seeded = self._closed_owner(phase=LatePhase.SPLITTING)

        deleted = self._swept(seeded)

        self.assertEqual(deleted.refs, [])
        self.assertEqual(self._states(seeded)[_support.SNAPSHOT_REF], _support.STATE_RETAINED)
        self.assertEqual(self._labels(seeded), [])

    def test_a_child_that_exists_is_left_alone(self) -> None:
        seeded = self._closed_owner(
            phase=LatePhase.SPLITTING, child_closed=False,
        )

        self._swept(seeded)

        github = seeded.github
        child = github.get_issue(_support.CHILD_NUMBER)
        self.assertFalse(child.closed)
        self.assertEqual(github.workflow_label(child), _support.LABEL_BLOCKED)
        self.assertEqual(github.posted_comments, [])

    def test_a_reclaimed_ref_still_touches_no_child(self) -> None:
        # The other half of the same claim, and the visit that could most
        # easily break it: the ref actually goes. Every consumer it was kept
        # for is READ -- proving each ended is what permits the delete -- and
        # that reading is the whole of what any of them costs. No comment, no
        # pinned write, no label, and the child is left closed as it was.
        seeded = self._closed_owner()
        github = seeded.github
        recorded = dict(github.pinned_data(_support.CHILD_NUMBER))

        deleted = self._swept(seeded)

        child = github.get_issue(_support.CHILD_NUMBER)
        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(github.posted_comments, [])
        self.assertEqual(github.pinned_data(_support.CHILD_NUMBER), recorded)
        self.assertEqual(github.workflow_label(child), _support.LABEL_DONE)
        self.assertTrue(child.closed)

    def test_a_superseded_branch_is_taken_once(self) -> None:
        # The crash window the transaction cannot close: it settles the held
        # plan PR and records the branch that PR carried in two writes, since
        # the second is the retirement and retiring ahead of a supersession
        # that might not land would let the children loose. A close landing in
        # between leaves a branch nothing on the record names -- and settling
        # around it would retire the owner over one the remote keeps for good.
        #
        # What says the supersession was REACHED is the announcement's own
        # receipt, not the phase: a park there is resumed from the top of the
        # transaction, which rewrites the earlier boundaries while stepping
        # over the announcement it already made. And only where nothing is
        # recorded: a `reconciled` entry re-taken as owed would ask the remote
        # to delete it again.
        for recorded, phase, asked in (
            (None, LatePhase.SUPERSEDING, [_support.SUPERSEDED_BRANCH]),
            (LateResourceState.RECONCILED, LatePhase.SUPERSEDING, []),
            (None, LatePhase.SPLITTING, [_support.SUPERSEDED_BRANCH]),
        ):
            with self.subTest(recorded=recorded, phase=phase):
                seeded = _support.split_umbrella(
                    recorded,
                    snapshot=LateResourceState.RETAINED,
                    owner=OwnerSeed(
                        label=_support.DECOMPOSING,
                        closed=True,
                        child=False,
                        announced=True,
                        phase=phase,
                    ),
                )

                with self.assertLogs(_WORKFLOW_LOG):
                    self._swept(seeded)

                self.assertEqual(
                    seeded.github.deleted_remote_branches, asked,
                )
                self.assertEqual(
                    self._states(seeded)[_support.SUPERSEDED_BRANCH],
                    _support.STATE_RECONCILED,
                )

    def test_an_unsettled_plan_pr_keeps_its_branch(self) -> None:
        # `superseding` is written BEFORE the supersession is attempted, so a
        # record standing there says the attempt was reached and nothing about
        # whether it landed. Inferring the branch from it while the pull
        # request is still open would delete, out from under a change a human
        # can still see, the branch that change is built on -- which is the
        # order the transaction itself takes, recording the branch only in the
        # retirement that FOLLOWS a supersession. Nothing is lost by waiting:
        # the pull request is re-asked on every visit, and the one that closes
        # it takes the branch on the way the sibling case above does.
        seeded = _support.split_umbrella(
            None,
            snapshot=LateResourceState.RETAINED,
            owner=OwnerSeed(
                label=_support.DECOMPOSING,
                closed=True,
                child=False,
                phase=LatePhase.SUPERSEDING,
            ),
        )
        self._holding_plan_pr(seeded)
        seeded.github._pull_state._unsupersedable_prs.add(PLAN_PR_NUMBER)

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        self.assertEqual(
            seeded.github.pulls[PLAN_PR_NUMBER].state, _PR_OPEN,
        )
        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertNotIn(_support.SUPERSEDED_BRANCH, self._states(seeded))
        self.assertEqual(self._labels(seeded), [])

    def test_a_cancelled_ref_stays_reclaimable(self) -> None:
        # The consumer rule is unchanged by the cancellation, and asking it
        # needs the boundary the mark kept: a live consumer holds the ref, and
        # the visit after it ends takes the ref and the terminal together.
        seeded = self._closed_owner(child_closed=False)

        held = self._swept(seeded)
        self.assertEqual(held.refs, [])
        self.assertEqual(self._states(seeded)[_support.SNAPSHOT_REF], _support.STATE_RETAINED)
        self.assertEqual(self._labels(seeded), [])

        seeded.github.get_issue(_support.CHILD_NUMBER).closed = True
        taken = self._swept(seeded)

        self.assertEqual(taken.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(taken.shas, [CANDIDATE_SHA])
        self.assertEqual(tuple(self._labels(seeded)), _RETIRED)


class TerminalTest(ClosedOwnerCase, unittest.TestCase):
    """`rejected` is the only label this path writes, and it is written last.

    It takes the issue out of the closed-owner sweep for good, so an owner
    that reached it over an unreclaimed remote would leave that object with
    nothing coming back for it.
    """

    def test_a_refused_branch_holds_the_terminal(self) -> None:
        seeded = self._refusing_remote()

        self.assertEqual(
            self._states(seeded)[_support.SUPERSEDED_BRANCH], _support.STATE_FAILED,
        )
        self.assertEqual(self._labels(seeded), [])

    def test_a_refused_branch_is_asked_again(self) -> None:
        seeded = self._refusing_remote()
        seeded.github._pull_state._delete_remote_branch_returns_ok = True

        self._swept(seeded)

        self.assertEqual(
            self._states(seeded)[_support.SUPERSEDED_BRANCH], _support.STATE_RECONCILED,
        )
        self.assertEqual(tuple(self._labels(seeded)), _RETIRED)

    def test_a_failed_label_waits_for_next_pass(self) -> None:
        # The obligations are settled and recorded by then, so a refusal costs
        # one more visit rather than the pass that did the work.
        seeded = _unstarted_owner()
        refusing = MagicMock(side_effect=RuntimeError)

        with patch.object(seeded.github, _SET_LABEL, refusing), self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        refusing.assert_called_once()

        self._swept(seeded)

        self.assertEqual(tuple(self._labels(seeded)), _RETIRED)

    def test_a_ledger_the_branch_rule_misses_holds(self) -> None:
        # Two shapes the branch-and-ref reading walks straight past. An entry
        # this binary cannot type blocks outright -- nothing on that ledger
        # may be reclaimed or recorded around it. A plan-PR obligation left
        # under a number the hold's own record no longer names is one the
        # reclamation owner never looks at at all. Retiring over either would
        # leave it behind on an issue nothing revisits, and would refuse the
        # restart that terminal is supposed to authorize, since a restart
        # counts every unreconciled resource as owed.
        orphaned = [{
            "kind": _PLAN_PR_KIND,
            "target": _ORPHANED_PR,
            "state": _support.STATE_FAILED,
        }]
        for ledger in (_OPAQUE_RESOURCES, orphaned):
            with self.subTest(ledger=ledger):
                seeded = self._closed_owner(owed=LateResourceState.PENDING)
                seeded.github.seed_state(
                    _support.PARENT_NUMBER,
                    **{**self._pinned(seeded), KEYS.resources: ledger},
                )

                with self.assertLogs(_WORKFLOW_LOG):
                    self._swept(seeded)

                self.assertTrue(self._pinned(seeded).get(KEYS.cancelled))
                self.assertEqual(seeded.github.deleted_remote_branches, [])
                self.assertEqual(self._labels(seeded), [])

    def test_a_reopened_plan_pr_is_closed_again(self) -> None:
        # A `reconciled` entry records what an earlier visit did, and a pull
        # request is not a thing that stays where it was put. An owner the
        # sweep is still visiting for a branch it cannot delete would
        # otherwise reach `rejected` -- and leave the sweep for good -- beside
        # a change that is open again under a cancelled cycle.
        seeded = self._closed_owner(
            owed=LateResourceState.PENDING, snapshot=None,
        )
        self._holding_plan_pr(seeded)
        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)
        seeded.github.pulls[PLAN_PR_NUMBER].state = _PR_OPEN

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        self.assertEqual(
            seeded.github.pulls[PLAN_PR_NUMBER].state, _PR_CLOSED,
        )
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)

    def test_a_standing_refusal_reports_once(self) -> None:
        # The retry is every visit; the record of it is not. A remote that
        # goes on refusing the same delete is one fact, and repeating it per
        # cadence would bury the transition that matters under a stream of
        # identical records and cost a pinned write apiece -- so the sinks
        # carry the move to `failed` and nothing after it, while the log goes
        # on saying what is still held.
        seeded = self._refusing_remote()
        written = seeded.github.write_state_calls

        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)

        self.assertEqual(len(self._events_named(seeded, _EVENT_CLEANUP)), 1)
        self.assertEqual(len(self._events_named(seeded, _EVENT_FAILURE)), 1)
        self.assertEqual(seeded.github.write_state_calls, written)
        self.assertEqual(
            seeded.github.deleted_remote_branches,
            [_support.SUPERSEDED_BRANCH, _support.SUPERSEDED_BRANCH],
        )

    def _refusing_remote(self) -> SeededUmbrella:
        """One pass over an owner whose branch the remote would not delete."""
        seeded = self._closed_owner(
            owed=LateResourceState.PENDING, snapshot=None,
        )
        seeded.github._pull_state._delete_remote_branch_returns_ok = False
        with self.assertLogs(_WORKFLOW_LOG):
            self._swept(seeded)
        return seeded


if __name__ == "__main__":
    unittest.main()
