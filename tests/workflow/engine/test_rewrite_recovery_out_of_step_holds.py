# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a record beside it holds out of step, proved ready before that hold is applied.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
at a final handoff boundary (`rewrite_handoff_test_support`). The evidence
handoff then stops naming the run, which holds the next tick's route out of
step, and the issue is edited under the run as well. The recovery proves the
run before it applies that hold: the edit is movement under it, so the run is
invalidated into history whole, its revision and binding kept, and the route
is held with the attempt standing. Putting both the handoff and the issue back
before the next poll revives nothing: the head is announced and routed once
with nothing current, the run made once, and nothing pushed or launched.
"""
from __future__ import annotations

import unittest
from functools import partial

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


def _writes_beside(case: support.CapturedRunCase, handoff_record, body: str) -> tuple:
    """Write `handoff_record` as the evidence handoff and `body` as the issue's; the handoff and body they replaced."""
    state = case.gh.read_pinned_state(case.issue)
    replaced = (state.get(_records.EVIDENCE_HANDOFF), case.issue.body)
    state.set(_records.EVIDENCE_HANDOFF, handoff_record)
    case.gh.write_pinned_state(case.issue, state)
    case.issue.body = body
    return replaced


class OutOfStepHandoffTest(support.CapturedRunCase, unittest.TestCase):
    """A handoff out of step with settled evidence holds the route only behind that evidence's proof."""

    def test_holds_out_of_step_behind_the_proof(self) -> None:
        # The handoff stops naming the settled run and the issue is edited
        # under it: the run is invalidated before the route is held over that
        # handoff, so putting both back routes the head with nothing current.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
                settled = readings.pinned_records(self)[1]
                kept = _writes_beside(self, None, _EDITED_BODY)

                self.recovers()
                self._assert_invalidated(settled, standing=self.anchor)
                _writes_beside(self, *kept)
                self.recovers()

                self._assert_invalidated(settled, standing=None)
                self._assert_routed_once(head)

    def _assert_routed_once(self, head: str) -> None:
        """`head` filed as `base_rebased`, announced, and relabelled once."""
        noticed = len(readings.notices(self))
        said = (support.announced(self), noticed, readings.relabels(self))
        self.assertEqual(said, ([head], 1, readings.ROUTED))

    def _assert_invalidated(self, settled, *, standing: str | None) -> None:
        """`settled` invalidated whole, the attempt on `standing`, the run made once, nothing pushed or launched."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], standing)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
