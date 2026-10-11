# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settlement another road made while the recovery published the run, adopted out of step, holds the route.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery publishes and settles it with the attempt still standing. Just
as the artifact is posted, another road settles that very run itself and
leaves the records beside it out of step with it: it records a newer
transaction and retires it, spending a revision past the run, or it drops the
handoff that names the run. The recovery's own settlement is refused over that
moved comment, and the ledger entry it then commits alone takes the comment in
as it stands. Those records are held to the same agreement the finish asks of
settled evidence before it resolves anything, so the route is held: nothing
announced, relabelled, or retired, the round as it was spent, and the records
exactly as that road left them -- poll after poll. Nothing runs again, nothing
is pushed, and no developer is launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.engine.verification_settlement_state import settled_state
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _settles_the_run(case: support.CapturedRunCase, captured):
    """Settle `captured` over the artifact just posted, as another road would; the comment it left, unwritten."""
    state = case.gh.read_pinned_state(case.issue)
    posted = case.pull_request.issue_comments[-1]
    settled = settled_state(state, captured, posted.id, git_support.REVIEWING)
    case.assertIsNotNone(settled)
    return settled


def _spends_a_revision_past(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then record a newer transaction and retire it, raising the floor past the run."""
    state = _settles_the_run(case, captured)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, case.source.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.assertTrue(_carries.abandons(state, newer))
    case.gh.write_pinned_state(case.issue, state)


def _drops_the_handoff(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then drop the handoff that names it."""
    state = _settles_the_run(case, captured)
    state.set(_records.EVIDENCE_HANDOFF, None)
    case.gh.write_pinned_state(case.issue, state)


# What another road leaves beside the run it settled, and the revision floor
# that leaves: one past the run's, or the run's own.
_OUT_OF_STEP = (
    ("a revision spent past it", _spends_a_revision_past, 1),
    ("its handoff dropped", _drops_the_handoff, 0),
)


class AdoptedSettlementRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """Records another road settled out of step while the run was published hold the route, poll after poll."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, the records beside it
        # are left as it wrote them, and the attempt stands with nothing
        # announced, however often the recovery polls.
        for beside, settles, past in _OUT_OF_STEP:
            with self.subTest(beside=beside):
                captured = self._polls_beside(settles)

                self._assert_held_as_settled(captured, past)

    def _polls_beside(self, settles):
        """A fresh case's captured run, `settles` made just as the recovery posts it, then three recoveries; the run."""
        self.setUp()
        captured = self.captures()[1]
        races = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, partial(settles, self, captured))
        self.enterContext(patch.object(self.gh, support.POST, races))
        self.recovers()
        self.recovers()
        self.recovers()
        return captured

    def _assert_held_as_settled(self, captured, past: int) -> None:
        """`captured` current as the other road settled it, the floor `past` it, the attempt standing, nothing made."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.records(pinned)[1].receipt, captured.receipt)
        self.assertEqual(pinned[readings.KEY_REVISION_FLOOR], captured.revision + past)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))

if __name__ == "__main__":
    unittest.main()
