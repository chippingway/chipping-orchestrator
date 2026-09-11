# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick that did not live to the end of the guard leaves behind.

Two boundaries, one obligation, so one set of cases run at both. The read is
CLAIMED before it is taken and the claim rides the write that records the
result -- so a process killed inside the read and one killed before any of the
guard runs both leave an issue that still owes the read. Derived from the
failure instead, a tick that never saw one would leave nothing, and a revised
candidate is exactly the result that carries the next tick past the point a
retry could hang off: under the ceiling it is not adjudicable, and over it the
advanced generation has no recorded answer to short-circuit the spawn.

"The write that records the result" is every completion's own, not the
verdict's alone, which is what the second and third cases here are about. A
timeout, an unusable reply, an outcome too large to record, a worktree the
read-only agent moved, and a developer reconciliation nobody could make are
all finished runs the issue paid for -- so the seam immediately before the
guard has to find each of them already durable, park and claim together. A
tick that died there having written nothing would leave a generation still
reading as `adjudicating`, and the next one would pay for another agent.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split.models import LatePhase
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import late_settlement_support as _support
from tests.workflow.stages.decomposition.late_content_support import (
    PARK_REVISION_DIRTY,
    reply,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_PIN,
    DIRTY_TREE,
    REMEASURED,
    REMEASURED_OVERSIZED,
    REVISED_SHA,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    adjudicate,
)
from tests.workflow.stages.decomposition.late_settlement_support import GuardedLateCase
from tests.workflow.stages.decomposition.late_test_support import KEYS

# The two places a tick can die and still have to leave the read owed: inside
# the read, past the claim, and before any of the guard runs at all -- which
# is the one that decides whether the obligation belongs to the write that
# recorded the result or to the step after it.
_SEAMS = (
    ("inside the read", _support.OWNER_READ),
    ("before the guard", _support.OWNER_GUARD),
)


class KilledTickTest(RevisionCase):
    """Every seam leaves the same obligation, so every case runs at both."""

    def test_an_undersized_revision_owes_the_read(self) -> None:
        # Under the ceiling, so the size gate would route the next tick past
        # everything: without the claim, nothing would ever reconcile again.
        for name, seam in _SEAMS:
            with self.subTest(killed=name):
                self._revise_and_die(seam, REMEASURED)
                self._assert_owes_the_read()

                outcome, spawn = self._adjudicate_again()

                spawn.assert_not_called()
                self.assertEqual(
                    outcome.disposition, _LateDisposition.NOT_LATE,
                )
                self.assertNotIn(
                    KEYS.owner_check_pending, self._pinned(),
                )

    def test_an_oversized_revision_re_reads_first(self) -> None:
        # Past the ceiling, so the next tick would otherwise pay for a fresh
        # decomposer before finding out whether anybody still wants the issue.
        for name, seam in _SEAMS:
            with self.subTest(killed=name):
                self._revise_and_die(seam, REMEASURED_OVERSIZED)
                self._assert_owes_the_read()

                outcome, spawn = self._retry_unread()

                spawn.assert_not_called()
                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)

    def test_a_closure_answers_the_owed_read(self) -> None:
        for name, seam in _SEAMS:
            with self.subTest(killed=name):
                self._revise_and_die(seam, REMEASURED_OVERSIZED)
                self.issue.closed = True

                outcome, spawn = self._adjudicate_again()

                spawn.assert_not_called()
                self.assertEqual(
                    outcome.disposition, _LateDisposition.CANCELLED,
                )
                self.assertTrue(self._pinned().get(KEYS.cancelled))

    def _revise_and_die(self, seam: str, measurement) -> None:
        """Seed one issue and run a revision the kill at `seam` cuts short."""
        self._seed(**DEV_PIN)
        reply(self.issue)
        with _support.killed_at(seam), self.assertRaises(KeyboardInterrupt):
            self._revise(measurement=measurement)

    def _adjudicate_again(self):
        """The next tick, with no agent available to it."""
        return adjudicate(self.github, self.issue)

    def _retry_unread(self):
        """The next tick, whose own read fails, log line included."""
        with _support.unreadable_owner(self.github), self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR):
            return self._adjudicate_again()

    def _assert_owes_the_read(self) -> None:
        """The re-measurement landed, and the read it owes landed with it."""
        pinned = self._pinned()
        self.assertEqual(pinned.get(KEYS.candidate_sha), REVISED_SHA)
        self.assertTrue(pinned.get(KEYS.owner_check_pending))


