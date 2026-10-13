# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a recovery keeps the attempt over, proved ready before the hold or exit that keeps it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
at a final handoff boundary (`rewrite_handoff_test_support`). The issue is then
edited under the run, beside something that keeps the next tick's finish from
routing the head: the evidence handoff no longer naming the run, which holds
the route out of step; a pending record nobody can read beside a base that
advanced past the head again, which holds its continuation; or a base count
nobody could take, which finishes nothing. Each proves the run before it keeps
the attempt: the edit is movement under it, so the run is invalidated into
history whole, its revision and binding kept, with the attempt standing. The
base gone past a continued head is the continuation's own, not movement: with
nothing else moved, the held continuation keeps the run for the rebase behind
it.
Putting the issue and the rest back before the next poll revives nothing: the
head is routed, or continued to another rebase, with nothing current, the run
made once, and no developer launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import repeat
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.workflow.engine import (
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_EDITED_BODY = "Also cover a base that moved twice."

# A pending record no reader can take a transaction from.
_UNREADABLE = "unreadable"


def _writes_beside(case: support.CapturedRunCase, key: str, record, body: str) -> tuple:
    """Write `record` as `key` and `body` as the issue's; the record and body they replaced."""
    state = case.gh.read_pinned_state(case.issue)
    replaced = (key, state.get(key), case.issue.body)
    state.set(key, record)
    case.gh.write_pinned_state(case.issue, state)
    case.issue.body = body
    return replaced


class HoldProofTest(support.CapturedRunCase, unittest.TestCase):
    """A recovery keeping the attempt over settled evidence proves it first, so restoring what moved revives nothing."""

    def test_holds_out_of_step_behind_the_proof(self) -> None:
        # The handoff stops naming the settled run and the issue is edited
        # under it: the run is invalidated before the route is held over that
        # handoff, so putting both back routes the head with nothing current.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self._settles_then_dies(boundary)
                kept = _writes_beside(self, _records.EVIDENCE_HANDOFF, None, _EDITED_BODY)

                self.recovers()
                self._assert_invalidated(standing=self.anchor)
                _writes_beside(self, *kept)
                self.recovers()

                self._assert_invalidated(standing=None)
                self._assert_routed_once(head)

    def test_a_held_continuation_proves_the_run_first(self) -> None:
        # The base advances past the head again beside a pending record nobody
        # can read: the continuation is held, the run kept for the rebase
        # behind it where only the base moved, and invalidated first where
        # the issue was edited too; with both put back the head is continued
        # to another rebase with nothing of the run current.
        for edited in (False, True):
            with self.subTest(edited=edited):
                self.setUp()
                self._settles_then_dies(handoff.BEFORE_THE_ANNOUNCEMENT)
                support.advances_the_base_again(self)
                body = _EDITED_BODY if edited else self.issue.body
                kept = _writes_beside(self, _records.PENDING_EVIDENCE, _UNREADABLE, body)

                self.recovers()
                expected = None if edited else self.settled
                self.assertEqual(readings.pinned_records(self)[1], expected)
                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                _writes_beside(self, *kept)
                for _ in range(2):
                    self.recovers()

                self._assert_invalidated(standing=None, pushed=1)

    def test_an_unfinishable_landing_proves_first(self) -> None:
        # The candidate's base count cannot be taken, so the landing finishes
        # nothing, and the issue was edited: the run is invalidated before
        # the attempt is kept, and with the issue and the count back the head
        # is routed with nothing current.
        head = self._settles_then_dies(handoff.BEFORE_THE_ANNOUNCEMENT)
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        with patch.object(rewrite_facts, "_standing_on_the_base", side_effect=repeat(_BranchDivergence())):
            self.recovers()

        self._assert_invalidated(standing=self.anchor)
        self.issue.body = written
        self.recovers()

        self._assert_invalidated(standing=None)
        self._assert_routed_once(head)

    def _settles_then_dies(self, boundary: handoff.Boundary) -> str:
        """Land a reviewed rebase and settle its run, its finish killed at `boundary`; the head, the run kept."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        self.settled = readings.pinned_records(self)[1]
        return head

    def _assert_invalidated(self, *, standing: str | None, pushed: int = 0) -> None:
        """The settled run invalidated whole, the attempt on `standing`, the run made once, `pushed` pushes."""
        settled = self.settled
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], standing)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, pushed, 0))

    def _assert_routed_once(self, head: str) -> None:
        """`head` filed as `base_rebased`, announced, and relabelled once."""
        noticed = len(readings.notices(self))
        said = (support.announced(self), noticed, readings.relabels(self))
        self.assertEqual(said, ([head], 1, readings.ROUTED))


if __name__ == "__main__":
    unittest.main()
