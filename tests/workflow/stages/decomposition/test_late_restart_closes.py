# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close held for a cycle restarted since, reconciled under the issue's writer claim.

Another poller on this host can settle the cycle a close ended and start the
fresh one an operator authorized, and so can this process's own restart, which
no claim note records. A close scoped to the old cycle -- or read before the
restart -- is then no close of the record's cycle: the barrier, the poll's
guard, and the sweep each leave that cycle unmarked, and the poll posts and
remembers no receipt for it, while a close read standing on it ends it and is
receipted. Entered directly through `claiming_closes()`, holding the claim,
since no production pass takes either yet -- and outside it, each still ends
the record's cycle on the latch alone.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    observations as _observations,
    retiring_cycles as _retiring_cycles,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_close_observation as _late_close_observation,
    late_sweep as _late_sweep,
)
from tests.support.fakes import FakeGitHubClient
from tests.support.writer_claims import claimable
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase, read_now, receipt_for
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
    late_generation,
    seed_late_issue,
)

_SLUG = _TEST_SPEC.slug

_WORKFLOW_LOG = "orchestrator.workflow"

# The cycle the record moved to after the close was read.
_RESTARTED = CYCLE_ID + 1


class _Behind:
    """A client read that answers as things stood, and has `then` happen behind it the first time."""

    def __init__(self, read, then) -> None:
        self._read = read
        self._then = then

    def __call__(self, *asked):
        """Answer the read, then let what follows it happen once."""
        answered = self._read(*asked)
        then = self._then
        self._then = None
        if then is not None:
            then()
        return answered


class _RestartedCase(ObservedCloseCase):
    """An owner on a restarted cycle, open again, holding a close scoped to the cycle before it."""

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.owner = seed_late_issue(self.github, late_generation(cycle_id=_RESTARTED))
        self._latch_close(_SLUG, LATE_ISSUE_NUMBER)
        _observations.scope_close(_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID)

    def _claimed(self, *, alongside: bool = False):
        """This owner's writer claim, every reconciliation inside answering as a pass under it."""
        return self._under_the_claim(self.github.repo_id, LATE_ISSUE_NUMBER, alongside=alongside)

    def _state(self):
        """The owner's record as it stands."""
        return self.github.read_pinned_state(self.owner)

    def _recorded(self, cycle_id: int) -> None:
        """Put a live generation of this cycle on the owner's record."""
        state = self._state()
        _late_state.write_late_generation(state, late_generation(cycle_id=cycle_id))
        self.github.write_pinned_state(self.owner, state)

    def _cancelled(self) -> bool:
        """Whether the record's cycle is marked over."""
        return _late_state.read_late_generation(self._state()).cancelled

    def _marked_by_the_poll(self, read_at: int | None = None) -> bool:
        """Apply the poll's closed reading under the claim, and say whether the tick stops."""
        with self._claimed():
            return _late_close_observation._mark_observed_close(
                self.github, _TEST_SPEC, self.owner, self._state(), read_at,
            )


class RestartedCycleTest(_RestartedCase, unittest.TestCase):
    """The close the old cycle was ended by, met by each claim-aware reconciliation."""

    def test_the_barrier_spares_the_fresh_cycle(self) -> None:
        with self._claimed():
            spared = _late_close_observation._latched_close_ends(self.github, _TEST_SPEC, self.owner, self._state())
        self.assertFalse(spared)
        self.assertFalse(self._cancelled())

        with self.assertLogs(_WORKFLOW_LOG):
            ended = _late_close_observation._latched_close_ends(self.github, _TEST_SPEC, self.owner, self._state())
        self.assertTrue(ended, "outside the claim the latch alone ends it, as production does")
        self.assertTrue(self._cancelled())

    def test_the_poll_guard_stops_without_marking(self) -> None:
        # Open again, the close cannot be tied to the fresh cycle, so the tick
        # stops and nothing is marked; read closed again, it is that cycle's.
        with self.assertLogs(_WORKFLOW_LOG):
            stopped = self._marked_by_the_poll()
        self.assertTrue(stopped)
        self.assertFalse(self._cancelled())

        self.owner.closed = True
        with self.assertLogs(_WORKFLOW_LOG):
            stopped = self._marked_by_the_poll()
        self.assertFalse(stopped)
        self.assertTrue(self._cancelled())

    def test_the_sweep_marks_nothing(self) -> None:
        with self._claimed(), self.assertLogs(_WORKFLOW_LOG):
            _late_sweep._handle_closed_owner_cleanup(self.github, _TEST_SPEC, self.owner)
        self.assertFalse(self._cancelled())
        self.assertEqual((self.github.posted_comments, self.github.label_history), ([], []))

        with self.assertLogs(_WORKFLOW_LOG):
            _late_sweep._handle_closed_owner_cleanup(self.github, _TEST_SPEC, self.owner)
        self.assertTrue(self._cancelled(), "outside the claim a reopened owner is marked all the same")


