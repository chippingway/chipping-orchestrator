# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run the evidence history no longer keeps is still this landing's, by the receipt on its attempt.

A finish recorded its run for the landed head and died posting its artifact,
and another road then recorded successors about the anchor over it, one after
another, until the history -- which keeps only its latest entries -- no longer
names the run at all. The receipt the finish put on the attempt beside the run
still does. So the recovery runs nothing again and decides nothing afresh: with
the last successor still pending it holds the route over that record poll
after poll, the successor and the revision floor it raised kept, nothing
announced; with that successor retired too, it routes the head to the fresh
reviewer, who owes the evidence; and with the remote rolled back onto the
anchor, it parks that rollback rather than pushing the replay over it. Nothing
runs again, nothing is pushed, and no developer is launched.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

# How many successors another road records over the run: one past what the
# history keeps, so the run is pushed out of it.
_EVICTING = _settlement._HISTORY_KEPT + 1


def _records_a_successor(case: support.CapturedRunCase, commands):
    """Record a transaction about the anchor over whatever `case`'s comment records, as another road would; it."""
    state = case.gh.read_pinned_state(case.issue)
    successor = _record_state.mint_pending_evidence(state, git_support.ISSUE, case.source.binding, commands)
    case.assertTrue(_record_state.record_pending_evidence(state, successor))
    case.gh.write_pinned_state(case.issue, state)
    return successor


def _retires_the_successor(case: support.CapturedRunCase, successor) -> None:
    """Abandon `successor` into the history, as the road that recorded it would."""
    state = case.gh.read_pinned_state(case.issue)
    case.assertTrue(_carries.abandons(state, successor))
    case.gh.write_pinned_state(case.issue, state)


class EvictedHistoryRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A run pushed out of the history is never run again, and nothing another road recorded is taken over it."""

    def test_a_pending_successor_holds(self) -> None:
        # The last successor is still pending: no finish of this landing can
        # answer it, so the route is held over it, poll after poll.
        captured, successor = self._evicts()[1:]

        self.recovers()
        self.recovers()

        self.assert_held(successor)
        self.assert_unannounced()
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], successor.revision)
        self.assertEqual(readings.pinned(self)[readings.KEY_EVIDENCE_RECEIPT], captured.receipt)
        self._assert_nothing_made_again()

    def test_a_retired_successor_routes(self) -> None:
        # The last successor was retired too: nothing is pending, and the
        # head is routed to the fresh reviewer with nothing decided afresh.
        head, _captured, successor = self._evicts()
        _retires_the_successor(self, successor)

        self.recovers()

        self.assert_recovered(head)
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self._assert_nothing_made_again()

    def test_a_rollback_parks(self) -> None:
        # The remote is rolled back onto the anchor: the receipt says the
        # replay's push landed, so the rollback parks with nothing pushed
        # over it, the successor kept as that road wrote it.
        successor = self._evicts()[2]
        self._git("update-ref", f"refs/heads/{git_support.BRANCH}", self.anchor, cwd=self._remote)
        self.pull_request.head.sha = self.anchor

        self.recovers()

        self.assertIn("rolled back or moved out of band", self.gh.posted_comments[-1][1])
        self.assertEqual(readings.pinned_records(self)[0], successor)
        self._assert_nothing_made_again()

    def _evicts(self) -> tuple:
        """Capture the run, then record successors over it until the history no longer names it.

        The landed head, the run, and the last successor.
        """
        head, captured = self.captures()
        successors = [_records_a_successor(self, captured.commands) for _ in range(_EVICTING)]
        self.assertNotIn(captured.receipt, dict(readings.pinned_records(self)[2]))
        return head, captured, successors[-1]

    def _assert_nothing_made_again(self) -> None:
        """The command run once, by the finish that captured the run; nothing pushed, no developer launched."""
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
