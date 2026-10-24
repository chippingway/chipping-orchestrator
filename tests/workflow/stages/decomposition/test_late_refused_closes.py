# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What close recovery and the closed-owner sweep do over a pinned record admission refuses.

The comment still carries what a cycle wrote and reads back empty, which is
an owner nothing touched. A close receipt is scoped to the cycle the record
names, and the sweep's every answer -- the mark, the adoption of a retired
cycle, the terminal an umbrella earned, the label that keeps an owed ending
reachable, the reclamation -- is read off the same record. Over this one,
none of them is given: no receipt is posted or remembered, nothing is
written, relabelled, reclaimed, or torn down, and the close this process
holds does not stand in for the record. The reading is kept, as a read that
established nothing keeps it. A record a human edits into one admission
refuses while the sweep is ending its cycle stops the pass at the first
checkpoint the comment no longer takes.

The same owners over a current record are `test_late_closed_sweep.py`'s and
`test_late_receipt_race.py`'s.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import observation_receipts as _observation_receipts, observations as _observations
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_close_observation as _late_close_observation,
    late_sweep as _late_sweep,
    umbrella_terminal as _umbrella_terminal,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin
from tests.workflow.observation_support import ObservedCloseCase, left_on_github, receipt_for, refuse_record
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cancel_support import hold_plan_pr
from tests.workflow.stages.decomposition.late_seam_support import RecordedDelete, SnapshotOutcome, local_teardown
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
    late_generation,
    seed_late_issue,
)

_WARNING = "WARNING"

_SLUG = _TEST_SPEC.slug

# What the sweep and the receipt each say they withheld over a refused record,
# and the version that record was found under against the one admitted.
_NO_CLEANUP = "running no cleanup"
_FOUND_VERSION = "found schema_version None, supported 1"

# The terminal a fully settled ending writes, which a stopped pass never reaches.
_REJECTED = "rejected"

# Each refused owner: whether its record had retired its cycle with the
# umbrella terminal due, and whether the comment still parses at all.
_REFUSED_OWNERS = (
    (False, True),
    (False, False),
    (True, True),
    (True, False),
)


class RefusedOwnerSweepTest(ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase):
    """A closed owner whose record admission refuses, swept for nothing.

    Over a current record the first owner here has its cycle marked, its
    held plan pull request closed, its branch and ref reclaimed, and
    `rejected` written; the second has its retired cycle adopted back off the
    receipt and the latch scoped to it.
    """

    def test_nothing_is_marked_adopted_or_reclaimed(self) -> None:
        for retired, parsed in _REFUSED_OWNERS:
            with self.subTest(retired=retired, parsed=parsed):
                seeded = self._refused_owner(retired=retired, parsed=parsed)
                before = left_on_github(seeded.github, _support.PARENT_NUMBER)

                teardown = self._swept(seeded)

                self.assertEqual(left_on_github(seeded.github, _support.PARENT_NUMBER), before)
                self.assertEqual(teardown.issues, [])
                teardown.branch_deleted.assert_not_called()

    def _refused_owner(self, *, retired: bool, parsed: bool):
        """A closed `decomposing` owner holding a plan PR, its record refused, a close held scoped to its cycle."""
        self._fresh_process()
        seeded = _support.split_umbrella(
            LateResourceState.PENDING,
            snapshot=LateResourceState.RETAINED,
            owner=_support.OwnerSeed(label=_support.DECOMPOSING, closed=True),
        )
        hold_plan_pr(seeded.github, seeded.parent)
        if retired:
            _retired_with_its_terminal_due(seeded)
        refuse_record(seeded.github, _support.PARENT_NUMBER, parsed=parsed)
        self._latch_close(_SLUG, _support.PARENT_NUMBER)
        _observations.scope_close(_SLUG, _support.PARENT_NUMBER, CYCLE_ID)
        return seeded

    def _swept(self, seeded):
        """Sweep the owner through the real handler, and hand back the local teardown it held."""
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
            teardown = _support.walk_owner(self, seeded, _late_sweep._handle_closed_owner_cleanup)
            said = list(logged.output)
        self.assertEqual((remote.refs, remote.observed), ([], []))
        self.assertTrue(any(_NO_CLEANUP in line for line in said), said)
        return teardown


class RefusedRecordReceiptTest(ObservedCloseCase, unittest.TestCase):
    """A refused record, asked by the poll posting its receipt and by the one that claim shuts out.

    It reads back with no cycle, which a current record would have both polls
    answer as nothing to end. The poll holding the claim posts and remembers
    nothing, and the one the claim shuts out asks the record for itself --
    and both keep the reading, since the record said nothing at all.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        seed_late_issue(self.github, late_generation())
        refuse_record(self.github, LATE_ISSUE_NUMBER)
        self._latch_close(_SLUG, LATE_ISSUE_NUMBER)

    def test_neither_poll_posts_and_both_keep_it(self) -> None:
        for shut_out in (False, True):
            with self.subTest(shut_out=shut_out):
                posting = _observation_receipts.claim_receipt_post(_SLUG, LATE_ISSUE_NUMBER) if shut_out else None

                kept, said = self._recorded()

                if posting is not None:
                    _observation_receipts.release_receipt_post(posting)
                self.assertTrue(kept)
                self.assertEqual(self.github.posted_comments, [])
                self.assertTrue(any(_FOUND_VERSION in line for line in said), said)
                self.assertIsNone(self._remembered(), "no receipt is remembered for it")

    def _recorded(self) -> tuple[bool, list[str]]:
        """One poll's attempt at the durable half, and what it said."""
        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
            kept = _late_close_observation._record_observed_close(self.github, _TEST_SPEC, LATE_ISSUE_NUMBER)
            return kept, list(logged.output)

    def _remembered(self) -> int | None:
        """The cycle this process remembers a receipt landed for, if any."""
        claim = _observation_receipts.claim_receipt_post(_SLUG, LATE_ISSUE_NUMBER)
        _observation_receipts.release_receipt_post(claim)
        return claim.landed


