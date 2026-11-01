# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer side of the owner guard: what a finished revision may say.

The same read a finished adjudication passes, at the same point and for the
same reason -- the developer ran for as long as it ran, and a human who closed
the issue in between ended the whole cycle rather than this tick. What differs
is what the two ends of a revision owe the issue: a candidate re-measured and
a reconciliation that could not be made both have a sentence for a human, and
neither is said until the read comes back open.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition import captured_revision_support as _captured
from tests.workflow.stages.decomposition.late_content_replies import reply
from tests.workflow.stages.decomposition.late_content_support import KEY_GENERATION, PARK_REVISION_DIRTY
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_ACK,
    DEV_PIN,
    DIRTY_NOTICE,
    DIRTY_TREE,
    REMEASURED_NOTICE,
    REVISED_SHA,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    adjudicate,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    ERROR,
    PARK_OWNER_UNREADABLE,
    WORKFLOW_LOG,
    _ClosedDuringRun,
    unreadable_owner,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS

SECOND_GENERATION = 2

# What a revision a recovery finished leaves the record on: the advanced
# generation, over the commit it re-measured.
_REVISED = (SECOND_GENERATION, REVISED_SHA)
_REVISED_AT = (KEY_GENERATION, KEYS.candidate_sha)


def _park_reason(pinned) -> object:
    """What this pinned comment says the issue is being held for."""
    return pinned.get(KEYS.park_reason)


class RevisionOwnerGuardTest(RevisionCase):
    """A finished developer run is guarded exactly as a finished verdict is."""

    def test_a_closed_owner_cancels_the_revision(self) -> None:
        self._seed(**DEV_PIN)
        reply(self.issue)
        closed = _ClosedDuringRun(self.issue, agent_reply(DEV_ACK))

        revised, resumed = self._revise(closed)

        resumed.assert_called_once()
        self.assertEqual(revised.disposition, _LateDisposition.CANCELLED)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertEqual(pinned.get(KEYS.phase), LatePhase.CANCELLING)
        # The measurement is durable before the read, so the cancellation
        # costs the developer run nothing it had already produced -- and
        # the notice it would have earned is not said to a closed issue.
        self.assertEqual(pinned.get(KEYS.candidate_sha), REVISED_SHA)
        self.assertNotIn(REMEASURED_NOTICE, self._said())

    def test_a_closed_owner_cancels_a_parked_revision(self) -> None:
        # The reconciliation could not be made and the issue was handed back,
        # but the run was paid for all the same -- and the closure ends the
        # cycle it was handed back in.
        self._seed(**DEV_PIN)
        reply(self.issue)
        closed = _ClosedDuringRun(self.issue, agent_reply(DEV_ACK))

        revised, _resumed = self._revise(
            closed, seed=WorktreeSeed(dirty=DIRTY_TREE),
        )

        self.assertEqual(revised.disposition, _LateDisposition.CANCELLED)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertEqual(_park_reason(pinned), PARK_REVISION_DIRTY)
        self.assertNotIn(DIRTY_NOTICE, self._said())

    def test_an_open_owner_says_what_was_measured(self) -> None:
        self._seed(**DEV_PIN)
        reply(self.issue)

        revised, _resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        self.assertIn(REMEASURED_NOTICE, self._said())

    def test_an_unreadable_owner_parks_the_revision(self) -> None:
        self._seed(**DEV_PIN)
        reply(self.issue)

        with unreadable_owner(self.github), self.assertLogs(WORKFLOW_LOG, level=ERROR):
            revised, _resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(_park_reason(pinned), PARK_OWNER_UNREADABLE)
        self.assertEqual(pinned.get(KEYS.candidate_sha), REVISED_SHA)
        self.assertEqual(pinned.get(KEY_GENERATION), SECOND_GENERATION)
        self.assertNotIn(REMEASURED_NOTICE, self._said())

    def _said(self) -> str:
        """Everything this tick posted on the issue, as one blob."""
        return "".join(
            body for _number, body in self.github.posted_comments
        )


