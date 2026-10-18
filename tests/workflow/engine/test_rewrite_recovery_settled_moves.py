# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence settled for a landed head, invalidated wherever a later tick's recovery reads the landing moving.

The real-git finish case (`rewrite_verification_recovery_support`), the run
settled and the finish killed at a final handoff boundary. The landing read
moving -- the checkout committed past the head, or the remote rolled back --
invalidates the run whole on whichever road that reading takes, so putting the
landing back revives nothing. The run is never made again, and no developer is
launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)


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
        # The recovery reads the landing off the head and resets or parks
        # without routing it: the run is invalidated first, and stays so once
        # the landing is put back and the issue's author replies.
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


if __name__ == "__main__":
    unittest.main()