class RefusedMidPassTest(ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase):
    """A record a human edits into one admission refuses while the sweep is ending its cycle.

    The pass read it supported under the writer claim, and every step behind a
    checkpoint acts on the record saying what that checkpoint wrote -- so a
    checkpoint the comment does not take stops the pass right there, with
    the failure handed to whatever holds it and nothing behind it done.
    """

    def test_a_refused_mark_stops_before_anything(self) -> None:
        # The first write is the cancellation itself, ahead of every external
        # call: the plan PR stays open, nothing is deleted or torn down, and
        # no terminal is written.
        seeded, editing = self._edited_owner(lambda _written: True)
        before = left_on_github(seeded.github, _support.PARENT_NUMBER)

        teardown = self._stopped(seeded)

        before["record"] = editing.edited
        self.assertEqual(left_on_github(seeded.github, _support.PARENT_NUMBER), before)
        self.assertEqual(teardown.issues, [])
        teardown.branch_deleted.assert_not_called()

    def test_a_refused_order_keeps_the_ref(self) -> None:
        # Later in the pass, the decision that orders the ref's deletion is the
        # checkpoint the edit lands ahead of: the ref is never asked to go, and
        # the terminal behind it is never written.
        seeded, editing = self._edited_owner(_orders_the_ref)

        self._stopped(seeded)

        self.assertIs(seeded.github._pinned[_support.PARENT_NUMBER], editing.edited)
        self.assertNotIn((_support.PARENT_NUMBER, _REJECTED), seeded.github.label_history)

    def _edited_owner(self, when):
        """The closed owner holding a plan PR, its writer edited ahead of the write `when` picks."""
        self._fresh_process()
        seeded = _support.split_umbrella(
            LateResourceState.PENDING,
            snapshot=LateResourceState.RETAINED,
            owner=_support.OwnerSeed(label=_support.DECOMPOSING, closed=True),
        )
        hold_plan_pr(seeded.github, seeded.parent)
        editing = _EditedBefore(seeded.github, when)
        seeded.github.write_pinned_state = editing
        return seeded, editing

    def _stopped(self, seeded):
        """Sweep the owner and see the pass stop, handing back the local teardown it held."""
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), local_teardown() as teardown, self.assertLogs(_support.WORKFLOW_LOG):
            self.assertRaises(
                RuntimeError, self._run,
                lambda: _late_sweep._handle_closed_owner_cleanup(seeded.github, _TEST_SPEC, seeded.parent),
                run_agent=_agent(),
            )
            self.assertEqual(remote.refs, [])
            return teardown


class _EditedBefore:
    """The pinned writer, behind a human who edits the comment into one admission refuses first.

    The edit lands just ahead of the first write `when` picks, keeping the
    comment's id as an edit in place does; `edited` is the record it left.
    """

    def __init__(self, github, when) -> None:
        self._github = github
        self._writing = github.write_pinned_state
        self._when = when
        self.edited = None

    def __call__(self, issue, state):
        """Edit the comment where this is the write picked, then write as the client does."""
        if self.edited is None and self._when(state.data):
            comment_id = self._github._pinned[issue.number].comment_id
            refuse_record(self._github, issue.number)
            self.edited = self._github._pinned[issue.number]
            self.edited.comment_id = comment_id
        return self._writing(issue, state)


def _orders_the_ref(written: dict) -> bool:
    """Whether this write is the decision that orders the snapshot ref's deletion."""
    ordered = (_support.SNAPSHOT_REF, LateResourceState.RECLAIMING)
    return any(
        (entry.get("target"), entry.get("state")) == ordered
        for entry in written.get("late_resources") or ()
    )


def _retired_with_its_terminal_due(seeded) -> None:
    """The owner past its umbrella terminal's retirement write, the close inside it on the thread.

    The record names the cycle it dropped and the terminal it earned, and the
    receipt names that same cycle -- everything a current record would have
    the sweep put the cycle back over and finish from.
    """
    github = seeded.github
    state = github.read_pinned_state(seeded.parent)
    _umbrella_terminal._retired_cycle(state)
    github.seed_state(_support.PARENT_NUMBER, **{**state.data, _support.RESOLVED_STAMP: _support.CANCELLED_AT})
    github.comment(seeded.parent, receipt_for(_support.PARENT_NUMBER, CYCLE_ID))


if __name__ == "__main__":
    unittest.main()