class LocalRestartTest(_RestartedCase, unittest.TestCase):
    """A close the poll read before this process's own restart, which no claim note records."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self._recorded(CYCLE_ID)
        self.assertTrue(claimable(self.github.repo_id, LATE_ISSUE_NUMBER))

    def test_a_close_read_after_the_restart_marks_it(self) -> None:
        polled_before = read_now()
        with _retiring_cycles.restarting(_SLUG, LATE_ISSUE_NUMBER):
            self._recorded(_RESTARTED)

        with self.assertLogs(_WORKFLOW_LOG):
            stopped = self._marked_by_the_poll(polled_before)
        self.assertTrue(stopped)
        self.assertFalse(self._cancelled())

        with self.assertLogs(_WORKFLOW_LOG):
            stopped = self._marked_by_the_poll(read_now())
        self.assertFalse(stopped)
        self.assertTrue(self._cancelled())


class ClaimedReceiptTest(_RestartedCase, unittest.TestCase):
    """The receipt a poll alongside the issue's writer posts, bound to the cycle it names."""

    def test_an_unproved_close_is_receipted_later(self) -> None:
        # Nothing ties the old close to the fresh cycle: no receipt, and no
        # memo saying one landed -- so the poll that reads the issue closed
        # again posts the one that fresh close is owed.
        self.assertTrue(self._receipted(), "the reading is still held for a pass under the claim")
        self.assertEqual(self._receipts(_RESTARTED), [])

        self.owner.closed = True
        with self.assertLogs(_WORKFLOW_LOG):
            self._receipted()
        self.assertEqual(len(self._receipts(_RESTARTED)), 1)

    def test_each_cycle_is_owed_its_own_receipt(self) -> None:
        # The memo of the ended cycle answers a repeat for that cycle without
        # a thread walk, and suppresses nothing for the cycle restarted after.
        self.owner.closed = True
        self._recorded(CYCLE_ID)
        with self.assertLogs(_WORKFLOW_LOG):
            self._receipted()
        with patch.object(self.github, "comments_after") as walked:
            self._receipted()
            walked.assert_not_called()

        self._recorded(_RESTARTED)
        with self.assertLogs(_WORKFLOW_LOG):
            self._receipted()

        self.assertEqual(len(self._receipts(CYCLE_ID)), 1)
        self.assertEqual(len(self._receipts(_RESTARTED)), 1)

    def test_a_local_restart_binds_no_receipt(self) -> None:
        # This process's own writer holds the claim and restarts the cycle
        # behind the receipt's record read, the issue standing closed: no read
        # pair confirms either cycle there, so nothing is scoped, posted, or
        # remembered -- and the next poll ties the close to the fresh cycle.
        self._fresh_process()
        self._latch_close(_SLUG, LATE_ISSUE_NUMBER)
        self._recorded(CYCLE_ID)
        self.owner.closed = True
        restart = _Behind(self.github.read_pinned_state, lambda: self._recorded(_RESTARTED))
        with self._claimed():
            with patch.object(self.github, "read_pinned_state", restart):
                self.assertTrue(self._receipted(), "the reading is still held")
            bound = (self._receipts(CYCLE_ID), _observations.close_scope(_SLUG, LATE_ISSUE_NUMBER))
            with self.assertLogs(_WORKFLOW_LOG):
                self._receipted()

        self.assertEqual(bound, ([], None), "the cycle the restart replaced is bound to nothing")
        self.assertEqual(len(self._receipts(_RESTARTED)), 1)
        self.assertEqual(_observations.close_scope(_SLUG, LATE_ISSUE_NUMBER), _RESTARTED)

    def _receipted(self) -> bool:
        """One poll's attempt at the durable half of its reading, beside this process's writer."""
        with self._claimed(alongside=True):
            return _late_close_observation._record_observed_close(self.github, _TEST_SPEC, LATE_ISSUE_NUMBER)

    def _receipts(self, cycle_id: int) -> list[str]:
        """Every receipt on the thread for one cycle's observed close."""
        marker = receipt_for(LATE_ISSUE_NUMBER, cycle_id)
        return [body for _, body in self.github.posted_comments if marker in body]


if __name__ == "__main__":
    unittest.main()
