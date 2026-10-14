# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite finished again and again under the dormant settled-evidence policy, saying and making all once.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish held to the dormant settled-evidence policy (`settled_finish_support`)
and handed over directly: issue #7's rebased head reviewed, its finish running
and settling the configured command under the anchor and killed at one of the
final handoff boundaries (`rewrite_handoff_test_support`). Nothing the run
rests on moves. The direct finish behind it proves the settled run ready and
routes the head, and the one behind that finds no anchor and makes nothing.
Whichever boundary the first died at, the issue ends with one notice and one
`base_rebased` event, one artifact and one settlement of the run, its whole
binding current, the round reset and one relabel to `workflow:validating`, the
attempt retired, the command run once, and nothing pushed or launched.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)


class RepeatedFinishTest(settled.SettledRunCase, unittest.TestCase):
    """Direct finishes behind one killed at any boundary route the settled run once and repeat nothing."""

    def test_every_boundary_finishes_once(self) -> None:
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
                run = readings.pinned_records(self)[1]

                finished = [self.finishes(head, FinishRoad.RECOVERY) for _ in range(2)]

                self.assertEqual(finished, [FinishOutcome.ROUTED, FinishOutcome.UNFINISHABLE])
                self._assert_said_once(head)
                self._assert_settled_once(run)

    def _assert_said_once(self, head: str) -> None:
        """`head` announced, filed, and relabelled once, its attempt retired and its round reset; nothing made."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        pinned = readings.pinned(self)
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        self.assertEqual(pinned[readings.KEY_REVIEW_ROUND], 0)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))

    def _assert_settled_once(self, run) -> None:
        """`run` current whole, beside the evidence the rewrite moved past, its artifact posted once."""
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, retired), (None, git_support.invalidated(self)))
        whole = (current.receipt, current.revision, current.binding)
        self.assertEqual(whole, (run.receipt, run.revision, run.binding))
        self.assertEqual(len(self.posted(run)), 1)


if __name__ == "__main__":
    unittest.main()
