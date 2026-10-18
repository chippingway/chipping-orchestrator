# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settled run stays retired for good when its checkout goes from disk while the recovery's proof is asked.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The checkout then goes from disk right as the
recovery's proof (`rewrite_landing_retirement.retires_unproved`) is asked
over it, after its caller read it on disk -- by the landed road that read it
committed past the head, by the dispatcher's quiet hold of a stage the refresh
drives, or by a stranded park already standing, found by the dispatcher or by
the refresh's eligibility gate -- or right behind one of the proof's own
readings of the issue, so its next git request finds nothing there. The proof
records the reset and retires the run, each in a write of its own, so with
the checkout back on the head -- the label and a reply too, for the park --
the head is routed with nothing current. The run is never made again, and
nothing is pushed or launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
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


class MidProofCheckoutTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """The retirement a proof owes over a checkout gone while it was asked lands, whoever asked it."""

    def setUp(self) -> None:
        super().setUp()
        self._away = self._wt.parent / "checkout-away"

    def test_a_moved_candidate(self) -> None:
        # The landed road reads the checkout committed past the head, and the
        # checkout goes as that movement's proof is asked.
        head, settled = self.settles_then_dies()
        with patch.object(rewrite_facts, _READS, partial(_moves_past, self, getattr(rewrite_facts, _READS))):
            self._vanishes_in_the_proof(self.recovers)
        self._assert_retired(head, settled)

    def test_a_quiet_hold(self) -> None:
        # The dispatcher holds a stage the refresh drives over a checkout on
        # disk, which goes as the hold's proof is asked.
        head, settled = self.settles_then_dies()
        self._vanishes_in_the_proof(partial(guarded.answers_a_held_anchor, self))
        self._assert_retired(head, settled)

    def test_a_standing_park(self) -> None:
        # The dispatcher's hold, or the refresh's eligibility gate, of a stage
        # the refresh does not drive finds its stranded park already
        # standing, and the checkout goes as its proof is asked; the author
        # replies once the label is put back.
        answerers = {"dispatcher": partial(guarded.answers_a_held_anchor, self), "refresh": self.recovers}
        for answerer, answers in answerers.items():
            with self.subTest(answerer=answerer):
                self.setUp()
                head, settled = self.settles_then_dies()
                self.issue.labels = [FakeLabel(_UNDRIVEN)]
                answers()
                self._vanishes_in_the_proof(answers)
                self.issue.labels = [FakeLabel(git_support.REVIEWING)]
                self.continues()
                self._assert_retired(head, settled)

    def test_a_request_inside_the_proof(self) -> None:
        # The dispatcher's quiet hold proves over a checkout on disk, which
        # goes right behind one of the proof's own readings of the issue, so
        # its next git request of the checkout finds nothing there.
        head, settled = self.settles_then_dies()
        with patch.object(self.gh, "get_issue", partial(_vanishes_behind, self, self.gh.get_issue)):
            guarded.answers_a_held_anchor(self)
        self.assertFalse(self._wt.is_dir())
        self._assert_retired(head, settled)

    def _vanishes_in_the_proof(self, recovery) -> None:
        """Run `recovery`, the checkout gone from disk right as the recovery's proof is first asked over it."""
        with patch.object(_retirement, _PROVES, partial(_vanishes_ahead, self, getattr(_retirement, _PROVES))):
            recovery()
        self.assertFalse(self._wt.is_dir())

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
