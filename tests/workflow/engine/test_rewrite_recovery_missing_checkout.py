# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A checkout gone from disk under a guarded park, its settled run's movement recorded before the park.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. Then the checkout goes from disk and the issue is
relabelled to a stage the refresh does not drive, so the dispatcher's anchor
hold answers it with the stranded park that keeps the attempt -- handed the
workflow's proof and park by the dispatcher's own answer
(`guarded_recovery_support`).

With no checkout there is nothing to prove the landing over, so the run is
retired on the state the park writes, and the movement is recorded against it
first, in a write of its own, by blanking the base tip the attempt recorded
its replay as made onto. A park record that lands keeps the attempt and
retires the run whole; one GitHub refuses, or a process killed before it,
leaves the run current, but read moving once the checkout and the label are
put back, so the proof a park that keeps the attempt asks invalidates it whole.
Nothing is run again, announced, relabelled, pushed, or launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
)

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

_AWAY = "checkout-away"


def _refuses_the_park(refused: set, live, issue, state, *, over: dict):
    """`live`, the client's pinned-comment edit, refused by GitHub where it is a park's record."""
    if guarded.parking(issue, state, over=over):
        refused.add(issue.number)
    answered = live(issue, state, over=over)
    refused.discard(issue.number)
    return answered


class MissingCheckoutTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout gone from disk has the movement recorded against the run before the stranded park retires it."""

    def test_a_landed_park_retires_the_run(self) -> None:
        # The stranded park keeps the attempt and lands the run's
        # invalidation in its own record, over the tip already blanked.
        settled = self._settles_then_strands()
        guarded.answers_a_held_anchor(self)
        self._returns()

        standing = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertEqual(standing, (True, self.anchor, None))
        self.assert_invalidated(settled)

    def test_a_park_that_never_lands(self) -> None:
        # The stranded park's record is refused, or the process is killed
        # ahead of it: the movement was recorded against the run first, so
        # with the checkout and the label put back the run reads moved, and
        # the proof invalidates it whole.
        for failing in ("refused", "killed"):
            with self.subTest(record=failing):
                self.setUp()
                settled = self._settles_then_strands()
                self._strands_unrecorded(failing)
                self._returns()

                self.assertEqual(readings.pinned_records(self)[1], settled)
                self.assertEqual(self.pinned_fields(readings.KEY_REWRITE_BASE), (None,))
                self.assertTrue(self.proves())
                self.assert_invalidated(settled)

    def _settles_then_strands(self):
        """Settle a reviewed rebase's run, kill its finish, move the checkout away, and relabel; the settled run."""
        settled = self.settles_then_dies()[1]
        self._wt.rename(self._wt.parent / _AWAY)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        return settled

    def _strands_unrecorded(self, failing: str) -> None:
        """Have the dispatcher's hold answer the issue, its park's record refused or the process killed before it."""
        if failing == "killed":
            handoff.dies_at(self.gh, guarded.BEFORE_THE_RECORD, partial(guarded.answers_a_held_anchor, self))
            return
        refusing = partial(_refuses_the_park, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(self.gh, "edit_pinned_state", refusing):
            guarded.answers_a_held_anchor(self)

    def _returns(self) -> None:
        """Put the checkout and the issue's label back where they stood."""
        (self._wt.parent / _AWAY).rename(self._wt)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]


if __name__ == "__main__":
    unittest.main()
