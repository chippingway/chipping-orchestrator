# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settled run whose checkout went from disk stays retired, however soon the base tip its reset blanked is put back.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. Then the checkout goes from disk -- right behind the
landed road reads it committed past the head, under a stage the refresh
drives while the dispatcher's hold cannot bring it back, or under a stranded
park already standing, which posts nothing -- and the recovery records the
reset against the run by blanking the attempt's base tip, which another road
writes back right behind. The run's retirement lands in a write of its own all
the same, over that tip, so with the checkout back on the head -- the label
and a reply too, for the park -- the head is routed with nothing current. The
run is never made again, and nothing is pushed or launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.worktrees import creation
from orchestrator.github.pinned_state import PinnedEdit
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

_READS = "_reads_the_checkout"


def _moves_then_vanishes(case, live, *read, **options):
    """`live`, the checkout's reading, taken past a stray commit, `case`'s checkout gone from disk right behind it."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)
    reading = live(*read, **options)
    case._wt.rename(case._away)
    return reading


class RestoredTipTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """The retirement a checkout gone from disk lands outlives the base tip written back behind its blank."""

    def setUp(self) -> None:
        super().setUp()
        self._away = self._wt.parent / "checkout-away"
        self._tips: list = []

    def test_a_candidate_whose_checkout_vanishes(self) -> None:
        # The landed road reads the checkout committed past the head, and the
        # checkout goes from disk right behind that reading.
        head, settled = self.settles_then_dies()
        reads = partial(_moves_then_vanishes, self, getattr(rewrite_facts, _READS))
        with patch.object(rewrite_facts, _READS, reads):
            self._races(self.recovers)
        self._assert_retired(head, settled)

    def test_a_quiet_hold(self) -> None:
        # The dispatcher holds a stage the refresh drives, and the checkout it
        # brings back for that refresh will not come back.
        head, settled = self.settles_then_dies()
        self._wt.rename(self._away)
        unavailable = RuntimeError("the checkout could not be brought back")
        with patch.object(creation, "_ensure_pr_worktree", side_effect=unavailable):
            self._races(partial(guarded.answers_a_held_anchor, self))
        self._assert_retired(head, settled)

    def test_a_standing_park(self) -> None:
        # The dispatcher's hold of a stage the refresh does not drive finds
        # its stranded park already standing, and the author replies once the
        # label is put back.
        head, settled = self.settles_then_dies()
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        guarded.answers_a_held_anchor(self)
        self._wt.rename(self._away)
        self._races(partial(guarded.answers_a_held_anchor, self))
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()
        self._assert_retired(head, settled)

    def _races(self, recovery) -> None:
        """Run `recovery`, the base tip another road writes back right behind the edit that first blanks it."""
        self._tips.append(self.pinned_fields(readings.KEY_REWRITE_BASE)[0])
        with patch.object(self.gh, "edit_pinned_state", partial(self._puts_back_behind, self.gh.edit_pinned_state)):
            recovery()
        self.assertEqual(self._tips, [])

    def _puts_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the tip held written back right behind the first to blank it."""
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        read = options["over"].get(tip)
        blanks = read is not None and staged.get(tip) is None
        if answered is PinnedEdit.EDITED and blanks and self._tips:
            state = self.gh.read_pinned_state(issue)
            state.set(tip, self._tips.pop())
            self.gh.write_pinned_state(issue, state)
        return answered

    def _assert_retired(self, head: str, settled) -> None:
        """`settled` invalidated whole while the checkout is away, and still once it is back on `head` and routed."""
        self.assert_invalidated(settled)
        self._away.rename(self._wt)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        self.recovers()
        self.assert_routed(head)
        retired = readings.pinned_records(self)[2]
        self.assertIn((settled.receipt, readings.INVALIDATED), retired)


if __name__ == "__main__":
    unittest.main()