class StalledRevisionGuardTest(RevisionCase):
    """A reconciliation that could not be made is guarded, and still speaks.

    Nothing supersedes a stalled revision, so no later attempt re-takes its
    park and re-announces it. Its sentence is the only thing that will ever
    say what the human has to do -- which is why an unreadable owner releases
    it and a healed read does not repeat it.
    """

    def test_a_parked_revision_keeps_its_reason(self) -> None:
        revised = self._park_a_revision_unread()

        self.assertEqual(revised.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(_park_reason(pinned), PARK_REVISION_DIRTY)
        self.assertTrue(pinned.get(KEYS.owner_check_pending))

    def test_a_parked_revision_still_says_what_to_do(self) -> None:
        # Nothing supersedes a stalled revision, so no later attempt re-takes
        # this park and re-announces it. Holding its sentence back for a read
        # that failed would leave the issue `awaiting_human` with nothing
        # saying what the human has to do -- for as long as the read kept
        # failing, which is unbounded.
        self._park_a_revision_unread()

        self.assertIn(DIRTY_NOTICE, self._said())
        self.assertTrue(self._pinned().get(KEYS.awaiting))

    def test_the_healed_read_repeats_no_notice(self) -> None:
        # The read comes back and nobody has replied. The pending check is
        # retired, the park stands where it was, and the sentence the human
        # already has is not said to them a second time.
        self._park_a_revision_unread()
        said = len(self.github.posted_comments)

        outcome, spawn = adjudicate(self.github, self.issue)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(_park_reason(pinned), PARK_REVISION_DIRTY)
        self.assertNotIn(KEYS.owner_check_pending, pinned)
        self.assertEqual(len(self.github.posted_comments), said)

    def _park_a_revision_unread(self):
        """One revision that could not be reconciled, its owner unreadable."""
        self._seed(**DEV_PIN)
        reply(self.issue)
        with unreadable_owner(self.github), self.assertLogs(WORKFLOW_LOG, level=ERROR):
            revised, _resumed = self._revise(
                seed=WorktreeSeed(dirty=DIRTY_TREE),
            )
        return revised

    def _said(self) -> str:
        """Everything this tick posted on the issue, as one blob."""
        return "".join(
            body for _number, body in self.github.posted_comments
        )


class RecoveredRevisionGuardTest(_captured.CapturedRevisionCase):
    """A held revision a recovery finishes passes the owner read its own tick would have."""

    def test_the_owner_is_read_behind_the_handoff(self) -> None:
        # The re-measured candidate and the report it hands the delivery are
        # durable before the read, so a close or a read GitHub refuses behind
        # them costs nothing the recovery produced -- and the notice the
        # re-measurement earns is said to neither. A close is settled by the
        # recovery's own owner read. An issue nobody can read holds the
        # recovery's next write, the controls it is asked about unreadable,
        # and the read the handoff left owed is taken -- and parks -- on the
        # dispatch after it.
        for name, moved, settled, later in (
            ("closed", self._closes, {KEYS.phase: LatePhase.CANCELLING}, False),
            ("unreadable", self._refuses_reads, {KEYS.park_reason: PARK_OWNER_UNREADABLE}, True),
        ):
            with self.subTest(owner=name):
                self._held_over_guidance()

                with patch.object(self.github, "edit_pinned_state", _BehindTheHandoff(self.github, moved)):
                    self._dispatched().assert_not_called()
                if later:
                    self._read_on_the_next_dispatch()

                pinned = self._pinned()
                self.assertEqual(_captured.capture_of(pinned).stage, _captured.HANDED_OFF)
                self.assertEqual(tuple(map(pinned.get, _REVISED_AT)), _REVISED)
                self.assertEqual({field: pinned.get(field) for field in settled}, settled)
                self.assertNotIn(REMEASURED_NOTICE, "".join(self._bodies()))

    def _held_over_guidance(self) -> None:
        """A revision bought by guidance, held to its capture under `paused` and released."""
        self._seed(**DEV_PIN)
        reply(self.issue)
        self._held()
        self._released()

    def _read_on_the_next_dispatch(self) -> None:
        """Assert the owner read is still owed, and dispatch the issue again to take it."""
        self.assertTrue(self._pinned()[KEYS.owner_check_pending])
        self._dispatched().assert_not_called()

    def _closes(self) -> None:
        """A human closing the issue."""
        self.issue.closed = True

    def _refuses_reads(self) -> None:
        """GitHub refusing every read of the issue from here on."""
        self.enterContext(patch.object(self.github, "get_issue", side_effect=RuntimeError))


class _BehindTheHandoff:
    """The strict edits a tick makes, `moved` called once the one handing a capture off has landed."""

    def __init__(self, github, moved) -> None:
        self._edits = github.edit_pinned_state
        self._moved = moved

    def __call__(self, issue, state, **options):
        sent = self._edits(issue, state, **options)
        handed = _captured.capture_of(state.state_data)
        if handed is not None and handed.stage is _captured.HANDED_OFF:
            self._moved()
        return sent


if __name__ == "__main__":
    import unittest

    unittest.main()
