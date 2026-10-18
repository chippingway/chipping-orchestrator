# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence settled for a landed head, invalidated wherever a later tick's recovery reads the landing moving.

The real-git finish case (`rewrite_verification_recovery_support`), its run settled and finish killed at a final handoff
boundary: the landing read moving -- the checkout committed past the head, or the remote rolled back -- invalidates the
run whole on any road, nothing reviving it: not the landing put back, nor a report put back that a lost-answer reset
record read moved, nor the comment written back behind, retired again first. No run is remade, no developer launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.git.base_sync.models import _AutoRebaseRecoverySnapshot
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_landing_moved as _landing_moved,
    rewrite_publication as _publication,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import late_publication, late_push
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_landed_hold_support as landed_hold,
    rewrite_verification_recovery_support as support,
)

# A settled run's current record, the report record it is bound to, and the edit another road's writes race.
_CURRENT = "verification_evidence_current"

_REPORT = "developer_report_current"

_EDITS = "edit_pinned_state"


def _commits_past(case: support.CapturedRunCase, _head: str) -> None:
    """Commit past `_head` in `case`'s checkout, as another hand would."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)


def _puts_the_checkout_on(case: support.CapturedRunCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


def _puts_the_remote_on(case: support.CapturedRunCase, head: str) -> None:
    """Point `case`'s remote branch, and the pull request reading it, at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)
    case.pull_request.head.sha = head


def _rolls_back_under(case, head: str, live, *read):
    """`live`, the leased no-op's reading of the landing, taken over the remote rolled back to the anchor, put back."""
    _puts_the_remote_on(case, case.anchor)
    ready = live(*read)
    _puts_the_remote_on(case, head)
    return ready


class _Move(NamedTuple):
    """What moves the landing under the settled run, and what puts it back, each handed the case and the head."""

    name: str
    moves: Callable
    restores: Callable


_MOVES = (
    _Move("the checkout committed past the head", _commits_past, _puts_the_checkout_on),
    _Move(
        "the remote rolled back onto the anchor",
        lambda case, _head: _puts_the_remote_on(case, case.anchor),
        _puts_the_remote_on,
    ),
)


class SettledRunMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A run settled under the anchor goes into history wherever the recovery reads the landing moving."""

    def test_a_moved_landing_invalidates_the_run(self) -> None:
        # The recovery resets or parks without routing the head, the run invalidated first and kept so past the reply.
        for move, boundary in product(_MOVES, handoff.BOUNDARIES):
            with self.subTest(move=move.name, boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                move.moves(self, head)

                self.recovers()
                self._assert_invalidated(settled)
                move.restores(self, head)
                self.continues()
                self.recovers()

                self._assert_invalidated(settled)

    def _settles_then_dies(self, boundary: handoff.Boundary) -> tuple:
        """Land a reviewed rebase, settle its run, and kill the finish at `boundary`; the head, and the settled run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        settled = readings.pinned_records(self)[1]
        self.assertEqual(settled.binding.target.target_head, head)
        return head, settled

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence, run once, nothing pushed or launched."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


class PutBackMovementTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """Movement a recovery's write read stands, however soon another road puts the comment back behind that write."""

    def test_a_restored_run_is_retired_again(self) -> None:
        # The snapshot reads the checkout on the anchor; the run written back behind its invalidation retires again.
        head, settled = self.settles_then_dies()
        self._held = [self.gh.read_pinned_state(self.issue)]
        snapshot = _AutoRebaseRecoverySnapshot(branch=git_support.BRANCH, local_head=self.anchor, remote_head=head)
        with patch.object(self.gh, _EDITS, partial(self._puts_back_behind, self.gh.edit_pinned_state)):
            self.assertTrue(_landing_moved.abandons_off_the_landing(guarded.recovery_context(self), snapshot))

        self.assertEqual(self._held, [])
        self._assert_routed_past(head, settled)

    def test_a_report_moved_under_a_lost_record(self) -> None:
        # A report taken off before the reset's record and put back as its answer is lost still invalidates the run.
        head, settled = self.settles_then_dies()
        context = guarded.recovery_context(self)
        self._held = [self.pinned_fields(_REPORT)[0]]
        self._writes_the_report(None)
        with patch.object(self.gh, _EDITS, partial(self._answers_lost_once, self.gh.edit_pinned_state)):
            self.assertFalse(context.records_before_a_reset(context))

        self._assert_routed_past(head, settled)

    def test_a_rollback_the_no_op_read(self) -> None:
        # The leased no-op reads the remote rolled back, restored right behind: the run is invalidated before the park.
        head, settled = self.settles_then_dies()
        allowed = late_publication._PublishedCandidate(held=False, revision=head, lease=head, standing=head)
        reads = partial(_rolls_back_under, self, head, _publication.CandidatePush.reads)
        with (
            landed_hold.holding(late_push._publishes),
            patch.object(late_publication, "_holds_published_work", return_value=allowed),
            patch.object(_publication.CandidatePush, "reads", autospec=True, side_effect=reads),
        ):
            self.recovers()
        self.continues()
        self._assert_routed_past(head, settled)

    def _puts_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the comment written back as held right behind the first to drop the run."""
        answered = live(issue, staged, **options)
        drops = answered is PinnedEdit.EDITED and staged.get(_CURRENT) is None
        if drops and self._held:
            self.gh.write_pinned_state(issue, self._held.pop())
        return answered

    def _answers_lost_once(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, its first answer lost behind the report held written back."""
        if not self._held:
            return live(issue, staged, **options)
        self._writes_the_report(self._held.pop())
        return PinnedEdit.UNCONFIRMED

    def _writes_the_report(self, report) -> None:
        """Write `report` as the run's report record, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        state.set(_REPORT, report)
        self.gh.write_pinned_state(self.issue, state)

    def _assert_routed_past(self, head: str, settled) -> None:
        """`settled` invalidated whole before anything is routed, then the next poll routing `head`, nothing current."""
        self.assert_invalidated(settled)
        self.recovers()
        self.assert_routed(head)

if __name__ == "__main__":
    unittest.main()