class KilledCompletionTest(GuardedLateCase, unittest.TestCase):
    """Every non-verdict completion is durable before the guard is entered.

    A verdict is the obvious one: it is recorded and persisted where it is
    read. These four are the ones with nothing to persist but a park -- the
    session they pinned, the reason they hand the issue back for, and the read
    they now owe -- so each has to make that write itself. A completion that
    left all of it in memory would have the issue reading as though the agent
    were still running, on a tick that no longer exists to say otherwise.
    """

    def test_the_park_and_the_claim_survive(self) -> None:
        for completion in _support.PARKING_COMPLETIONS:
            with self.subTest(completion=completion[_support.NAME]):
                self._complete_and_die(completion)

                pinned = self._pinned()
                self.assertEqual(
                    pinned.get(KEYS.park_reason), completion[_support.REASON],
                )
                self.assertTrue(pinned.get(KEYS.owner_check_pending))
                self.assertEqual(
                    pinned.get(KEYS.phase), LatePhase.OWNER_CHECK,
                )

    def test_a_closure_after_it_still_cancels(self) -> None:
        # What the lost claim costs, in the case that cannot be recovered
        # from later: nothing brings a tick back to the read, so an issue
        # somebody closed while this one was dying is one the cycle never
        # finds out about -- and the cleanup path never runs against it.
        for completion in _support.PARKING_COMPLETIONS:
            with self.subTest(completion=completion[_support.NAME]):
                self._complete_and_die(completion)
                self.issue.closed = True

                outcome, spawn = adjudicate(self.github, self.issue)

                spawn.assert_not_called()
                self.assertEqual(
                    outcome.disposition, _LateDisposition.CANCELLED,
                )
                self.assertTrue(self._pinned().get(KEYS.cancelled))

    def _complete_and_die(self, completion: dict) -> None:
        """One finished run on a fresh issue, killed as the guard is entered.

        Re-seeded per case rather than per test, since each of these is one
        whole tick and the state it leaves is what the next assertion reads.
        """
        self.setUp()
        with _support.killed_at(_support.OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
            self._adjudicate(completion[_support.RUN], worktree=completion[_support.TREE])


class KilledReconciliationTest(RevisionCase):
    """A reconciliation that could not be made is durable before the guard.

    The sharpest of the completions, because the guidance that bought the run
    was consumed in memory: lose that write and the next tick finds the same
    reply unread and pays for a SECOND developer run of one that had already
    finished, against a checkout nobody has cleaned in between.
    """

    def test_the_park_and_the_claim_survive(self) -> None:
        self._reconcile_and_die()

        pinned = self._pinned()
        self.assertEqual(pinned.get(KEYS.park_reason), PARK_REVISION_DIRTY)
        self.assertTrue(pinned.get(KEYS.owner_check_pending))
        self.assertEqual(pinned.get(KEYS.phase), LatePhase.OWNER_CHECK)

    def test_the_next_tick_resumes_no_developer(self) -> None:
        self._reconcile_and_die()

        outcome, spawn = adjudicate(self.github, self.issue)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned().get(KEYS.park_reason), PARK_REVISION_DIRTY,
        )

    def _reconcile_and_die(self) -> None:
        """One finished developer run whose checkout could not be read."""
        self._seed(**DEV_PIN)
        reply(self.issue)
        with _support.killed_at(_support.OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
            self._revise(seed=WorktreeSeed(dirty=DIRTY_TREE))
