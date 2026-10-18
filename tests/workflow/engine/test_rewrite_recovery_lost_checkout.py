# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settled run stays retired for good once a recovery finds its checkout gone from disk.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. Then the checkout goes from disk under the landed
road, the dispatcher's quiet hold, or a stranded park already standing --
ahead of the recovery's proof, while it is asked, behind one of its own
readings of the issue, or as the landed road reads the checkout as its
candidate -- and another road may write the base tip the reset's record
blanked back right behind it. The reset is recorded and the run retired, each
in a write of its own, so with the checkout back on the head -- the label and
a reply too, for the park -- the head is routed with nothing current. The run
is never made again, and nothing is pushed or launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.worktrees import creation
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import rewrite_landing_retirement as _retirement
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

_PROVES = "retires_unproved"


def _moves_past(case, live, *read, **options):
    """`live`, the checkout's reading, taken past a stray commit made on `case`'s checkout."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)
    return live(*read, **options)


def _vanishes_ahead(case, live, *asked, **options):
    """`live`, a call, asked once `case`'s checkout is gone from disk."""
    if case._wt.is_dir():
        case._wt.rename(case._away)
    return live(*asked, **options)


def _vanishes_behind(case, live, *asked, **options):
    """`live`, a call, its answer handed back once `case`'s checkout is gone from disk."""
    answered = live(*asked, **options)
    if case._wt.is_dir():
        case._wt.rename(case._away)
    return answered


class _LostCheckoutCase(guarded.GuardedRecoveryCase):
    """The finish case whose checkout a recovery finds gone from disk, put back once that recovery answered."""

    def setUp(self) -> None:
        super().setUp()
        self._away = self._wt.parent / "checkout-away"
        self._tips: list = []

    def settles(self) -> None:
        """Land a reviewed rebase, settle its run, and kill its finish, the head and the run kept for the case."""
        self._run = self.settles_then_dies()

    def strands_then(self, answers, again) -> None:
        """Settle and kill the finish, strand the attempt by `answers`, `again` it, and reply under the label."""
        self.settles()
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        answers()
        again(answers)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()

    def assert_retired(self) -> None:
        """The run invalidated whole while the checkout is away, and still once it is back on the head and routed."""
        head, settled = self._run
        self.assertFalse(self._wt.is_dir())
        self.assert_invalidated(settled)
        self._away.rename(self._wt)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        self.recovers()
        self.assert_routed(head)
        retired = readings.pinned_records(self)[2]
        self.assertIn((settled.receipt, readings.INVALIDATED), retired)


class RestoredTipTest(_LostCheckoutCase, unittest.TestCase):
    """The retirement a checkout gone from disk lands outlives the base tip written back behind its blank."""

    def test_a_vanishing_candidate(self) -> None:
        # The landed road reads the checkout committed past the head, and the
        # checkout goes from disk right behind that reading.
        self.settles()
        reads = partial(_vanishes_behind, self, partial(_moves_past, self, getattr(rewrite_facts, _READS)))
        with patch.object(rewrite_facts, _READS, reads):
            self._races(self.recovers)
        self.assert_retired()

    def test_a_quiet_hold(self) -> None:
        # The dispatcher holds a stage the refresh drives, and the checkout it
        # brings back for that refresh will not come back.
        self.settles()
        self._wt.rename(self._away)
        unavailable = RuntimeError("the checkout could not be brought back")
        with patch.object(creation, "_ensure_pr_worktree", side_effect=unavailable):
            self._races(partial(guarded.answers_a_held_anchor, self))
        self.assert_retired()

    def test_a_standing_park(self) -> None:
        # The dispatcher's hold of a stage the refresh does not drive finds
        # its stranded park already standing.
        self.strands_then(partial(guarded.answers_a_held_anchor, self), self._races_away)
        self.assert_retired()

    def _races_away(self, recovery) -> None:
        """Run `recovery` with the checkout gone from disk, the base tip written back behind its blank."""
        self._wt.rename(self._away)
        self._races(recovery)

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


class MidRoadCheckoutTest(_LostCheckoutCase, unittest.TestCase):
    """A checkout gone from disk after a recovery's caller found it on disk still has its run retired."""

    def test_a_moved_candidate(self) -> None:
        # The landed road reads the checkout committed past the head, and the
        # checkout goes as that movement's proof is asked.
        self.settles()
        with patch.object(rewrite_facts, _READS, partial(_moves_past, self, getattr(rewrite_facts, _READS))):
            self._vanishes_in_the_proof(self.recovers)
        self.assert_retired()

    def test_a_candidate_being_read(self) -> None:
        # The landed road's own git request reading the checkout as its
        # candidate finds it gone, outside any proof.
        self.settles()
        with patch.object(rewrite_facts, _READS, partial(_vanishes_ahead, self, getattr(rewrite_facts, _READS))):
            self.recovers()
        self.assert_retired()

    def test_a_quiet_hold(self) -> None:
        # The dispatcher holds a stage the refresh drives over a checkout on
        # disk, which goes as the hold's proof is asked.
        self.settles()
        self._vanishes_in_the_proof(partial(guarded.answers_a_held_anchor, self))
        self.assert_retired()

    def test_a_standing_park(self) -> None:
        # The dispatcher's hold, or the refresh's eligibility gate, finds its
        # stranded park already standing, and the checkout goes as its proof
        # is asked.
        answerers = {"dispatcher": partial(guarded.answers_a_held_anchor, self), "refresh": self.recovers}
        for answerer, answers in answerers.items():
            with self.subTest(answerer=answerer):
                self.setUp()
                self.strands_then(answers, self._vanishes_in_the_proof)
                self.assert_retired()

    def test_a_request_inside_the_proof(self) -> None:
        # The quiet hold's checkout goes right behind one of the proof's own
        # readings of the issue, so its next git request finds nothing there.
        self.settles()
        with patch.object(self.gh, "get_issue", partial(_vanishes_behind, self, self.gh.get_issue)):
            guarded.answers_a_held_anchor(self)
        self.assert_retired()

    def _vanishes_in_the_proof(self, recovery) -> None:
        """Run `recovery`, the checkout gone from disk right as the recovery's proof is first asked over it."""
        with patch.object(_retirement, _PROVES, partial(_vanishes_ahead, self, getattr(_retirement, _PROVES))):
            recovery()


if __name__ == "__main__":
    unittest.main()
