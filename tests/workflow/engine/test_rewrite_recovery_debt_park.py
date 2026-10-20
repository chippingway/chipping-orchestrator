# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run the recovery's debt park keeps exactly as captured, settled once room lets the route go on.

Issue #7's run captured for the landed head and the pinned comment left
without room for the landing's report debt, so the recovery's finish parks for
it: the push and the attempt kept, the run still recorded exactly as it was
captured, and nothing run again, pushed, or launched. Once room is made, the
next finish of the landing publishes and settles that very run and routes the
head once, with the command still run only the once the capture ran it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_AWAITING = "awaiting_human"

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250


class RecoveryDebtParkTest(support.CapturedRunCase, unittest.TestCase):
    """The recovery's finish parks for a debt with no room over its captured run, and settles that run behind it."""

    def setUp(self) -> None:
        support.CapturedRunCase.setUp(self)
        self.enterContext(patch.object(branch_transport, "_push_branch", self.pushes))
        self.enterContext(patch.object(_agent_runner, "run_agent", self.developer))

    def test_the_park_keeps_the_captured_run(self) -> None:
        # Parked with the run still pending as captured and nothing said for
        # the landing; room made, the run is settled as recorded and the head
        # routed once, nothing run again.
        head, captured = self.captures()
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.PARKED)

        self._assert_parked_over(captured)
        finish_moves.makes_room(self)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)

        self.assert_settled(captured)
        self.assertEqual(support.announced(self), [head])
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        made = (self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (0, 0))

    def _assert_parked_over(self, captured) -> None:
        """Parked with `captured` still pending as it was captured, nothing announced and the command run once."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.records(pinned)[0], captured)
        self.assertTrue(pinned[_AWAITING])
        self.assertEqual(support.announced(self), [])
        self.assertEqual(self.runs(), 1)


if __name__ == "__main__":
    unittest.main()
